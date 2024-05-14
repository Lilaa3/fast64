import math
import os

import bpy
from bpy.types import Object, Action, PoseBone, Context
from bpy.path import abspath
import mathutils
from mathutils import Euler, Quaternion, Vector, Matrix

from ...utility import (
    PluginError,
    bytesToHex,
    encodeSegmentedAddr,
    decodeSegmentedAddr,
    get64bitAlignedAddr,
    intToHex,
    writeIfNotFound,
    radians_to_s16,
    applyBasicTweaks,
    toAlnum,
    writeInsertableFile,
)
from ...utility_anim import stashActionInArmature
from ..sm64_constants import (
    BEHAVIOR_COMMANDS,
    BEHAVIOR_EXITS,
    insertableBinaryTypes,
    defaultExtendSegment4,
    level_pointers,
)
from ..classes import BinaryExporter, RomReader
from ..sm64_level_parser import parseLevelAtPointer
from ..sm64_rom_tweaks import ExtendBank0x04

from .classes import (
    Animation,
    AnimationHeader,
    AnimationData,
    AnimationPair,
    AnimationTable,
    AnimationTableElement,
)
from .utility import (
    get_anim_pose_bones,
    animation_operator_checks,
    get_animation_props,
    get_element_header,
    get_element_action,
    get_frame_range,
    get_max_frame,
    get_anim_file_name,
    get_anim_name,
    get_anim_enum,
    get_int_flags,
    get_anim_table_name,
)
from .constants import HEADER_SIZE

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .properties import (
        AnimProps,
        TableProps,
        SM64_ActionProps,
        HeaderProps,
        TableElementProps,
    )
    from ..settings.properties import SM64_Properties


def get_entire_fcurve_data(action: Action, bone: PoseBone, path: str, max_frame: int, max_index: int = 0) -> list:
    data_path = f'pose.bones["{bpy.utils.escape_identifier(bone.name)}"].{path}'
    values = [None] * max_index
    for fcurve in action.fcurves:
        if fcurve.data_path != data_path:
            continue
        values[fcurve.array_index] = [fcurve.evaluate(frame) for frame in range(max_frame)]

    for i, value in enumerate(values):
        if not value:
            values[i] = [getattr(bone, path)[i]] * max_frame
    return values


def get_trans_data(action: Action, bone: PoseBone, max_frame: int, blender_to_sm64_scale: float) -> tuple:
    translation_pairs = (
        AnimationPair(),
        AnimationPair(),
        AnimationPair(),
    )
    for x, y, z in zip(*get_entire_fcurve_data(action, bone, "location", max_frame, 3)):
        translation_pairs[0].values.append(int(x * blender_to_sm64_scale))
        translation_pairs[1].values.append(int(y * blender_to_sm64_scale))
        translation_pairs[2].values.append(int(z * blender_to_sm64_scale))
    return translation_pairs


def get_rotation_data(action: Action, bone: PoseBone, max_frame: int):
    rotation_pairs = (
        AnimationPair(),
        AnimationPair(),
        AnimationPair(),
    )
    rotation = (rotation_pairs[0].values, rotation_pairs[1].values, rotation_pairs[2].values)
    if bone.rotation_mode == "QUATERNION":
        for w, x, y, z in zip(*get_entire_fcurve_data(action, bone, "rotation_quaternion", max_frame, 4)):
            euler = Quaternion((w, x, y, z)).to_euler()
            rotation[0].append(radians_to_s16(euler.x))
            rotation[1].append(radians_to_s16(euler.y))
            rotation[2].append(radians_to_s16(euler.z))
    elif bone.rotation_mode == "AXIS_ANGLE":
        for x, y, z, w in zip(*get_entire_fcurve_data(action, bone, "rotation_axis_angle", max_frame, 4)):
            euler = mathutils.AxisAngle((x, y, z), w).to_euler()
            rotation[0].append(radians_to_s16(euler.x))
            rotation[1].append(radians_to_s16(euler.y))
            rotation[2].append(radians_to_s16(euler.z))
    else:
        for x, y, z in zip(*get_entire_fcurve_data(action, bone, "rotation_euler", max_frame, 3)):
            euler = Euler((x, y, z), bone.rotation_mode)
            rotation[0].append(radians_to_s16(euler.x))
            rotation[1].append(radians_to_s16(euler.y))
            rotation[2].append(radians_to_s16(euler.z))
    return rotation_pairs


