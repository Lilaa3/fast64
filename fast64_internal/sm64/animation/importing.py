import math
import os
import re

import bpy
from bpy.path import abspath
from bpy.types import Object, Action, Context
from mathutils import Euler, Vector, Quaternion

from ...utility import PluginError, decodeSegmentedAddr, filepath_checks, is_bit_active, path_checks, intToHex
from ...utility_anim import stashActionInArmature
from ..sm64_constants import insertableBinaryTypes, level_pointers
from ..sm64_level_parser import parseLevelAtPointer
from ..sm64_utility import import_rom_checks
from ..classes import RomReader

from .utility import (
    animation_operator_checks,
    get_anim_file_name,
    get_anim_name,
    get_anim_pose_bones,
    get_animation_props,
    get_frame_range,
    sm64_to_radian,
    update_header_variant_numbers,
)
from .classes import (
    Animation,
    CArrayDeclaration,
    AnimHeader,
    AnimPair,
    AnimationTable,
    AnimationTableElement,
)
from .constants import FLAG_PROPS, ACTOR_PRESET_INFO

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .properties import (
        ImportProps,
        AnimProps,
        HeaderProps,
        TableProps,
        SM64_ActionProps,
    )
    from ..settings.properties import SM64_Properties


def from_header_class(
    header_props: "HeaderProps",
    header: AnimHeader,
    action: Action,
    actor_name: str = "mario",
    use_custom_name: bool = True,
):
    if (
        isinstance(header.reference, str)
        and header.reference != get_anim_name(actor_name, action, header_props)
        and use_custom_name
    ):
        header_props.custom_name = header.reference
        header_props.override_name = True

    correct_frame_range = header.start_frame, header.loop_start, header.loop_end
    header_props.start_frame, header_props.loop_start, header_props.loop_end = correct_frame_range
    auto_frame_range = get_frame_range(action, header_props)
    if correct_frame_range != auto_frame_range:
        header_props.manual_frame_range = True

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

        flags = header.flags.replace(" ", "").lstrip("(").rstrip(")").split(" | ")
        try:
            int_flags = int(header.flags, 0)
        except ValueError:
            for flag in flags:
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
    action_props: "SM64_ActionProps",
    action: Action,
    animation: Animation,
    actor_name: str,
    remove_name_footer: bool = True,
    use_custom_name: bool = True,
):
    main_header = animation.headers[0]
    is_from_binary = isinstance(main_header.reference, int)

    if main_header.file_name:
        action_name = main_header.file_name.rstrip(".c").rstrip(".inc")
    elif is_from_binary:
        action_name = intToHex(main_header.reference)
    else:
        action_name = main_header.reference

    if remove_name_footer:
        index = action_name.find("anim_")
        if index != -1:
            action_name = action_name[index + 5 :]
    action.name = action_name

    indice_reference = main_header.indice_reference
    values_reference = main_header.values_reference
    if is_from_binary:
        indice_reference = intToHex(indice_reference)
        values_reference = intToHex(values_reference)
        action_props.indices_address, action_props.values_address = indice_reference, values_reference
    action_props.indices_table = indice_reference
    action_props.values_table = values_reference

    if animation.data:
        action_props.custom_file_name = animation.data.indices_file_name
        action_props.custom_max_frame = max([1] + [len(x.values) for x in animation.data.pairs])
    else:
        action_props.custom_file_name = main_header.file_name
        action_props.reference_tables = True

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

    if action_props.custom_file_name and get_anim_file_name(action, action_props) != action_props.custom_file_name:
        action_props.override_file_name = True

    for i in range(len(animation.headers) - 1):
        action_props.header_variants.add()
    for header, header_props in zip(animation.headers, action_props.headers):
        header.action = action  # Used in table class to prop
        from_header_class(header_props, header, action, actor_name, use_custom_name)

    update_header_variant_numbers(action_props)


def from_table_element_class(element_props: "TableElementProps", element: AnimationTableElement):
    if element.header:
        element_props.set_variant(element.header.action, element.header.header_variant)
    else:
        element_props.reference = True
    if isinstance(element.reference, int):
        element_props.header_name = intToHex(element.reference)
        element_props.header_address = intToHex(element.reference)
    else:
        element_props.header_name = element.reference
        element_props.header_address = intToHex(0)
    if element.enum_name:
        element_props.enum_name = element.enum_name


def from_anim_table_class(table_props: "TableProps", table: AnimationTable, clear_table: bool = False):
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


def value_distance(e1: Euler, e2: Euler) -> float:
    result = 0
    for x1, x2 in zip(e1, e2):
        result += abs(x1 - x2)
    return result


def flip_euler(euler: Euler) -> Euler:
    ret = euler.copy()

    ret[0] += math.pi
    ret[2] += math.pi
    ret[1] = -ret[1] + math.pi
    return ret


