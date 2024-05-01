import os
import shutil

import bpy
from bpy.types import Object, Action, PoseBone, Context
from bpy.path import abspath
import mathutils

from ...utility import (
    PluginError,
    intToHex,
    tempName,
    writeIfNotFound,
    radians_to_s16,
    applyBasicTweaks,
    toAlnum,
    writeInsertableFile,
)
from ...utility_anim import stashActionInArmature
from ..sm64_constants import insertableBinaryTypes
from ..sm64_utility import export_rom_checks

from .classes import SM64_Anim, SM64_AnimPair, SM64_AnimTable
from .utility import get_anim_pose_bones, animation_operator_checks

from typing import TYPE_CHECKING, BinaryIO

if TYPE_CHECKING:
    from .properties import SM64_AnimProps, SM64_AnimTableProps, SM64_ActionProps
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
        SM64_AnimPair(),
        SM64_AnimPair(),
        SM64_AnimPair(),
    )
    for x, y, z in zip(*get_entire_fcurve_data(action, bone, "location", max_frame, 3)):
        translation_pairs[0].values.append(int(x * blender_to_sm64_scale))
        translation_pairs[1].values.append(int(y * blender_to_sm64_scale))
        translation_pairs[2].values.append(int(z * blender_to_sm64_scale))
    return translation_pairs


def get_rotation_data(action: Action, bone: PoseBone, max_frame: int):
    rotation_pairs = (
        SM64_AnimPair(),
        SM64_AnimPair(),
        SM64_AnimPair(),
    )
    rotation = (rotation_pairs[0].values, rotation_pairs[1].values, rotation_pairs[2].values)
    if bone.rotation_mode == "QUATERNION":
        for w, x, y, z in zip(*get_entire_fcurve_data(action, bone, "rotation_quaternion", max_frame, 4)):
            euler = mathutils.Quaternion((w, x, y, z)).to_euler()
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
            euler = mathutils.Euler(x, y, z, action, bone.rotation_mode)
            rotation[0].append(radians_to_s16(euler.x))
            rotation[1].append(radians_to_s16(euler.y))
            rotation[2].append(radians_to_s16(euler.z))
    return rotation_pairs


def get_animation_pairs(
    blender_to_sm64_scale: float, max_frame: int, action: Action, armature_obj: Object, quick_read: bool = True
) -> tuple[list[int], list[int]]:
    print(f"Reading animation pair values from action {action.name}.")
    anim_bones = get_anim_pose_bones(armature_obj)
    if len(anim_bones) < 1:
        raise PluginError(f'No animation bones in armature "{armature_obj.name}"')

    pairs = []
    if quick_read:
        root_bone = anim_bones[0]
        pairs.extend(get_trans_data(action, root_bone, max_frame, blender_to_sm64_scale))

        for i, pose_bone in enumerate(anim_bones):
            pairs.extend(get_rotation_data(action, pose_bone, max_frame))
    else:
        pre_export_frame = bpy.context.scene.frame_current
        pre_export_action = armature_obj.animation_data.action
        armature_obj.animation_data.action = action

        pairs = [
            SM64_AnimPair(),
            SM64_AnimPair(),
            SM64_AnimPair(),
        ]
        trans_x_pair, trans_y_pair, trans_z_pair = pairs

        rotation_pairs: list[tuple[SM64_AnimPair]] = []
        for _ in anim_bones:
            rotation = (
                SM64_AnimPair(),
                SM64_AnimPair(),
                SM64_AnimPair(),
            )
            rotation_pairs.append(rotation)
            pairs.extend(rotation)

        scale: mathutils.Vector = armature_obj.matrix_world.to_scale() * blender_to_sm64_scale
        for frame in range(max_frame):
            bpy.context.scene.frame_set(frame)
            for i, pose_bone in enumerate(anim_bones):
                matrix = pose_bone.matrix_basis
                if i == 0:  # Only first bone has translation.
                    translation: mathutils.Vector = matrix.to_translation() * scale
                    trans_x_pair.values.append(int(translation.x))
                    trans_y_pair.values.append(int(translation.y))
                    trans_z_pair.values.append(int(translation.z))

                for angle, pair in zip(matrix.to_euler(), rotation_pairs[i]):
                    pair.values.append(radians_to_s16(angle))

        armature_obj.animation_data.action = pre_export_action
        bpy.context.scene.frame_current = pre_export_frame

    for pair in pairs:
        pair.clean_frames()
    return pairs


def update_includes(
    level_name: str,
    group_name: str,
    dir_name: str,
    dir_path: str,
    header_type: str,
    update_table: bool,
):
    if header_type == "Actor":
        data_path = os.path.join(dir_path, f"{group_name}.c")
        header_path = os.path.join(dir_path, f"{group_name}.h")
        include_start = f'#include "{dir_name}/'
    elif header_type == "Level":
        data_path = os.path.join(dir_path, "leveldata.c")
        header_path = os.path.join(dir_path, "header.h")
        include_start = f'#include "{dir_name}/{level_name}/anims/'
    print(f"Updating includes at {data_path} and {header_path}.")
    writeIfNotFound(data_path, f'{include_start}/anims/data.inc.c"\n', "")
    if update_table:
        writeIfNotFound(data_path, f'{include_start}/anims/table.inc.c"\n', "")
        writeIfNotFound(header_path, f'{include_start}/anim_header.h"\n', "#endif")