def get_animation_pairs(
    sm64_scale: float, max_frame: int, action: Action, armature_obj: Object, quick_read: bool = True
) -> tuple[list[int], list[int]]:
    print(f"Reading animation pair values from action {action.name}.")
    anim_bones = get_anim_pose_bones(armature_obj)
    if len(anim_bones) < 1:
        raise PluginError(f'No animation bones in armature "{armature_obj.name}"')

    pairs = []
    if quick_read:
        root_bone = anim_bones[0]
        pairs.extend(get_trans_data(action, root_bone, max_frame, sm64_scale))

        for i, pose_bone in enumerate(anim_bones):
            pairs.extend(get_rotation_data(action, pose_bone, max_frame))
    else:
        pre_export_frame = bpy.context.scene.frame_current
        pre_export_action = armature_obj.animation_data.action
        armature_obj.animation_data.action = action

        pairs = [
            AnimationPair(),
            AnimationPair(),
            AnimationPair(),
        ]
        rotation_pairs: list[tuple[AnimationPair]] = []
        for _ in anim_bones:
            rotation = (
                AnimationPair(),
                AnimationPair(),
                AnimationPair(),
            )
            rotation_pairs.append(rotation)
            pairs.extend(rotation)

        scale: Vector = armature_obj.matrix_world.to_scale() * sm64_scale
        for frame in range(max_frame):
            bpy.context.scene.frame_set(frame)
            for i, pose_bone in enumerate(anim_bones):
                matrix = (
                    armature_obj.convert_space(
                        pose_bone=pose_bone,
                        matrix=pose_bone.matrix,
                        from_space="WORLD",
                        to_space="LOCAL",
                    )
                )
                if i == 0:  # Only first bone has translation.
                    translation: Vector = matrix.to_translation() * scale
                    for j, pair in enumerate(pairs[:3]):
                        pair.values.append(int(translation[j]))
                rot = matrix.to_euler()
                for j, pair in enumerate(rotation_pairs[i]):
                    pair.values.append(radians_to_s16(rot[j]))

        armature_obj.animation_data.action = pre_export_action
        bpy.context.scene.frame_current = pre_export_frame

    for pair in pairs:
        pair.clean_frames()
    return pairs


def to_header_class(
    header_props: "HeaderProps",
    bone_count: int,
    data: AnimationData,
    action: Action,
    use_int_flags: bool = False,
    values_reference: int | str | None = None,
    indice_reference: int | str | None = None,
    table_index: int | None = None,
    actor_name: str | None = "mario",
    generate_enums: bool = False,
    file_name: str | None = "anim_00.inc.c",
):
    header = AnimationHeader()
    header.reference = get_anim_name(actor_name, action, header_props)
    if generate_enums:
        header.enum_name = get_anim_enum(actor_name, action, header_props)

    if header_props.set_custom_flags:
        if use_int_flags:
            header.flags = int(header_props.custom_int_flags, 0)
        else:
            header.flags = header_props.custom_flags
    else:
        header.flags = get_int_flags(header_props)

    header.trans_divisor = header_props.trans_divisor
    header.start_frame, header.loop_start, header.loop_end = get_frame_range(action, header_props)
    header.values_reference = values_reference
    header.indice_reference = indice_reference
    header.bone_count = bone_count
    header.table_index = header_props.table_index if table_index is None else table_index
    header.file_name = file_name
    header.data = data
    return header


def to_data_class(
    action: Action,
    armature_obj: Object,
    blender_to_sm64_scale: float,
    quick_read: bool,
    file_name: str = "anim_00.inc.c",
):
    data = AnimationData()
    pairs = get_animation_pairs(
        blender_to_sm64_scale,
        get_max_frame(action, action.fast64.sm64),
        action,
        armature_obj,
        quick_read,
    )
    data_name: str = toAlnum(f"anim_{action.name}")
    values_reference = f"{data_name}_values"
    indice_reference = f"{data_name}_indices"
    data.pairs = pairs
    data.values_reference, data.indice_reference = values_reference, indice_reference
    data.values_file_name, data.indices_file_name = file_name, file_name
    return data


