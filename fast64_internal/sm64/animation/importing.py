import os, re, dataclasses, numpy as np

import bpy
from bpy.path import abspath
from bpy.types import Object, Action, Context, PoseBone
from mathutils import Quaternion

from ...utility import PluginError, decodeSegmentedAddr, filepath_checks, is_bit_active, path_checks, intToHex
from ...utility_anim import stashActionInArmature
from ..sm64_constants import level_pointers
from ..sm64_level_parser import parseLevelAtPointer
from ..sm64_utility import import_rom_checks
from ..sm64_classes import RomReader

from .utility import (
    animation_operator_checks,
    get_anim_file_name,
    get_anim_name,
    get_anim_pose_bones,
    get_animation_props,
    get_frame_range,
    update_header_variant_numbers,
    get_anim_actor_name,
)
from .classes import (
    Animation,
    CArrayDeclaration,
    AnimationHeader,
    AnimationTable,
    AnimationTableElement,
)
from .constants import FLAG_PROPS, ACTOR_PRESET_INFO, C_FLAGS

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .properties import (
        SM64_AnimImportProperties,
        SM64_ArmatureAnimProperties,
        SM64_AnimHeaderProperties,
        SM64_AnimTableProperties,
        SM64_ActionProperty,
    )
    from ..settings.properties import SM64_Properties
    from ..sm64_objects import SM64_CombinedObjectProperties


def flip_euler(euler: np.ndarray) -> np.ndarray:
    euler = euler.copy()
    euler[1] = -euler[1]
    euler += np.pi
    return euler


def naive_flip_diff(a1: np.ndarray, a2: np.ndarray) -> np.ndarray:
    diff = a1 - a2
    mask = np.abs(diff) > np.pi
    return a2 + mask * np.sign(diff) * 2 * np.pi


@dataclasses.dataclass
class FramesHolder:
    frames: np.ndarray = dataclasses.field(default_factory=list)

    def populate_action(self, action: Action, pose_bone: PoseBone, path: str):
        for property_index in range(3):
            f_curve = action.fcurves.new(
                data_path=pose_bone.path_from_id(path),
                index=property_index,
                action_group=pose_bone.name,
            )
            for time, frame in enumerate(self.frames):
                f_curve.keyframe_points.insert(time, frame[property_index], options={"FAST"})


def euler_to_quaternion(euler_angles: np.ndarray):
    """
    Fast vectorized euler to quaternion function, euler_angles is an array of shape (-1, 3)
    """
    phi = euler_angles[:, 0]
    theta = euler_angles[:, 1]
    psi = euler_angles[:, 2]

    half_phi = phi / 2.0
    half_theta = theta / 2.0
    half_psi = psi / 2.0

    cos_half_phi = np.cos(half_phi)
    sin_half_phi = np.sin(half_phi)
    cos_half_theta = np.cos(half_theta)
    sin_half_theta = np.sin(half_theta)
    cos_half_psi = np.cos(half_psi)
    sin_half_psi = np.sin(half_psi)

    q_w = cos_half_phi * cos_half_theta * cos_half_psi + sin_half_phi * sin_half_theta * sin_half_psi
    q_x = sin_half_phi * cos_half_theta * cos_half_psi - cos_half_phi * sin_half_theta * sin_half_psi
    q_y = cos_half_phi * sin_half_theta * cos_half_psi + sin_half_phi * cos_half_theta * sin_half_psi
    q_z = cos_half_phi * cos_half_theta * sin_half_psi - sin_half_phi * sin_half_theta * cos_half_psi

    quaternions = np.vstack((q_w, q_x, q_y, q_z)).T  # shape (-1, 4)
    return quaternions


