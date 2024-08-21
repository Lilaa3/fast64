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
        SM64_ArmatureAnimProperties,
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


def get_action(name: str):
    if name == "":
        raise ValueError("Empty action name.")
    if not name in bpy.data.actions:
        raise IndexError(f"Action ({name}) is not in this file´s action data.")
    return bpy.data.actions[name]


def get_selected_action(armature: Object, raise_exc=True) -> Action:
    assert armature is not None
    if armature.type == "ARMATURE" and armature.animation_data and armature.animation_data.action:
        return armature.animation_data.action
    if raise_exc:
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


def num_to_padded_hex(num: int):
    hex_str = hex(num)[2:].upper()  # remove the '0x' prefix
    return hex_str.zfill(2)


def get_dma_anim_name(index: int):
    return f"anim_{num_to_padded_hex(index)}"


def get_max_frame(action: Action, action_props: "SM64_ActionProperty") -> int:
    if action_props.use_custom_max_frame:
        return action_props.custom_max_frame
    loop_ends: list[int] = [getFrameInterval(action)[1]]
    header_props: SM64_AnimHeaderProperties
    for header_props in action_props.headers:
        loop_ends.append(header_props.get_loop_points(action)[2])

    return max(loop_ends)


def get_scene_anim_props(context: Context) -> "SM64_AnimProperties":
    return context.scene.fast64.sm64.animation


def get_anim_props(context: Context) -> "SM64_ArmatureAnimProperties":
    assert context.object
    assert context.object.type == "ARMATURE"
    return context.object.data.fast64.sm64.animation


def get_anim_actor_name(context: Context):
    sm64_props = context.scene.fast64.sm64
    if sm64_props.export_type == "C" and sm64_props.combined_export.export_anim:
        return toAlnum(sm64_props.combined_export.obj_name_anim)
    return sm64_props.combined_export.filter_name(toAlnum(context.object.name) if context.object else "", True)


def dma_structure_context(context: Context):
    if not context.object or context.object.type != "ARMATURE":
        return False
    return get_anim_props(context).is_dma