def to_animation_class(
    action_props: "SM64_ActionProps",
    action: Action,
    armature_obj: Object,
    blender_to_sm64_scale: float,
    quick_read: bool,
    can_use_references: bool,
    use_int_flags: bool,
    actor_name: str = "mario",
    generate_enums: bool = False,
    use_addresses_for_references: bool = False,
):
    animation = Animation()
    animation.file_name = get_anim_file_name(action, action_props)

    if can_use_references and action_props.reference_tables:
        if use_addresses_for_references:
            values_reference, indice_reference = int(action_props.values_address, 0), int(
                action_props.indices_address, 0
            )
        else:
            values_reference, indice_reference = action_props.values_table, action_props.indices_table
    else:
        animation.data = to_data_class(action, armature_obj, blender_to_sm64_scale, quick_read, animation.file_name)
        values_reference = animation.data.values_reference
        indice_reference = animation.data.indice_reference
    bone_count = len(get_anim_pose_bones(armature_obj))
    for header_props in action_props.headers:
        animation.headers.append(
            to_header_class(
                header_props,
                bone_count,
                animation.data,
                action,
                use_int_flags,
                values_reference,
                indice_reference,
                None,
                actor_name,
                generate_enums,
                animation.file_name,
            )
        )

    return animation


def get_enum_list_name(actor_name: str):
    return f"{actor_name}Anims".title()


def to_table_class(
    table_props: "TableProps",
    armature_obj: Object,
    blender_to_sm64_scale: float,
    quick_read: bool,
    use_int_flags: bool = False,
    can_reference: bool = True,
    actor_name: str = "mario",
    generate_enums: bool = False,
    use_addresses_for_references: bool = False,
) -> AnimationTable:
    table = AnimationTable()
    table.reference = get_anim_table_name(table_props, actor_name)
    table.enum_list_reference = get_enum_list_name(actor_name)
    table.file_name = "table_animations.inc.c"
    table.values_reference = toAlnum(f"anim_{actor_name}_values")

    bone_count = len(get_anim_pose_bones(armature_obj))

    existing_data: dict[Action, AnimationData] = {}
    existing_headers: dict[HeaderProps, AnimationHeader] = {}

    element_props: TableElementProps
    for i, element_props in enumerate(table_props.elements):
        reference = AnimationTableElement()
        if can_reference and element_props.reference:
            header_reference = (
                int(
                    element_props.header_address,
                    0,
                )
                if use_addresses_for_references
                else element_props.header_name
            )
            if not header_reference:
                raise ValueError(f"Header in table element {i} is not set.")
            reference.reference = header_reference
            if generate_enums:
                if not element_props.enum_name:
                    raise ValueError(f"Enum Name in table element {i} is not set.")
                reference.enum_name = element_props.enum_name
            table.elements.append(reference)
            continue

        header: HeaderProps = get_element_header(element_props, can_reference)
        if not header:
            raise ValueError(f"Header in table element {i} is not set.")
        action: Action = get_element_action(element_props, can_reference)
        if not action:
            raise ValueError(f"Action in table element {i} is not set.")

        action_props: SM64_ActionProps = action.fast64.sm64
        if can_reference and action_props.reference_tables:
            if use_addresses_for_references:
                values_reference, indice_reference = (
                    int(action_props.values_address, 0),
                    int(action_props.indices_address, 0),
                )
            else:
                values_reference, indice_reference = action_props.values_table, action_props.indices_table
            data = None
        else:
            if not action in existing_data:
                existing_data[action] = to_data_class(action, armature_obj, blender_to_sm64_scale, quick_read)
            data = existing_data[action]
            values_reference, indice_reference = data.values_reference, data.indice_reference

        reference.header = existing_headers.get(
            header,
            to_header_class(
                header,
                bone_count,
                data,
                action,
                use_int_flags,
                values_reference,
                indice_reference,
                i,
                actor_name,
                generate_enums,
                get_anim_file_name(action, action_props),
            ),
        )
        reference.reference = reference.header.reference
        reference.enum_name = reference.header.enum_name
        table.elements.append(reference)

    return table


def get_table_actions(table_props: "TableProps", can_reference: bool) -> list[Action]:
    actions = []
    for element_props in table_props.elements:
        action = get_element_action(element_props, can_reference)
        if action and action not in actions:
            actions.append(action)
    return actions


