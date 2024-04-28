import math
import os
import re

import bpy
from bpy.types import Object, Action
from mathutils import Euler, Vector, Quaternion

from ...utility import PluginError, path_checks
from ...utility_anim import stashActionInArmature
from ..sm64_constants import insertableBinaryTypes

from .utility import RomReading, get_anim_pose_bones, sm64_to_radian
from .classes import (
    SM64_DMATable,
    DMATableEntrie,
    SM64_Anim,
    CArrayDeclaration,
    SM64_AnimHeader,
    SM64_AnimPair,
    SM64_AnimTable,
)


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


class SM64_AnimBone:
    def __init__(self):
        self.translation: list[Vector] = []
        self.rotation: list[Quaternion] = []

    def read_pairs(self, pairs: list[SM64_AnimPair]):
        array: list[int] = []

        max_frame = max(len(pair.values) for pair in pairs)
        for frame in range(max_frame):
            array.append([x.get_frame(frame) for x in pairs])
        return array

    def read_translation(self, pairs: list[SM64_AnimPair], scale: float):
        translation_frames = self.read_pairs(pairs)

        for translation_frame in translation_frames:
            self.translation.append([x / scale for x in translation_frame])

    def read_rotation(self, pairs: list[SM64_AnimPair]):
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
    anim_import: SM64_Anim,
    action: Action,
):
    anim_bones = get_anim_pose_bones(armature_obj)
    for pose_bone in anim_bones:
        pose_bone.rotation_mode = "QUATERNION"

    bone_anim_data: list[SM64_AnimBone] = []

    # TODO: Duplicate keyframe filter
    pairs = anim_import.data.pairs
    for pair in pairs:
        pair.clean_frames()

    for pair_num in range(3, len(pairs), 3):
        bone = SM64_AnimBone()
        if pair_num == 3:
            bone.read_translation(pairs[0:3], blender_to_sm64_scale)
        bone.read_rotation(pairs[pair_num : pair_num + 3])
        bone_anim_data.append(bone)

    is_root = True
    for pose_bone, bone_data in zip(anim_bones, bone_anim_data):
        if is_root:
            for property_index in range(3):
                f_curve = action.fcurves.new(
                    data_path='pose.bones["' + pose_bone.name + '"].location',
                    index=property_index,
                    action_group=pose_bone.name,
                )
                for frame, translation in enumerate(bone_data.translation):
                    f_curve.keyframe_points.insert(frame, translation[property_index])
            is_root = False

        for property_index in range(4):
            f_curve = action.fcurves.new(
                data_path='pose.bones["' + pose_bone.name + '"].rotation_quaternion',
                index=property_index,
                action_group=pose_bone.name,
            )
            for frame, rotation in enumerate(bone_data.rotation):
                f_curve.keyframe_points.insert(frame, rotation[property_index])


def animation_import_to_blender(
    armature_obj: Object,
    blender_to_sm64_scale: float,
    anim_import: SM64_Anim,
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

    action.fast64.sm64.from_anim_class(anim_import, action, actor_name, remove_name_footer, use_custom_name)

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
    animation_headers: dict[str, SM64_AnimHeader],
    animation_data: dict[tuple[str, str], SM64_Anim],
    table: SM64_AnimTable,
):
    path_checks(path)

    header_decls, value_decls, indices_decls, table_decls = [], [], [], []

    if os.path.isfile(path):
        file_paths = [path]
    else:
        file_paths = sorted(os.listdir(path))
        file_paths = [os.path.join(path, file_name) for file_name in file_paths]

    for file_path in file_paths:
        print("Reading from: " + file_path)
        with open(file_path, "r", newline="\n") as file:
            c_data = comment_remover(file.read())

        find_decls(c_data, "static const struct Animation ", file_path, header_decls)
        find_decls(c_data, "static const u16 ", file_path, indices_decls)
        find_decls(c_data, "static const s16 ", file_path, value_decls)
        find_decls(c_data, "const struct Animation *const ", file_path, table_decls)

    if table_decls:
        assert len(table_decls) <= 1, "More than 1 table declaration"
        table.read_c(table_decls[0], animation_headers, animation_data, header_decls, value_decls, indices_decls)
        return
    for header_decl in header_decls:
        header = SM64_AnimHeader().read_c(header_decl, value_decls, indices_decls, animation_headers, animation_data)


def import_binary_animations(
    data_reader: RomReading,
    import_type: str,
    animation_headers: dict[str, SM64_AnimHeader],
    animation_data: dict[tuple[str, str], SM64_Anim],
    table: SM64_AnimTable,
    table_index: int | None = None,
    ignore_null: bool = False,
    assumed_bone_count: int | None = None,
):
    if import_type == "Table":
        table.read_binary(data_reader, animation_headers, animation_data, table_index, ignore_null, assumed_bone_count)
    elif import_type == "DMA":
        table.read_dma_binary(data_reader, animation_headers, animation_data, table_index, assumed_bone_count)
    elif import_type == "Animation":
        SM64_AnimHeader.read_binary(
            data_reader,
            animation_headers,
            animation_data,
            False,
            assumed_bone_count,
        )
    else:
        raise PluginError("Unimplemented binary import type.")


def import_insertable_binary_animations(
    insertable_data_reader: RomReading,
    animation_headers: dict[str, SM64_AnimHeader],
    animation_data: dict[tuple[str, str], SM64_Anim],
    table_index: int = 0,
    ignore_null: bool = False,
    assumed_bone_count: int | None = None,
    table: SM64_AnimTable = SM64_AnimTable(),
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
    insertable_data_reader.insertable_ptrs = pointer_offsets

    actual_start = insertable_data_reader.address + start_address
    data_reader = insertable_data_reader.branch(
        0,
        insertable_data_reader.data[actual_start : actual_start + data_size],
    )

    data_type = next(key for key, value in insertableBinaryTypes.items() if value == data_type_num)
    if data_type == "Animation":
        import_binary_header(
            header_reader=data_reader,
            is_dma=False,
            animation_data=animation_data,
            assumed_bone_count=assumed_bone_count,
        )
    elif data_type == "Animation Table":
        pass
    else:
        raise PluginError(f'Wrong animation data type "{data_type}".')