@dataclasses.dataclass
class RotationFramesHolder(FramesHolder):
    @property
    def quaternion(self):
        return euler_to_quaternion(self.frames)

    def get_euler(self, order: str):
        if order == "XYZ":
            return self.frames
        return [Quaternion(x).to_euler(order) for x in self.quaternion]

    @property
    def axis_angle(self):
        result = []
        for x in self.quaternion:
            x = Quaternion(x).to_axis_angle()
            result.append([x[1]] + list(x[0]))
        return result

    def populate_action(self, action: Action, pose_bone: PoseBone):
        rotation_mode = pose_bone.rotation_mode
        rotation_mode_name = {
            "QUATERNION": "rotation_quaternion",
            "AXIS_ANGLE": "rotation_axis_angle",
        }.get(rotation_mode, "rotation_euler")
        data_path = pose_bone.path_from_id(rotation_mode_name)

        size = 4
        if rotation_mode == "QUATERNION":
            rotations = self.quaternion
        elif rotation_mode == "AXIS_ANGLE":
            rotations = self.axis_angle
        else:
            rotations = self.get_euler(rotation_mode)
            size = 3
        for property_index in range(size):
            f_curve = action.fcurves.new(
                data_path=data_path,
                index=property_index,
                action_group=pose_bone.name,
            )
            for frame, rotation in enumerate(rotations):
                f_curve.keyframe_points.insert(frame, rotation[property_index], options={"FAST"})


@dataclasses.dataclass
class IntermidiateAnimationBone:
    translation: FramesHolder = dataclasses.field(default_factory=FramesHolder)
    rotation: RotationFramesHolder = dataclasses.field(default_factory=RotationFramesHolder)

    def read_pairs(self, pairs: list["SM64_AnimPair"]):
        pair_count = len(pairs)
        max_length = max(len(pair.values) for pair in pairs)
        result = np.empty((max_length, pair_count), dtype=np.int16)

        for i, pair in enumerate(pairs):
            current_length = len(pair.values)
            result[:current_length, i] = pair.values
            result[current_length:, i] = pair.values[-1]
        return result

    def read_translation(self, pairs: list["SM64_AnimPair"], scale: float):
        self.translation.frames = self.read_pairs(pairs) / scale

    def continuity_filter(self, frames: np.ndarray) -> np.ndarray:
        if len(frames) <= 1:
            return frames

        # There is no way to fully vectorize this function
        prev = frames[0]
        for frame, euler in enumerate(frames):
            euler = naive_flip_diff(prev, euler)
            flipped_euler = naive_flip_diff(prev, flip_euler(euler))
            if np.all((prev - flipped_euler) ** 2 < (prev - euler) ** 2):
                euler = flipped_euler
            frames[frame] = prev = euler

        return frames

    def read_rotation(self, pairs: list["SM64_AnimPair"], continuity_filter: bool):
        frames = self.read_pairs(pairs).astype(np.uint16).astype(np.float32)
        frames *= 360.0 / (2**16)
        frames = np.radians(frames)
        if continuity_filter:
            frames = self.continuity_filter(frames)
        self.rotation.frames = frames

    def populate_action(self, action: Action, pose_bone: PoseBone):
        self.translation.populate_action(action, pose_bone, "location")
        self.rotation.populate_action(action, pose_bone)


def from_header_class(
    header_props: "SM64_AnimHeaderProperties",
    header: AnimationHeader,
    action: Action,
    actor_name: str,
    use_custom_name: bool,
):
    if (
        isinstance(header.reference, str)
        and header.reference != get_anim_name(actor_name, action, header_props)
        and use_custom_name
    ):
        header_props.custom_name = header.reference
        header_props.use_custom_name = True

    correct_frame_range = header.start_frame, header.loop_start, header.loop_end
    header_props.start_frame, header_props.loop_start, header_props.loop_end = correct_frame_range
    auto_frame_range = get_frame_range(action, header_props)
    if correct_frame_range != auto_frame_range:
        header_props.manual_loop = True

    header_props.trans_divisor = header.trans_divisor

    # Flags
    if isinstance(header.flags, int):
        int_flags = header.flags
        header_props.custom_flags = intToHex(header.flags, 2)
        if int_flags >> 6:  # If any non supported bit is active
            header_props.set_custom_flags = True
    else:
        header_props.custom_flags = header.flags
        int_flags = 0

        flags = header.flags.lstrip("(").rstrip(")").split("|")
        try:
            int_flags = int(header.flags, 0)
        except ValueError:
            for flag in flags:
                flag = flag.strip()
                index = next((index for index, flag_tuple in enumerate(C_FLAGS) if flag in flag_tuple), None)
                if index is not None:
                    int_flags |= 1 << index
                else:
                    header_props.set_custom_flags = True  # Unknown flag
    header_props.custom_int_flags = intToHex(int_flags, 2)
    for index, prop in enumerate(FLAG_PROPS):
        setattr(header_props, prop, is_bit_active(int_flags, index))

    header_props.table_index = header.table_index