def update_includes(
    level_name: str,
    group_name: str,
    dir_name: str,
    directory: os.PathLike,
    header_type: str,
    update_table: bool,
):
    if header_type == "Actor":
        data_path = os.path.join(directory, f"{group_name}.c")
        header_path = os.path.join(directory, f"{group_name}.h")
        include_start = f'#include "{dir_name}/'
    elif header_type == "Level":
        data_path = os.path.join(directory, "leveldata.c")
        header_path = os.path.join(directory, "header.h")
        include_start = f'#include "{dir_name}/{level_name}/anims/'
    print(f"Updating includes at {data_path} and {header_path}.")
    writeIfNotFound(data_path, f'{include_start}/anims/data.inc.c"\n', "")
    if update_table:
        writeIfNotFound(data_path, f'{include_start}/anims/table.inc.c"\n', "")
        writeIfNotFound(header_path, f'{include_start}/anim_header.h"\n', "#endif")


def write_anim_header(
    anim_header: os.PathLike,
    table_name: str,
    generate_enums: bool,
):
    print("Writing animation header")
    with open(anim_header, "w", encoding="utf-8") as file:
        if generate_enums:
            file.write('#include "anims/table_enum.h"\n')
        file.write(f"extern const struct Animation *const {table_name}[];\n")


def update_enum_file(
    enum_list: os.PathLike,
    enum_list_name: str,
    enum_names: list[str],
    override_files: bool,
):
    if override_files or not os.path.exists(enum_list):
        text = ""
    else:
        with open(enum_list, "r") as file:
            text = file.read()

    end_enum = f"{enum_list_name.upper()}_END"

    enum_list_index = text.find(enum_list_name)
    if enum_list_index == -1:  # If there is no enum list, add one and find again
        text += f"enum {enum_list_name} {{\n"
        text += f"\t{end_enum}\n"
        text += "};\n"
        enum_list_index = text.find(enum_list_name)

    for enum_name in enum_names:
        if not enum_name:
            continue
        if text.find(enum_name, enum_list_index) == -1:
            enum_list_end = text.find(end_enum, enum_list_index)
            if enum_list_end == -1:
                enum_list_end = text.find("}", enum_list_index)
            text = text[:enum_list_end] + f"{enum_name},\n\t" + text[enum_list_end:]

    with open(enum_list, "w", newline="\n") as file:
        file.write(text)


def update_table_file(
    table: os.PathLike,
    enum_and_header_names: list[tuple[str, str]],
    table_name: str,
    generate_enums: bool,
    enum_list: os.PathLike,
    enum_list_name: str,
):
    if not os.path.exists(table):
        text = ""
    else:
        with open(table, "r") as file:
            text = file.read()

    if generate_enums:
        update_enum_file(enum_list, enum_list_name, [tup[0] for tup in enum_and_header_names], False)

    # Table
    table_index = text.find(table_name)
    if table_index == -1:  # If there is no table, add one and find again
        text += f"const struct Animation *const {table_name}[] = {{\n"
        text += "\tNULL,\n"
        text += "}};\n"
        table_index = text.find(table_name)

    for _, header_name in enum_and_header_names:
        header_reference = f"&{header_name}"
        if text.find(header_reference, table_index) != -1:
            continue

        table_end = text.find("NULL", table_index)
        if table_end == -1:
            table_end = text.find("}", table_index)

        text = text[:table_end] + f"{header_reference},\n\t" + text[table_end:]

    with open(table, "w", newline="\n") as file:
        file.write(text)


def update_data_file(data_file_path: os.PathLike, anim_file_names: list, override_files: bool = False):
    print(f"Updating animation data file at {data_file_path}")
    if not os.path.exists(data_file_path) or override_files:
        with open(data_file_path, "w", newline="\n"):
            pass  # Leave empty

    for anim_file_name in anim_file_names:
        writeIfNotFound(data_file_path, f'#include "{anim_file_name}"\n', "")


def update_behaviour_binary(
    binary_exporter: BinaryExporter, address: int, table_address: bytes, beginning_animation: int
):
    load_set = False
    animate_set = False
    exited = False
    while not exited:
        command_index = int.from_bytes(binary_exporter.read(1, address), "big")
        name, size = BEHAVIOR_COMMANDS[command_index]
        if name in BEHAVIOR_EXITS:
            exited = True
        if name == "LOAD_ANIMATIONS":
            binary_exporter.seek(address + 4)
            print(
                f"Found LOAD_ANIMATIONS at {intToHex(address)}, "
                f"replacing {bytesToHex(binary_exporter.read(4))} with {bytesToHex(table_address)}"
            )
            binary_exporter.write(table_address)
            load_set = True
        elif name == "ANIMATE":
            binary_exporter.seek(address + 1)
            print(
                f"Found ANIMATE at {hex(address)}, "
                f"replacing {bytesToHex(binary_exporter.read(1))} with {beginning_animation}"
            )
            binary_exporter.write(beginning_animation.to_bytes(1, "big"))
            animate_set = True
        address += 4 * size
    if exited:
        if not load_set:
            raise IndexError("Could not find LOAD_ANIMATIONS command")
        if not animate_set:
            print("Could not find ANIMATE command")