def write_anim_header(
    anim_header_path: str,
    table_name: str,
    generate_enums: bool,
):
    print("Writing animation header")
    with open(anim_header_path, "w", encoding="utf-8") as file:
        if generate_enums:
            file.write('#include "anims/table_enum.h"\n')
        file.write(f"extern const struct Animation *const {table_name}[];\n")


def update_enum_file(
    enum_path: str,
    enum_list_name: str,
    enum_names: list[str],
    override_files: bool,
):
    if override_files or not os.path.exists(enum_path):
        text = ""
    else:
        with open(enum_path, "r") as file:
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

    with open(enum_path, "w", newline="\n") as file:
        file.write(text)


def update_table_file(
    table_path: str,
    enum_and_header_names: list[tuple[str, str]],
    table_name: str,
    generate_enums: bool,
    enum_path: str,
    enum_list_name: str,
):
    if not os.path.exists(table_path):
        text = ""
    else:
        with open(table_path, "r") as file:
            text = file.read()

    if generate_enums:
        update_enum_file(enum_path, enum_list_name, [tup[0] for tup in enum_and_header_names], False)

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

    with open(table_path, "w", newline="\n") as file:
        file.write(text)


def update_data_file(data_file_path: os.PathLike, anim_file_names: list, override_files: bool = False):
    print(f"Updating animation data file at {data_file_path}")
    if not os.path.exists(data_file_path) or override_files:
        with open(data_file_path, "w", newline="\n"):
            pass  # Leave empty

    for anim_file_name in anim_file_names:
        writeIfNotFound(data_file_path, f'#include "{anim_file_name}"\n', "")


def export_animation_table_c(
    animation_props: "SM64_AnimProps",
    table_props: "SM64_AnimTableProps",
    table: SM64_AnimTable,
    decomp_path: os.PathLike,
):
    header_type = animation_props.header_type
    if header_type != "Custom":
        applyBasicTweaks(decomp_path)
    anim_dir_path, dir_path, geo_dir_path, level_name = animation_props.get_animation_paths(True)

    print("Creating all C data")
    if table_props.export_seperately:
        files_data = table.data_and_headers_to_c(header_type == "DMA")
        print("Saving all generated data files")
        for file_name, file_data in files_data.items():
            with open(os.path.join(anim_dir_path, file_name), "w", encoding="utf-8") as file:
                file.write(file_data)
            print(file_name)
        print("All files exported")
        if header_type != "DMA":
            update_data_file(
                os.path.join(anim_dir_path, "data.inc.c"),
                files_data.keys(),
                table_props.override_files,
            )
    else:
        result = table.data_and_headers_to_c_combined()
        print("Saving generated data file")
        with open(os.path.join(anim_dir_path, "data.inc.c"), "w", encoding="utf-8") as file:
            file.write(result)
        print("File exported")

    if header_type == "DMA":
        return

    header_path = os.path.join(geo_dir_path, "anim_header.h")
    write_anim_header(header_path, table.reference, table_props.generate_enums)
    if table_props.override_files:
        with open(os.path.join(anim_dir_path, "table.inc.c"), "w", encoding="utf-8") as file:
            file.write(table.table_to_c())
        if table_props.generate_enums:
            table_enum_path = os.path.join(anim_dir_path, "table_enum.h")
            with open(table_enum_path, "w", encoding="utf-8") as file:
                file.write(table.enum_list_to_c())
    else:
        update_table_file(
            os.path.join(anim_dir_path, "table.inc.c"),
            table.enum_and_header_names,
            table.reference,
            table_props.generate_enums,
            os.path.join(anim_dir_path, "table_enum.h"),
            table.enum_list_reference,
        )

    if header_type == "Custom":
        return
    update_includes(
        level_name,
        animation_props.group_name,
        toAlnum(animation_props.actor_name),
        dir_path,
        header_type,
        True,
    )


class SM64_BinaryExporter:

    def __init__(self, export_rom: os.PathLike, output_rom: os.PathLike, extended_check: bool = False):
        self.export_rom = export_rom
        self.output_rom = output_rom
        self.temp_rom: os.PathLike = tempName(self.output_rom)
        self.rom_file_output: BinaryIO = None
        self.extended_check = extended_check

    def __enter__(self):
        export_rom_checks(self.export_rom, self.extended_check)
        shutil.copy(abspath(self.export_rom), abspath(self.temp_rom))
        self.rom_file_output = open(abspath(self.temp_rom), "rb+")
        return self

    def write_to_range(self, start_address: int, end_address: int, data: bytes):
        assert (
            start_address + len(data) <= end_address
        ), f"Data does not fit in the bounds ({intToHex(start_address)}, {intToHex(end_address)})"
        self.rom_file_output.seek(start_address)
        self.rom_file_output.write(data)

    def __exit__(self, exc_type, exc_value, traceback):
        self.rom_file_output.close()
        if exc_value:
            if os.path.exists(self.temp_rom):
                os.remove(self.temp_rom)
            print("\nExecution type:", exc_type)
            print("\nExecution value:", exc_value)
            print("\nTraceback:", traceback)
        else:
            if os.path.exists(self.output_rom):
                os.remove(self.output_rom)
            os.rename(self.temp_rom, self.output_rom)