def naive_flip_diff(a1: float, a2: float) -> float:
    while abs(a1 - a2) > math.pi:
        if a1 < a2:
            a2 -= 2 * math.pi
        else:
            a2 += 2 * math.pi
    return a2


class AnimationBone:
    def __init__(self):
        self.translation: list[Vector] = []
        self.rotation: list[Quaternion] = []

    def read_pairs(self, pairs: list[AnimPair]):
        array: list[int] = []

        max_frame = max(len(pair.values) for pair in pairs)
        for frame in range(max_frame):
            array.append([x.get_frame(frame) for x in pairs])
        return array

    def read_translation(self, pairs: list[AnimPair], scale: float):
        translation_frames = self.read_pairs(pairs)

        for translation_frame in translation_frames:
            self.translation.append([x / scale for x in translation_frame])

    def read_rotation(self, pairs: list[AnimPair]):
        rotation_frames: list[Vector] = self.read_pairs(pairs)

        prev = Euler([0, 0, 0])

        for rotation_frame in rotation_frames:
            e = Euler([sm64_to_radian(x) for x in rotation_frame])
            e[0] = naive_flip_diff(prev[0], e[0])
            e[1] = naive_flip_diff(prev[1], e[1])
            e[2] = naive_flip_diff(prev[2], e[2])

            fe = flip_euler(e)
            fe[0] = naive_flip_diff(prev[0], fe[0])
            fe[1] = naive_flip_diff(prev[1], fe[1])
            fe[2] = naive_flip_diff(prev[2], fe[2])

            de = value_distance(prev, e)
            dfe = value_distance(prev, fe)
            if dfe < de:
                e = fe
            prev = e

            self.rotation.append(e.to_quaternion())


def animation_data_to_blender(
    armature_obj: Object,
    blender_to_sm64_scale: float,
    anim_import: Animation,
    action: Action,
):
    anim_bones = get_anim_pose_bones(armature_obj)

    bone_anim_data: list[AnimationBone] = []
    pairs = anim_import.data.pairs
    for pair_num in range(3, len(pairs), 3):
        bone = AnimationBone()
        if pair_num == 3:
            bone.read_translation(pairs[0:3], blender_to_sm64_scale)
        bone.read_rotation(pairs[pair_num : pair_num + 3])
        bone_anim_data.append(bone)

    is_root = True
    for pose_bone, bone_data in zip(anim_bones, bone_anim_data):
        if is_root:
            for property_index in range(3):
                f_curve = action.fcurves.new(
                    data_path=f'pose.bones["{pose_bone.name}"].location',
                    index=property_index,
                    action_group=pose_bone.name,
                )
                for frame, translation in enumerate(bone_data.translation):
                    f_curve.keyframe_points.insert(frame, translation[property_index])
            is_root = False

        rotation_mode = pose_bone.rotation_mode
        rotation_mode_name = {
            "QUATERNION": "rotation_quaternion",
            "AXIS_ANGLE": "rotation_axis_angle",
        }.get(rotation_mode, "rotation_euler")
        data_path = f'pose.bones["{pose_bone.name}"].{rotation_mode_name}'
        if rotation_mode == "QUATERNION":
            rotations = bone_data.rotation
        elif rotation_mode == "AXIS_ANGLE":
            rotations = [rotation.to_axis_angle() for rotation in bone_data.rotation]
        else:
            rotations = [rotation.to_euler(rotation_mode) for rotation in bone_data.rotation]
        for property_index in range(len(rotations[0])):
            f_curve = action.fcurves.new(
                data_path=data_path,
                index=property_index,
                action_group=pose_bone.name,
            )
            for frame, rotation in enumerate(rotations):
                f_curve.keyframe_points.insert(frame, rotation[property_index])


def animation_import_to_blender(
    armature_obj: Object,
    blender_to_sm64_scale: float,
    anim_import: Animation,
    actor_name: str,
    remove_name_footer: bool = True,
    use_custom_name: bool = True,
):
    action = bpy.data.actions.new("")

    if armature_obj.animation_data is None:
        armature_obj.animation_data_create()

    if anim_import.data:
        animation_data_to_blender(
            armature_obj=armature_obj,
            blender_to_sm64_scale=blender_to_sm64_scale,
            anim_import=anim_import,
            action=action,
        )

    from_anim_class(action.fast64.sm64, action, anim_import, actor_name, remove_name_footer, use_custom_name)

    stashActionInArmature(armature_obj, action)
    armature_obj.animation_data.action = action