def export_animation_table_binary(
    binary_exporter: BinaryExporter,
    table_props: "TableProps",
    table: AnimationTable,
    is_binary_dma: bool,
    level_option: str,
    extend_bank_4: bool,
):
    if is_binary_dma:
        data = table.to_binary_dma()
        binary_exporter.write_to_range(
            int(table_props.dma_address, 0),
            int(table_props.dma_end_address, 0),
            data,
        )
        return

    level_parsed = parseLevelAtPointer(binary_exporter.rom_file_output, level_pointers[level_option])
    segment_data = level_parsed.segmentData
    if extend_bank_4:
        ExtendBank0x04(binary_exporter.rom_file_output, segment_data, defaultExtendSegment4)

    table_address = get64bitAlignedAddr(int(table_props.address, 0))
    table_end_address = int(table_props.end_address, 0)

    if table_props.write_data_seperately:
        data_address = get64bitAlignedAddr(int(table_props.data_address, 0))
        data_end_address = int(table_props.data_end_address, 0)
        table_data, data = table.to_combined_binary(table_address, data_address, segment_data)[:2]
        binary_exporter.write_to_range(
            table_address,
            table_end_address,
            table_data,
        )
        binary_exporter.write_to_range(
            data_address,
            data_end_address,
            data,
        )
    else:
        table_data, data = table.to_combined_binary(table_address, -1, segment_data)[:2]
        binary_exporter.write_to_range(
            table_address,
            table_end_address,
            table_data + data,
        )
    if table_props.update_behavior:
        update_behaviour_binary(
            binary_exporter,
            decodeSegmentedAddr(table_props.behavior_address.to_bytes(4, "big"), segment_data),
            encodeSegmentedAddr(table_address, segment_data),
            int(table_props.begining_animation, 0),
        )


def export_animation_table_insertable(
    animation_props: "AnimProps",
    table_props: "TableProps",
    table: AnimationTable,
    is_binary_dma: bool,
):
    path = abspath(os.path.join(animation_props.directory_path, table_props.insertable_file_name))
    if is_binary_dma:
        data = table.to_binary_dma()
        writeInsertableFile(path, insertableBinaryTypes["Animation DMA Table"], [], 0, data)
    else:
        table_data, data, ptrs = table.to_combined_binary()
        writeInsertableFile(path, insertableBinaryTypes["Animation Table"], ptrs, 0, table_data + data)


def create_and_get_paths(animation_props: "AnimProps", decomp: os.PathLike):
    paths = animation_props.get_c_paths(decomp)
    for path in paths:
        if path and not os.path.exists(path):
            os.mkdir(path)
    return paths


def export_animation_table_c(
    animation_props: "AnimProps",
    table_props: "TableProps",
    table: AnimationTable,
    decomp: os.PathLike,
):
    header_type = animation_props.header_type
    if header_type != "Custom":
        applyBasicTweaks(decomp)
    anim_directory, geo_directory, header_directory = create_and_get_paths(animation_props, decomp)

    print("Creating all C data")
    if table_props.export_seperately or animation_props.is_c_dma:
        files_data = table.data_and_headers_to_c(animation_props.is_c_dma)
        print("Saving all generated data files")
        for file_name, file_data in files_data.items():
            with open(os.path.join(anim_directory, file_name), "w", encoding="utf-8") as file:
                file.write(file_data)
            print(file_name)
        print("All files exported")
        if not animation_props.is_c_dma:
            update_data_file(
                os.path.join(anim_directory, "data.inc.c"),
                files_data.keys(),
                table_props.override_files,
            )
    else:
        result = table.data_and_headers_to_c_combined()
        print("Saving generated data file")
        with open(os.path.join(anim_directory, "data.inc.c"), "w", encoding="utf-8") as file:
            file.write(result)
        print("File exported")
    if animation_props.is_c_dma:
        return

    header_path = os.path.join(geo_directory, "anim_header.h")
    write_anim_header(header_path, table.reference, table_props.generate_enums)
    if table_props.override_files:
        with open(os.path.join(anim_directory, "table.inc.c"), "w", encoding="utf-8") as file:
            file.write(table.table_to_c())
        if table_props.generate_enums:
            table_enum_path = os.path.join(anim_directory, "table_enum.h")
            with open(table_enum_path, "w", encoding="utf-8") as file:
                file.write(table.enum_list_to_c())
    else:
        update_table_file(
            os.path.join(anim_directory, "table.inc.c"),
            table.enum_and_header_names,
            table.reference,
            table_props.generate_enums,
            os.path.join(anim_directory, "table_enum.h"),
            table.enum_list_reference,
        )

    if header_type != "Custom":
        update_includes(
            animation_props.level_name,
            animation_props.group_name,
            toAlnum(animation_props.actor_name),
            header_directory,
            header_type,
            True,
        )