def from_anim_class(
    action_props: "SM64_ActionProperty",
    action: Action,
    animation: Animation,
    actor_name: str,
    use_custom_name: bool,
):
    main_header = animation.headers[0]
    is_from_binary = isinstance(main_header.reference, int)

    if animation.action_name:
        action_name = animation.action_name
    elif main_header.file_name:
        action_name = main_header.file_name.rstrip(".c").rstrip(".inc")
    elif is_from_binary:
        action_name = intToHex(main_header.reference)

    index = action_name.find("anim_")
    if index != -1:
        action_name = action_name.lstrip("anim_")
    action.name = action_name
    print(f'Populating action "{action_name}" properties.')

    indice_reference = main_header.indice_reference
    values_reference = main_header.values_reference
    if is_from_binary:
        indice_reference = intToHex(indice_reference)
        values_reference = intToHex(values_reference)
        action_props.indices_address, action_props.values_address = indice_reference, values_reference
    action_props.indices_table = indice_reference
    action_props.values_table = values_reference

    if animation.data:
        file_name = animation.data.indices_file_name
        action_props.custom_max_frame = max([1] + [len(x.values) for x in animation.data.pairs])
    else:
        file_name = main_header.file_name
        action_props.reference_tables = True
    if file_name:
        action_props.custom_file_name = file_name
        if use_custom_name and get_anim_file_name(action, action_props) != action_props.custom_file_name:
            action_props.use_custom_file_name = True
    if is_from_binary:
        start_addresses = [x.reference for x in animation.headers]
        end_addresses = [x.end_address for x in animation.headers]
        if animation.data:
            start_addresses.append(animation.data.indice_reference)
            end_addresses.append(animation.data.indice_reference)
            start_addresses.append(animation.data.values_reference)
            end_addresses.append(animation.data.value_end_address)
        action_props.start_address = intToHex(min(start_addresses))
        action_props.end_address = intToHex(max(end_addresses))

    print("Populating header properties.")
    for i, header in enumerate(animation.headers):
        if i:
            action_props.header_variants.add()
        header_props = action_props.headers[-1]
        header.action = action  # Used in table class to prop
        from_header_class(header_props, header, action, actor_name, use_custom_name)

    update_header_variant_numbers(action_props)


def from_table_element_class(element_props: "SM64_AnimTableElement", element: AnimationTableElement):
    if element.header:
        element_props.set_variant(element.header.action, element.header.header_variant)
    else:
        element_props.reference = True
    if isinstance(element.reference, int):
        element_props.header_address = intToHex(element.reference)
    else:
        element_props.header_name = element.reference
        element_props.header_address = intToHex(0)
    if element.enum_name:
        element_props.enum_name = element.enum_name


def from_anim_table_class(
    table_props: "SM64_AnimTableProperties",
    table: AnimationTable,
    clear_table: bool,
    use_custom_name: bool,
    actor_name: str,
):
    if clear_table:
        table_props.elements.clear()
    for element in table.elements:
        table_props.elements.add()
        from_table_element_class(table_props.elements[-1], element)

    if isinstance(table.reference, int):  # Binary
        table_props.dma_address = intToHex(table.reference)
        table_props.dma_end_address = intToHex(table.end_address)
        table_props.address = intToHex(table.reference)
        table_props.end_address = intToHex(table.end_address)

        # Data
        start_addresses = []
        end_addresses = []
        for element in table.elements:
            if element.header and element.header.data:
                start_addresses.append(element.header.data.start_address)
                end_addresses.append(element.header.data.end_address)
        if start_addresses and end_addresses:
            table_props.write_data_seperately = True
            table_props.data_address = intToHex(min(start_addresses))
            table_props.data_end_address = intToHex(max(end_addresses))
    elif table.reference:
        if use_custom_name:
            table_props.custom_table_name = table.reference
            if table_props.get_name(actor_name) != table_props.custom_table_name:
                table_props.use_custom_table_name = True