def find_decls(
    c_data: str,
    search_text: str,
    file_path: os.PathLike,
    decl_list: list[CArrayDeclaration],
):
    start_index = c_data.find(search_text)
    while start_index != -1:
        decl_index = c_data.find("{", start_index)
        end_index = c_data.find("};", start_index)
        name = c_data[start_index + len(search_text) : decl_index]
        name = name.replace("[]", "").replace("=", "").rstrip().lstrip()
        values = [value.strip() for value in c_data[decl_index + 1 : end_index].split(",")]
        if values[-1] == "":
            values = values[:-1]
        decl_list.append(CArrayDeclaration(name, file_path, values))
        start_index = c_data.find(search_text, end_index)


pattern = re.compile(r'//.*?$|/\*.*?\*/|\'(?:\\.|[^\\\'])*\'|"(?:\\.|[^\\"])*"', re.DOTALL | re.MULTILINE)


def comment_remover(text: str):
    def replacer(match):
        s = match.group(0)
        if s.startswith("/"):
            return " "  # note: a space and not an empty string
        else:
            return s

    return re.sub(pattern, replacer, text)


def import_c_animations(
    path: os.PathLike,
    animation_headers: dict[str, AnimHeader],
    animation_data: dict[tuple[str, str], Animation],
    table: AnimationTable,
):
    path_checks(path)

    header_decls, value_decls, indices_decls, table_decls = [], [], [], []

    if os.path.isfile(path):
        file_paths = [path]
    else:
        file_paths = sorted(
            [
                os.path.join(
                    root,
                    filename,
                )
                for root, _, files in os.walk(path)
                for filename in files
            ]
        )

    for file_path in file_paths:
        print("Reading from: " + file_path)
        with open(file_path, "r", encoding="utf-8", errors="ignore") as file:
            c_data = comment_remover(file.read())

        find_decls(c_data, "static const struct Animation ", file_path, header_decls)
        find_decls(c_data, "static const u16 ", file_path, indices_decls)
        find_decls(c_data, "static const s16 ", file_path, value_decls)
        find_decls(c_data, "const struct Animation *const ", file_path, table_decls)

    if table_decls:
        if len(table_decls) > 1:
            raise ValueError("More than 1 table declaration")
        table.read_c(
            table_decls[0],
            animation_headers,
            animation_data,
            header_decls,
            value_decls,
            indices_decls,
        )
        return
    for header_decl in header_decls:
        AnimHeader().read_c(
            header_decl,
            value_decls,
            indices_decls,
            animation_headers,
            animation_data,
        )


def import_binary_animations(
    data_reader: RomReader,
    import_type: str,
    animation_headers: dict[str, AnimHeader],
    animation_data: dict[tuple[str, str], Animation],
    table: AnimationTable,
    table_index: int | None = None,
    assumed_bone_count: int | None = None,
    table_size: int | None = None,
):
    if import_type == "Table":
        table.read_binary(data_reader, animation_headers, animation_data, table_index, assumed_bone_count, table_size)
    elif import_type == "DMA":
        table.read_dma_binary(data_reader, animation_headers, animation_data, table_index, assumed_bone_count)
    elif import_type == "Animation":
        AnimHeader.read_binary(
            data_reader,
            animation_headers,
            animation_data,
            False,
            assumed_bone_count,
            table_size,
        )
    else:
        raise PluginError("Unimplemented binary import type.")


def import_insertable_binary_animations(
    insertable_data_reader: RomReader,
    animation_headers: dict[str, AnimHeader],
    animation_data: dict[tuple[str, str], Animation],
    table: AnimationTable,
    table_index: int | None = None,
    assumed_bone_count: int | None = None,
    table_size: int | None = None,
):
    data_type_num = insertable_data_reader.read_value(4, signed=False)
    if data_type_num not in insertableBinaryTypes.values():
        raise PluginError(f"Unknown data type: {intToHex(data_type_num)}")
    data_size = insertable_data_reader.read_value(4, signed=False)
    start_address = insertable_data_reader.read_value(4, signed=False)

    pointer_count = insertable_data_reader.read_value(4, signed=False)
    pointer_offsets = []
    for _ in range(pointer_count):
        pointer_offsets.append(insertable_data_reader.read_value(4, signed=False))

    actual_start = insertable_data_reader.address + start_address
    data_reader = insertable_data_reader.branch(
        0,
        insertable_data_reader.data[actual_start : actual_start + data_size],
    )
    data_reader.insertable_ptrs = pointer_offsets

    data_type = next(key for key, value in insertableBinaryTypes.items() if value == data_type_num)
    if data_type == "Animation":
        AnimHeader.read_binary(
            data_reader,
            animation_headers,
            animation_data,
            False,
            assumed_bone_count,
        )
    elif data_type == "Animation Table":
        table.read_binary(data_reader, animation_headers, animation_data, table_index, table_size, assumed_bone_count)
    elif data_type == "Animation DMA Table":
        table.read_dma_binary(data_reader, animation_headers, animation_data, table_index, assumed_bone_count)
    else:
        raise PluginError(f'Wrong animation data type "{data_type}".')