def export_animation_binary(
    binary_exporter: BinaryExporter,
    animation: Animation,
    action_props: "SM64_ActionProps",
    table_props: "TableProps",
    animation_props: "AnimProps",
    bone_count: int,
    level_option: str,
    extend_bank_4: bool,
):
    if animation_props.is_binary_dma:
        dma_address = int(table_props.dma_address, 0)
        print("Reading DMA table")
        table = AnimationTable().read_dma_binary(
            RomReader(open(binary_exporter.export_rom, "rb").read(), dma_address),
            {},
            {},
            None,
            bone_count if animation_props.assume_bone_count else None,
        )
        empty_data = AnimationData()
        for header in animation.headers:
            while header.table_index >= len(table.elements):
                table.elements.append(table.elements[-1])
            table.elements[header.table_index] = AnimationTableElement(header=AnimationHeader(data=empty_data))
        print("Converting to binary data")
        data = table.to_binary_dma()
        print("Writing to ROM")
        binary_exporter.write_to_range(
            dma_address,
            int(table_props.dma_end_address, 0),
            data,
        )
        return
    level_parsed = parseLevelAtPointer(binary_exporter.rom_file_output, level_pointers[level_option])
    segment_data = level_parsed.segmentData
    if extend_bank_4:
        ExtendBank0x04(binary_exporter.rom_file_output, segment_data, defaultExtendSegment4)

    animation_address = get64bitAlignedAddr(int(action_props.start_address, 0))
    animation_end_address = int(action_props.end_address, 0)

    data = animation.to_binary(animation_address, segment_data)[0]
    binary_exporter.write_to_range(
        animation_address,
        animation_end_address,
        data,
    )
    table_address = get64bitAlignedAddr(int(table_props.address, 0))
    if animation_props.update_table:
        for i, header in enumerate(animation.headers):
            element_address = table_address + (4 * header.table_index)
            binary_exporter.seek(element_address)
            binary_exporter.write(encodeSegmentedAddr(animation_address + (i * HEADER_SIZE), segment_data))
    if table_props.update_behavior:
        update_behaviour_binary(
            binary_exporter,
            decodeSegmentedAddr(table_props.behavior_address.to_bytes(4, "big"), segment_data),
            encodeSegmentedAddr(table_address, segment_data),
            int(table_props.begining_animation, 0),
        )


def export_animation_insertable(animation: Animation, animation_props: "AnimProps", anim_file_name: str):
    data, ptrs = animation.to_binary(animation_props.is_binary_dma)
    path = abspath(os.path.join(animation_props.insertable_directory_path, anim_file_name))
    writeInsertableFile(path, insertableBinaryTypes["Animation"], ptrs, 0, data)