def animation_import_to_blender(
    armature_obj: Object,
    blender_to_sm64_scale: float,
    anim_import: Animation,
    actor_name: str,
    use_custom_name: bool,
    force_quaternion: bool,
    continuity_filter: bool,
):
    if armature_obj.animation_data is None:
        armature_obj.animation_data_create()
    action = bpy.data.actions.new("")
    try:
        if anim_import.data:
            print("Converting pairs to intermidiate data.")
            bones = get_anim_pose_bones(armature_obj)
            bones_data: list[IntermidiateAnimationBone] = []
            pairs = anim_import.data.pairs
            for pair_num in range(3, len(pairs), 3):
                bone = IntermidiateAnimationBone()
                if pair_num == 3:
                    bone.read_translation(pairs[0:3], blender_to_sm64_scale)
                bone.read_rotation(pairs[pair_num : pair_num + 3], continuity_filter)
                bones_data.append(bone)
            print("Populating action keyframes.")
            for pose_bone, bone_data in zip(bones, bones_data):
                if force_quaternion:
                    pose_bone.rotation_mode = "QUATERNION"
                bone_data.populate_action(action, pose_bone)

        from_anim_class(
            action.fast64.sm64,
            action,
            anim_import,
            actor_name,
            use_custom_name,
        )
        stashActionInArmature(armature_obj, action)
        return action
    except PluginError as exc:
        bpy.data.actions.remove(action)
        raise exc


COMMENT_SUB_PATTERN = re.compile(r'//.*?$|/\*.*?\*/|\'(?:\\.|[^\\\'])*\'|"(?:\\.|[^\\"])*"', re.DOTALL | re.MULTILINE)


def comment_remover(text: str):
    def replacer(match):
        s = match.group(0)
        if s.startswith("/"):
            return " "  # note: a space and not an empty string
        else:
            return s

    return re.sub(COMMENT_SUB_PATTERN, replacer, text)


DECL_PATTERN = re.compile(
    r"(static\s+const\s+struct\s+Animation|static\s+const\s+u16|static\s+const\s+s16|const\s+struct Animation\s+\*const)\s+(\w+)\s*?(?:\[.*?\])?\s*?=\s*?\{(.*?)\};",
    re.DOTALL,
)
VALUE_SPLIT_PATTERN = re.compile(r"\s*([^,\s]+)\s*(?:,|$)")


def find_decls(c_data: str, f: os.PathLike, decl_list: dict[str, list[CArrayDeclaration]]):
    file_basename = os.path.basename(f)
    matches = DECL_PATTERN.findall(c_data)
    for decl_type, name, value_text in matches:
        values = VALUE_SPLIT_PATTERN.findall(value_text)
        decl_list[decl_type].append(CArrayDeclaration(name, f, file_basename, values))


def import_c_animations(
    path: os.PathLike,
    read_headers: dict[str, AnimationHeader],
    read_animations: dict[tuple[str, str], Animation],
    table: AnimationTable,
):
    path_checks(path)
    if os.path.isfile(path):
        file_paths = [path]
    else:
        file_paths = sorted(
            [os.path.join(root, filename) for root, _, files in os.walk(path) for filename in files],
        )

    print(f"Reading from: {', '.join(file_paths)}.")
    decl_lists = {
        "static const struct Animation": [],
        "static const u16": [],
        "static const s16": [],
        "const struct Animation *const": [],
    }

    for file_path in file_paths:
        print(f"Reading from: {file_path}.")
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            c_data = comment_remover(f.read())
        find_decls(c_data, file_path, decl_lists)

    header_decls = decl_lists["static const struct Animation"]
    indices_decls = decl_lists["static const u16"]
    value_decls = decl_lists["static const s16"]
    table_decls = decl_lists["const struct Animation *const"]

    if table_decls:
        if len(table_decls) > 1:
            raise ValueError("More than 1 table declaration")
        table.read_c(
            table_decls[0],
            read_headers,
            read_animations,
            header_decls,
            value_decls,
            indices_decls,
        )
    else:
        for table_index, header_decl in enumerate(sorted(header_decls, key=lambda h: h.name)):
            AnimationHeader().read_c(
                header_decl, value_decls, indices_decls, read_headers, read_animations, table_index
            )