def import_animations(context: Context):
    animation_operator_checks(context, False)

    scene = context.scene
    sm64_props: SM64_Properties = scene.fast64.sm64
    animation_props: AnimProps = get_animation_props(context)
    import_props: ImportProps = animation_props.importing
    table_props: TableProps = animation_props.table
    armature_obj: Object = context.selected_objects[0]

    animation_data: dict[tuple[str, str], Animation] = {}
    animation_headers: dict[str, AnimHeader] = {}
    table = AnimationTable()

    if import_props.preset == "Custom":
        is_segmented_address = import_props.is_segmented_address
        level = import_props.level
        address = import_props.address
        table_size = import_props.table_size
        binary_import_type = import_props.binary_import_type
        c_path = abspath(import_props.path)
    else:
        preset = ACTOR_PRESET_INFO[import_props.preset]
        is_segmented_address = True
        level = preset.level
        address = preset.animation_table
        table_size = preset.table_size
        binary_import_type = "DMA" if preset.dma_animation else "Table"
        c_path = os.path.join(import_props.decomp_path, preset.decomp_path)

    rom_data, segment_data = None, None
    if import_props.import_type == "Binary" or import_props.read_from_rom:
        rom_path = abspath(import_props.rom if import_props.rom else sm64_props.import_rom)
        import_rom_checks(rom_path)
        with open(rom_path, "rb") as rom_file:
            rom_data = rom_file.read()
            if import_props.read_from_rom or binary_import_type != "DMA":
                segment_data = parseLevelAtPointer(rom_file, level_pointers[level]).segmentData
    anim_bones = get_anim_pose_bones(armature_obj)
    assumed_bone_count = len(anim_bones) if import_props.assume_bone_count else None
    table_index = None
    if binary_import_type == "Table":
        table_index = import_props.table_index

    if import_props.import_type == "Binary":
        if is_segmented_address:
            address = decodeSegmentedAddr(address.to_bytes(4, "big"), segment_data)
        if binary_import_type == "DMA":
            table_index = import_props.dma_table_index
        import_binary_animations(
            RomReader(rom_data, address, rom_data=rom_data, segment_data=segment_data),
            binary_import_type,
            animation_headers,
            animation_data,
            table,
            table_index,
            assumed_bone_count,
            table_size,
        )
    elif import_props.import_type == "Insertable Binary":
        path = abspath(import_props.path)
        filepath_checks(path)
        with open(path, "rb") as insertable_file:
            import_insertable_binary_animations(
                RomReader(insertable_file.read(), 0, None, rom_data, segment_data),
                animation_headers,
                animation_data,
                table,
                import_props.table_index if binary_import_type == "Table" else None,
                assumed_bone_count,
            )
    elif import_props.import_type == "C":
        path_checks(c_path)
        import_c_animations(c_path, animation_headers, animation_data, table)

    if not table.elements:
        table.elements = [AnimationTableElement(header=header) for header in animation_headers.values()]
    for animation in animation_data.values():
        animation_import_to_blender(
            context.selected_objects[0],
            sm64_props.blender_to_sm64_scale,
            animation,
            animation_props.actor_name,
            import_props.remove_name_footer,
            import_props.use_custom_name,
        )
    from_anim_table_class(table_props, table, import_props.clear_table)


def import_all_mario_animations(context: Context):
    animation_operator_checks(context, False)
    scene = context.scene
    sm64_props: SM64_Properties = scene.fast64.sm64

    animation_props: AnimProps = get_animation_props(context)
    import_props: ImportProps = animation_props.importing

    animations: dict[str, Animation] = {}
    table: AnimationTable = AnimationTable()

    mario_dma_table_address = 0x4EC000

    if import_props.import_type == "Binary":
        rom_path = abspath(import_props.rom if import_props.rom else sm64_props.import_rom)
        import_rom_checks(rom_path)
        with open(rom_path, "rb") as rom:
            rom_data = rom.read()
            for entrie_str, name, _ in marioAnimationNames[1:]:
                entrie_num = int(entrie_str)
                dma_table = DMATable()
                dma_table.read_binary(rom_data, mario_dma_table_address)
                if entrie_num < 0 or entrie_num >= len(dma_table.entries):
                    raise PluginError(
                        f"Index {entrie_num} outside of defined table ({len(dma_table.entries)} entries)."
                    )

                entrie: DMATableEntrie = dma_table.entries[entrie_num]
                header = import_binary_header(rom_data, entrie.address, True, animations, None)
                table.elements.append(header)
                header.reference = toAlnum(name)
                header.data.action_name = name
    else:
        raise PluginError("Unimplemented import type.")

    for _, data in animations.items():
        animation_import_to_blender(armature_obj, sm64_props.blender_to_sm64_scale, data)
    from_anim_table_class(sm64_props.animation.table, table)