def export_animation_table(context: Context):
    bpy.ops.object.mode_set(mode="OBJECT")
    animation_operator_checks(context)

    scene = context.scene
    sm64_props: SM64_Properties = scene.fast64.sm64
    armature_obj: Object = context.selected_objects[0]
    if context.space_data.type != "VIEW_3D" and context.space_data.context == "OBJECT":
        animation_props: SM64_AnimProps = armature_obj.fast64.sm64.animation
    else:
        animation_props: SM64_AnimProps = sm64_props.animation
    table_props: SM64_AnimTableProps = animation_props.table

    is_binary_dma = sm64_props.binary_export and animation_props.is_binary_dma
    is_dma = is_binary_dma or animation_props.header_type == "DMA"

    print("Stashing all actions in table")
    for action in table_props.get_actions(not is_dma):
        stashActionInArmature(armature_obj, action)

    print("Reading table data from fast64")
    table: SM64_AnimTable = table_props.to_table_class(
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
        path = abspath(os.path.join(animation_props.directory_path, table_props.insertable_file_name))
        if is_binary_dma:
            data = table.to_binary_dma()
            writeInsertableFile(path, insertableBinaryTypes["Animation DMA Table"], [], 0, data)
        else:
            data, ptrs = table.to_combined_binary(animation_props.is_binary_dma, 0)
            writeInsertableFile(path, insertableBinaryTypes["Animation Table"], ptrs, 0, data)
    else:
        with SM64_BinaryExporter(
            sm64_props.export_rom, sm64_props.output_rom, sm64_props.extended_rom_check
        ) as rom_file_output:
            if is_binary_dma:
                data = table.to_binary_dma()
                rom_file_output.write_to_range(
                    int(table_props.dma_address, 0),
                    int(table_props.dma_end_address, 0),
                    data,
                )


def export_animation(context: Context):
    animation_operator_checks(context)

    scene = context.scene
    sm64_props: SM64_Properties = scene.fast64.sm64
    armature_obj: Object = context.selected_objects[0]
    if context.space_data.type != "VIEW_3D" and context.space_data.context == "OBJECT":
        animation_props: SM64_AnimProps = armature_obj.fast64.sm64.animation
    else:
        animation_props: SM64_AnimProps = sm64_props.animation
    table_props: SM64_AnimTableProps = animation_props.table

    action = animation_props.selected_action
    action_props: SM64_ActionProps = action.fast64.sm64
    stashActionInArmature(armature_obj, action)

    actor_name = animation_props.actor_name
    animation: SM64_Anim = action_props.to_animation_class(
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
    if sm64_props.export_type == "C":
        header_type = animation_props.header_type

        anim_dir_path, dir_path, geo_dir_path, level_name = animation_props.get_animation_paths(create_directories=True)
        anim_file_name = action_props.get_anim_file_name(action)
        anim_path = os.path.join(anim_dir_path, anim_file_name)

        if header_type != "Custom":
            applyBasicTweaks(abspath(sm64_props.decomp_path))

        with open(anim_path, "w", encoding="utf-8") as file:
            file.write(animation.to_c(animation_props.is_c_dma_structure))

        if header_type != "DMA":
            table_name = table_props.get_anim_table_name(actor_name)
            enum_list_name = table_props.get_enum_list_name(actor_name)

            if table_props.update_table:
                write_anim_header(
                    os.path.join(geo_dir_path, "anim_header.h"),
                    table_name,
                    table_props.generate_enums,
                )
                update_table_file(
                    os.path.join(anim_dir_path, "table.inc.c"),
                    action_props.get_enum_and_header_names(action, actor_name),
                    table_name,
                    table_props.generate_enums,
                    os.path.join(anim_dir_path, "table_enum.h"),
                    enum_list_name,
                )
            update_data_file(os.path.join(anim_dir_path, "data.inc.c"), [anim_file_name])

        if not header_type in {"Custom", "DMA"}:
            update_includes(
                level_name,
                animation_props.group_name,
                toAlnum(actor_name),
                dir_path,
                header_type,
                table_props.update_table,
            )
    elif sm64_props.export_type == "Insertable Binary":
        data, ptrs = animation.to_binary(animation_props.is_binary_dma)
        path = abspath(action_props.get_anim_file_name(action))
        writeInsertableFile(path, insertableBinaryTypes["Animation"], ptrs, 0, data)
    else:
        raise PluginError(f"Unimplemented export type ({sm64_props.export_type})")