def import_binary_animations(
    data_reader: RomReader,
    import_type: str,
    read_headers: dict[str, AnimationHeader],
    read_animations: dict[tuple[str, str], Animation],
    table: AnimationTable,
    table_index: int | None = None,
    assumed_bone_count: int | None = None,
    table_size: int | None = None,
):
    if import_type == "Table":
        table.read_binary(data_reader, read_headers, read_animations, table_index, assumed_bone_count, table_size)
    elif import_type == "DMA":
        table.read_dma_binary(data_reader, read_headers, read_animations, table_index, assumed_bone_count)
    elif import_type == "Animation":
        AnimationHeader.read_binary(
            data_reader,
            read_headers,
            read_animations,
            False,
            assumed_bone_count,
            table_size,
        )
    else:
        raise PluginError("Unimplemented binary import type.")


def import_insertable_binary_animations(
    reader: RomReader,
    read_headers: dict[str, AnimationHeader],
    read_animations: dict[tuple[str, str], Animation],
    table: AnimationTable,
    table_index: int | None = None,
    assumed_bone_count: int | None = None,
    table_size: int | None = None,
):
    if reader.insertable.data_type == "Animation":
        AnimationHeader.read_binary(
            reader,
            read_headers,
            read_animations,
            False,
            assumed_bone_count,
        )
    elif reader.insertable.data_type == "Animation Table":
        table.read_binary(reader, read_headers, read_animations, table_index, assumed_bone_count, table_size)
    elif reader.insertable.data_type == "Animation DMA Table":
        table.read_dma_binary(reader, read_headers, read_animations, table_index, assumed_bone_count)


