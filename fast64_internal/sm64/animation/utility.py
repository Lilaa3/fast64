import dataclasses, math, re, numpy as np

import bpy
from mathutils import Euler, Quaternion, Vector
from bpy.types import Context, Object, Action, PoseBone

from ...utility_anim import getFrameInterval
from ...utility import findStartBones, PluginError, toAlnum
from ..sm64_geolayout_bone import animatableBoneTypes

from .constants import FLAG_PROPS

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .properties import (
        SM64_AnimProperties,
        SM64_AnimHeaderProperties,
        SM64_ActionProperty,
        SM64_AnimTableElement,
        SM64_AnimTableProperties,
    )


def animation_operator_checks(context: Context, requires_animation=True, specific_obj: Object = None):
    if specific_obj:
        obj = specific_obj
    else:
        if len(context.selected_objects) == 0 and context.object is None:
            raise PluginError("No armature selected.")
        if len(context.selected_objects) > 1:
            raise PluginError("Multiple objects selected at once.")
        obj = context.object

    if obj.type != "ARMATURE":
        raise PluginError(f'Selected object "{obj.name}" is not an armature.')
    if requires_animation and obj.animation_data is None:
        raise PluginError(f'Armature "{obj.name}" has no animation data.')


def get_scene_anim_props(context: Context) -> "SM64_AnimProperties":
    return context.scene.fast64.sm64.animation


def get_anim_props(context: Context) -> "SM64_ArmatureAnimProperties":
    assert context.object
    assert context.object.type == "ARMATURE"
    return context.object.data.fast64.sm64.animation


def get_action(name: str):
    if name == "":
        raise ValueError("Empty action name.")
    if not name in bpy.data.actions:
        raise IndexError(f"Action ({name}) is not in this file´s action data.")
    return bpy.data.actions[name]


def get_selected_action(armature: Object) -> Action:
    if armature.animation_data and armature.animation_data.action:
        return armature.animation_data.action
    raise ValueError(f'No action selected in armature "{armature.name}".')


# TODO: MOVE THESE
def get_anim_pose_bones(armature: Object) -> list[PoseBone]:
    bones_to_process: list[str] = findStartBones(armature)
    current_bone = armature.data.bones[bones_to_process[0]]
    anim_bones = []

    # Get animation bones in order
    while len(bones_to_process) > 0:
        bone_name = bones_to_process[0]
        current_bone = armature.data.bones[bone_name]
        current_pose_bone = armature.pose.bones[bone_name]
        bones_to_process = bones_to_process[1:]

        # Only handle 0x13 bones for animation
        if current_bone.geo_cmd in animatableBoneTypes:
            anim_bones.append(current_pose_bone)

        # Traverse children in alphabetical order.
        children_names = sorted([bone.name for bone in current_bone.children])
        bones_to_process = children_names + bones_to_process

    return anim_bones


def get_frame_range(action: Action, header_props: "SM64_AnimHeaderProperties") -> tuple[int, int, int]:
    if header_props.manual_loop:
        return (header_props.start_frame, header_props.loop_start, header_props.loop_end)
    loop_start, loop_end = getFrameInterval(action)
    return (0, loop_start, loop_end + 1)


def get_anim_name(actor_name: str, action: Action, header_props: "SM64_AnimHeaderProperties") -> str:
    if header_props.use_custom_name:
        return header_props.custom_name
    if header_props.header_variant == 0:
        if actor_name:
            name = f"{actor_name}_anim_{action.name}"
        else:
            name = f"anim_{action.name}"
        return toAlnum(name)
    main_header_name = get_anim_name(actor_name, action, action.fast64.sm64.headers[0])
    name = f"{main_header_name}_{header_props.header_variant}"

    return toAlnum(name)


def num_to_padded_hex(num: int):
    hex_str = hex(num)[2:].upper()  # remove the '0x' prefix
    return hex_str.zfill(2)


def get_dma_anim_name(index: int):
    return f"anim_{num_to_padded_hex(index)}"


def get_anim_enum(actor_name: str, action: Action, header_props: "SM64_AnimHeaderProperties") -> str:
    if header_props.use_custom_enum:
        return header_props.custom_enum
    anim_name = get_anim_name(actor_name, action, header_props)
    enum_name = anim_name.upper()
    if anim_name == enum_name:
        enum_name = f"_{enum_name}"
    return enum_name


def get_int_flags(header_props: "SM64_AnimHeaderProperties"):
    flags: int = 0
    for i, flag in enumerate(FLAG_PROPS):
        flags |= 1 << i if getattr(header_props, flag) else 0
    return flags


def update_header_variant_numbers(action_props: "SM64_ActionProperty"):
    for i, variant in enumerate(action_props.headers):
        variant.header_variant = i


def get_max_frame(action: Action, action_props: "SM64_ActionProperty") -> int:
    if action_props.use_custom_max_frame:
        return action_props.custom_max_frame

    loop_ends: list[int] = [getFrameInterval(action)[1]]
    for header_props in action_props.headers:
        loop_end = get_frame_range(action, header_props)[2]
        loop_ends.append(loop_end)

    return max(loop_ends)


def get_element_header(element_props: "SM64_AnimTableElement", use_reference: bool) -> "SM64_AnimHeaderProperties":
    if use_reference and element_props.reference:
        return None
    action = get_element_action(element_props, use_reference)
    if not action:
        return None
    return action.fast64.sm64.headers[element_props.variant]


def get_element_action(element_props: "SM64_AnimTableElement", use_reference: bool) -> Action:
    if use_reference and element_props.reference:
        return None
    return element_props.action_prop


def get_enum_list_name(table_props: "SM64_AnimTableProperties", actor_name: str):
    table_name = table_props.get_name(actor_name)
    return table_name.title().replace("_", "")


def get_enum_list_end(table_props: "SM64_AnimTableProperties", actor_name: str):
    table_name = table_props.get_name(actor_name)
    return f"{table_name.upper()}_END"


def get_anim_actor_name(context: Context):
    sm64_props = context.scene.fast64.sm64
    if sm64_props.export_type == "C" and sm64_props.combined_export.export_anim:
        return toAlnum(sm64_props.combined_export.obj_name_anim)
    return sm64_props.combined_export.filter_name(toAlnum(context.object.name) if context.object else "", True)


def dma_structure_context(context: Context):
    if not context.object or context.object.type != "ARMATURE":
        return False
    sm64_props = context.scene.fast64.sm64
    anim_props = get_anim_props(context)
    header_type = sm64_props.combined_export.export_header_type
    if sm64_props.export_type == "C" and header_type == "Custom" and anim_props.use_dma_structure:
        return True
    else:
        return anim_props.is_dma
