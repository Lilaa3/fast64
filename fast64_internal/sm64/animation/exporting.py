import os

import bpy
import mathutils
from bpy.types import Object, Action, PoseBone

from ...utility import PluginError, writeIfNotFound, radians_to_s16

from .classes import SM64_AnimPair
from .utility import get_anim_pose_bones


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
    trasnlation_pairs = (
        SM64_AnimPair(),
        SM64_AnimPair(),
        SM64_AnimPair(),
    )
    data_path = f'pose.bones["{bpy.utils.escape_identifier(bone.name)}"].location'
    for fcurve in action.fcurves:
        if fcurve.data_path != data_path:
            continue
        for index in range(3):
            if fcurve.array_index == index:
                values = trasnlation_pairs[index].values
                for frame in range(max_frame):
                    values.append(int(fcurve.evaluate(frame) * blender_to_sm64_scale))
    return trasnlation_pairs


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
    anim_bones = get_anim_pose_bones(armature_obj)
    if len(anim_bones) < 1:
        raise PluginError(f'No animation bones in armature "{armature_obj.name}"')

    pairs = []

    print(f"Reading animation pair values from action {action.name}.")

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
    level_name: str, group_name: str, dir_name: str, dir_path: str, header_type: str, update_table: bool
):
    if header_type == "Actor":
        data_path = os.path.join(dir_path, f"{group_name}.c")
        header_path = os.path.join(dir_path, f"{group_name}.h")

        writeIfNotFound(data_path, f'\n#include "{dir_name}/anims/data.inc.c"\n', "")
        if update_table:
            writeIfNotFound(data_path, f'\n#include "{dir_name}/anims/table.inc.c"\n', "")
            writeIfNotFound(header_path, f'\n#include "{dir_name}/anim_header.h"\n', "#endif")
    elif header_type == "Level":
        data_path = os.path.join(dir_path, "leveldata.c")
        header_path = os.path.join(dir_path, "header.h")

        writeIfNotFound(data_path, f'\n#include "levels/{level_name}/{dir_name}/anims/data.inc.c"\n', "")
        if update_table:
            writeIfNotFound(data_path, f'\n#include "levels/{level_name}/{dir_name}/anims/table.inc.c"\n', "")
            writeIfNotFound(header_path, f'\n#include "levels/{level_name}/{dir_name}/anim_header.h"\n', "\n#endif")


def write_anim_header(
    anim_header_path: str,
    table_name: str,
    generate_enums: bool,
):
    with open(anim_header_path, "w", newline="\n") as file:
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