def import_animations(context: Context):
    animation_operator_checks(context, False)

    scene = context.scene
    armature_obj: Object = context.object
    sm64_props: SM64_Properties = scene.fast64.sm64
    combined_props: SM64_CombinedObjectProperties = sm64_props.combined_export
    import_props: SM64_AnimImportProperties = sm64_props.animation.importing
    anim_props: SM64_ArmatureAnimProperties = armature_obj.data.fast64.sm64.animation
    table_props: SM64_AnimTableProperties = anim_props.table

    read_animations: dict[tuple[str, str], Animation] = {}
    read_headers: dict[str, AnimationHeader] = {}
    table = AnimationTable()

    import_type = import_props.import_type
    if import_type == "Insertable Binary" or import_props.preset == "Custom":
        preset = None
        level = import_props.level
        table_size = import_props.table_size
        if import_type == "C":
            c_path = abspath(import_props.path)
        else:
            if import_type == "Binary":
                is_segmented_address = import_props.is_segmented_address
                address = import_props.address
                binary_type = import_props.binary_import_type
            table_index = import_props.table_index
    else:  # Preset
        preset = ACTOR_PRESET_INFO[import_props.preset]
        if import_type == "C":
            decomp_path = import_props.decomp_path
            decomp_path = decomp_path if decomp_path else sm64_props.decomp_path
            directory = preset.animation.directory
            directory = directory if directory else f"{preset.decomp_path}/anims"
            c_path = abspath(os.path.join(decomp_path, directory))
        else:
            level = preset.level
            address = preset.animation.address
            table_size = preset.animation.size
            binary_type = "DMA" if preset.animation.dma else "Table"
            is_segmented_address = False if preset.animation.dma else True
            table_index = import_props.table_index

    if import_type in {"Binary", "Insertable Binary"}:
        bone_count = len(get_anim_pose_bones(armature_obj)) if import_props.assume_bone_count else None
        binary_args = (
            read_headers,
            read_animations,
            table,
            table_index,
            bone_count,
            table_size,
        )

    print("Reading animation data.")
    if import_type == "Binary":
        rom_path = abspath(import_props.rom if import_props.rom else sm64_props.import_rom)
        import_rom_checks(rom_path)
        with open(rom_path, "rb") as rom_file:
            if binary_type == "DMA":
                segment_data = None
            else:
                segment_data = parseLevelAtPointer(rom_file, level_pointers[level]).segmentData
                if is_segmented_address:
                    address = decodeSegmentedAddr(address.to_bytes(4, "big"), segment_data)
            import_binary_animations(
                RomReader(rom_file, start_address=address, segment_data=segment_data), binary_type, *binary_args
            )
    elif import_type == "Insertable Binary":
        path = abspath(import_props.path)
        filepath_checks(path)
        with open(path, "rb") as insertable_file:
            if not import_props.read_from_rom:
                import_insertable_binary_animations(RomReader(insertable_file=insertable_file), *binary_args)
            else:
                with open(rom_path, "rb") as rom_file:
                    segment_data = parseLevelAtPointer(rom_file, level_pointers[level]).segmentData
                    import_insertable_binary_animations(
                        RomReader(rom_file, insertable_file=insertable_file, segment_data=segment_data),
                        *binary_args,
                    )
    elif import_type == "C":
        path_checks(c_path)
        import_c_animations(c_path, read_headers, read_animations, table)

    if not table.elements:
        print("No table was read. Automatically creating table.")
        table.elements = [AnimationTableElement(header=header) for header in read_headers.values()]

    if preset:
        preset_animation_names = get_preset_anim_name_list(import_props.preset)
        for animation in read_animations.values():
            animation_names = []
            for header in animation.headers:
                if header.table_index < len(preset_animation_names):
                    animation_names.append(preset_animation_names[header.table_index])
            if animation_names:
                animation.action_name = " ".join(animation_names)

    print("Importing animations into blender.")
    actions = []
    for animation in read_animations.values():
        actions.append(
            animation_import_to_blender(
                armature_obj,
                sm64_props.blender_to_sm64_scale,
                animation,
                combined_props.obj_name_anim,  # TODO: is this fine?
                import_props.use_custom_name,
                import_props.force_quaternion,
                import_props.continuity_filter if not import_props.force_quaternion else True,
            )
        )

    if import_props.run_decimate:
        old_area = bpy.context.area.type
        old_action = armature_obj.animation_data.action
        try:
            bpy.ops.object.posemode_toggle()  # Select all bones
            bpy.ops.pose.select_all(action="SELECT")

            bpy.context.area.type = "GRAPH_EDITOR"
            for action in actions:
                print(f"Decimating {action.name}.")
                armature_obj.animation_data.action = action
                bpy.ops.graph.select_all(action="SELECT")
                bpy.ops.graph.decimate(mode="ERROR", factor=1, remove_error_margin=import_props.decimate_margin)
        finally:
            bpy.context.area.type = old_area
            armature_obj.animation_data.action = old_action

    print("Importing animation table into properties.")
    from_anim_table_class(  # TODO: is the table address range including the null delimiter?
        table_props, table, import_props.clear_table, import_props.use_custom_name, get_anim_actor_name(context)
    )


def get_preset_anim_name_list(preset: str):
    assert preset in ACTOR_PRESET_INFO, "Selected preset not in actor presets"
    preset_info = ACTOR_PRESET_INFO[preset]
    assert preset_info.animation is not None, "Selected preset's actor has not animation information"
    return preset_info.animation.names


def get_enum_from_import_preset(_self, context):
    try:
        preset = get_animation_props(context).importing.preset
        animation_names = get_preset_anim_name_list(preset)
        return [("Custom", "Custom", "Pick your own animation index", len(animation_names))] + [
            (str(i), name, f'"{preset}" Animation {i}', i) for i, name in enumerate(animation_names)
        ]
    except:
        return [("Custom", "Custom", "Pick your own animation index", 0)]
