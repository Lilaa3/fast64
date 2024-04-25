from collections import OrderedDict
import math
import os

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
    SM64_AnimData,
    SM64_AnimHeader,
    SM64_AnimPair,
    SM64_AnimTable,
)
from .c_parser import CParser, EnumIndexedValue, Initialization


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
        self.clean_frames()

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


def import_animation_from_c_header(
    animations: dict[str, SM64_Anim], header_initialization: Initialization, c_parser: CParser
):
    print(f"Reading animation {header_initialization.name}")

    header = SM64_AnimHeader()
    header.read_c(header_initialization)

    data_key = f"{header.indice_reference}-{header.values_reference}"

    if data_key in animations:
        anim = animations[data_key]
    else:
        anim = SM64_Anim()
        if header.indice_reference in c_parser.values_by_name and header.values_reference in c_parser.values_by_name:
            indices_array = c_parser.values_by_name[header.indice_reference]
            values_array = c_parser.values_by_name[header.values_reference]
            anim.data = SM64_AnimData()
            anim.data.read_c(indices_array, values_array)
            header.data = anim.data

        animations[data_key] = anim

    header.header_variant = len(anim.headers)
    header.data = anim
    anim.headers.append(header)

    return header


def import_c_animations(path: str, animations: dict[str, SM64_Anim], table: SM64_AnimTable):
    path_checks(path)

    if os.path.isfile(path):
        file_paths: list[str] = [path]
    elif os.path.isdir(path):
        file_names = sorted(os.listdir(path))
        file_paths: list[str] = [os.path.join(path, fileName) for fileName in file_names]

    c_parser = CParser()

    for filepath in file_paths:
        print(f"Reading file {filepath}")
        try:
            with open(filepath, "r") as file:
                c_parser.read_c_text(file.read(), filepath)
        except Exception as e:
            print(f"Exception while attempting to parse file {filepath}: {str(e)}")
            # Should I raise here?

    print("All files have been parsed")

    table_initialization: None | Initialization = None
    all_headers: OrderedDict[SM64_AnimHeader] = OrderedDict()

    for value in c_parser.values:
        if not "Animation" in value.keywords:
            continue

        if value.pointer_depth == 1:  # Table
            table_initialization = value
        else:
            header = import_animation_from_c_header(animations, value, c_parser)
            all_headers[header.reference] = header

    if table_initialization:  # If a table was found
        for element in table_initialization.value.value:
            if isinstance(element, EnumIndexedValue):
                name = element.value.value[1:]
            else:
                name = element.value[1:]
            if name in all_headers:
                table.elements.append(all_headers[name])
        table.name = table_initialization.name
    else:
        table.elements.extend(all_headers.values())


def import_binary_header(
    header_reader: RomReading,
    is_dma: bool,
    animations: dict[str, SM64_Anim],
    assumed_bone_count: int | None = None,
):
    print(f"Reading binary header at address {hex(header_reader.address)}")
    header = SM64_AnimHeader()
    header.read_binary(header_reader=header_reader, is_dma=is_dma, assumed_bone_count=assumed_bone_count)

    data_key = f"{header.indice_reference}-{header.values_reference}"
    if data_key in animations:
        anim = animations[data_key]
    else:
        anim = SM64_Anim()
        # TODO: if header.indice_reference < len(data) and header.values_reference < len(data):
        if True:
            anim.data = SM64_AnimData()
            anim.data.read_binary(
                indices_reader=header_reader.branch(header.indice_reference),
                values_reader=header_reader.branch(header.values_reference),
                bone_count=header.bone_count,
            )
            header.data = anim.data
        animations[data_key] = anim

    header.header_variant = len(anim.headers)
    header.data = anim
    anim.headers.append(header)
    return header


def import_binary_dma_animation(
    dma_table_reader: RomReading,
    animations: dict[str, SM64_Anim],
    table: SM64_AnimTable,
    table_index: int | None = None,
    assumed_bone_count: int | None = None,
) -> SM64_AnimHeader | None:
    dma_table = SM64_DMATable()
    dma_table.read_binary(dma_table_reader)
    if table_index is not None:
        if table_index < 0 or table_index >= len(dma_table.entries):
            raise PluginError(f"Index {table_index} outside of defined table ({len(dma_table.entries)} entries).")

        entrie: DMATableEntrie = dma_table.entries[table_index]
        header = import_binary_header(
            header_reader=dma_table_reader.branch(entrie.address),
            is_dma=True,
            animations=animations,
            assumed_bone_count=assumed_bone_count,
        )
        table.elements.append(header)
        return header
    else:
        for entrie in dma_table.entries:
            header = import_binary_header(
                header_reader=dma_table_reader.branch(entrie.address),
                is_dma=True,
                animations=animations,
                assumed_bone_count=assumed_bone_count,
            )
            table.elements.append(header)


def import_binary_table(
    table_reader: RomReading,
    animations: dict[str, SM64_Anim],
    table: SM64_AnimTable,
    ignore_null: bool,
    table_index: int | None = None,
    assumed_bone_count: int | None = None,
):
    for i in range(255):
        ptr = table_reader.read_ptr()
        if ptr is None and not ignore_null:
            if table_index is not None:
                raise PluginError("Table index not in table.")
            break

        is_correct_index = i == table_index
        if table_index is None or is_correct_index:
            header = import_binary_header(
                header_reader=table_reader.branch(ptr),
                is_dma=False,
                animations=animations,
                assumed_bone_count=assumed_bone_count,
            )
            table.elements.append(header)

            if table_index is not None and is_correct_index:
                break
    else:
        raise PluginError("Table address is invalid, iterated through 255 indices and no NULL was found.")


def import_binary_animations(
    data_reader: RomReading,
    import_type: str,
    animations: dict[str, SM64_Anim],
    table_index: int | None = None,
    ignore_null: bool = False,
    assumed_bone_count: int | None = None,
    table: SM64_AnimTable = SM64_AnimTable(),
):
    if import_type == "Table":
        import_binary_table(
            table_reader=data_reader,
            animations=animations,
            table=table,
            table_index=table_index,
            ignore_null=ignore_null,
            assumed_bone_count=assumed_bone_count,
        )
    elif import_type == "DMA":
        import_binary_dma_animation(
            dma_table_reader=data_reader,
            animations=animations,
            table=table,
            table_index=table_index,
            assumed_bone_count=assumed_bone_count,
        )
    elif import_type == "Animation":
        import_binary_header(
            header_reader=data_reader,
            is_dma=False,
            animations=animations,
            assumed_bone_count=assumed_bone_count,
        )
    else:
        raise PluginError("Unimplemented binary import type.")


def import_insertable_binary_animations(
    insertable_data_reader: RomReading,
    animations: dict[str, SM64_Anim],
    table_index: int = 0,
    ignore_null: bool = False,
    assumed_bone_count: int | None = None,
    table: SM64_AnimTable = SM64_AnimTable(),
):
    data_type_num = insertable_data_reader.read_value(4, signed=False)
    if data_type_num not in insertableBinaryTypes.values():
        raise PluginError(f"Unknown data type: {hex(data_type_num)}")
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
            animations=animations,
            assumed_bone_count=assumed_bone_count,
        )
    elif data_type == "Animation Table":
        import_binary_table(
            table_reader=data_reader,
            animations=animations,
            table=table,
            table_index=table_index,
            ignore_null=ignore_null,
            assumed_bone_count=assumed_bone_count,
        )
    else:
        raise PluginError(f'Wrong animation data type "{data_type}".')