def export_animation_c(
    animation: Animation,
    animation_props: "AnimProps",
    table_props: "TableProps",
    decomp: os.PathLike,
    anim_file_name: str,
    actor_name: str,
):
    header_type = animation_props.header_type
    if header_type != "Custom":
        applyBasicTweaks(decomp)

    anim_directory, geo_directory, header_directory = create_and_get_paths(animation_props, decomp)
    anim_path = os.path.join(anim_directory, anim_file_name)
    with open(anim_path, "w", encoding="utf-8") as file:
        file.write(animation.to_c(animation_props.is_c_dma))
    if animation_props.is_c_dma:
        return
    table_name = get_anim_table_name(table_props, actor_name)
    enum_list_name = get_enum_list_name(actor_name)

    if animation_props.update_table:
        write_anim_header(
            os.path.join(geo_directory, "anim_header.h"),
            table_name,
            table_props.generate_enums,
        )
        update_table_file(
            os.path.join(anim_directory, "table.inc.c"),
            animation.enum_and_header_names,
            table_name,
            table_props.generate_enums,
            os.path.join(anim_directory, "table_enum.h"),
            enum_list_name,
        )
    update_data_file(os.path.join(anim_directory, "data.inc.c"), [anim_file_name])
    if header_type != "Custom":
        update_includes(
            animation_props.level_name,
            animation_props.group_name,
            toAlnum(actor_name),
            header_directory,
            header_type,
            animation_props.update_table,
        )


def export_animation(context: Context):
    animation_operator_checks(context)

    scene = context.scene
    sm64_props: SM64_Properties = scene.fast64.sm64
    animation_props: AnimProps = get_animation_props(context)
    table_props: TableProps = animation_props.table
    armature_obj: Object = context.selected_objects[0]

    action = animation_props.selected_action
    action_props: SM64_ActionProps = action.fast64.sm64
    stashActionInArmature(armature_obj, action)
    bone_count = len(get_anim_pose_bones(armature_obj))

    actor_name = animation_props.actor_name
    animation: Animation = to_animation_class(
        action_props,
        action,
        armature_obj,
        sm64_props.blender_to_sm64_scale,
        animation_props.quick_read,
        sm64_props.binary_export or animation_props.header_type == "DMA",
        not sm64_props.binary_export or not animation_props.is_binary_dma,
        actor_name,
        not sm64_props.binary_export and table_props.generate_enums,
        sm64_props.binary_export,
    )
    anim_file_name = get_anim_file_name(action, action_props)
    if sm64_props.export_type == "C":
        export_animation_c(
            animation,
            animation_props,
            table_props,
            sm64_props.decomp_path,
            anim_file_name,
            actor_name,
        )
    elif sm64_props.export_type == "Insertable Binary":
        export_animation_insertable(animation, animation_props, anim_file_name)
    elif sm64_props.export_type == "Binary":
        with BinaryExporter(abspath(sm64_props.export_rom), abspath(sm64_props.output_rom)) as binary_exporter:
            export_animation_binary(
                binary_exporter,
                animation,
                action_props,
                table_props,
                animation_props,
                bone_count,
                animation_props.binary_level,
                sm64_props.extend_bank_4,
            )
    else:
        raise NotImplementedError(f"Export type {sm64_props.export_type} is not implemented")


def export_animation_table(context: Context):
    bpy.ops.object.mode_set(mode="OBJECT")
    animation_operator_checks(context)

    scene = context.scene
    sm64_props: SM64_Properties = scene.fast64.sm64
    animation_props: AnimProps = get_animation_props(context)
    table_props: TableProps = animation_props.table
    armature_obj: Object = context.selected_objects[0]

    is_binary_dma = sm64_props.binary_export and animation_props.is_binary_dma
    is_dma = is_binary_dma or animation_props.is_c_dma

    print("Stashing all actions in table")
    for action in get_table_actions(table_props, not is_dma):
        stashActionInArmature(armature_obj, action)

    print("Reading table data from fast64")
    table = to_table_class(
        table_props,
        armature_obj,
        sm64_props.blender_to_sm64_scale,
        animation_props.quick_read,
        is_dma or sm64_props.binary_export,
        not is_dma,
        animation_props.actor_name,
        not is_dma and not sm64_props.binary_export and table_props.generate_enums,
        sm64_props.binary_export,
    )

    print("Exporting table data")
    if sm64_props.export_type == "C":
        export_animation_table_c(animation_props, table_props, table, abspath(sm64_props.decomp_path))
    elif sm64_props.export_type == "Insertable Binary":
        export_animation_table_insertable(animation_props, table_props, table, is_binary_dma)
    elif sm64_props.export_type == "Binary":
        with BinaryExporter(abspath(sm64_props.export_rom), abspath(sm64_props.output_rom)) as binary_exporter:
            export_animation_table_binary(
                binary_exporter,
                table_props,
                table,
                is_binary_dma,
                animation_props.binary_level,
                sm64_props.extend_bank_4,
            )
    else:
        raise NotImplementedError(f"Export type {sm64_props.export_type} is not implemented")
