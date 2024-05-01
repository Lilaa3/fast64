import dataclasses
import math

import bpy
from bpy.types import Object, Armature

from ...utility import findStartBones, PluginError, decodeSegmentedAddr, intToHex
from ..sm64_geolayout_bone import animatableBoneTypes

def animation_operator_checks(context, requires_animation_data=True):
    if len(context.selected_objects) > 1:
        raise PluginError("Multiple objects selected at once, make sure to select only one armature.")
    if len(context.selected_objects) == 0:
        raise PluginError("No armature selected.")

    armature_obj: Object = context.selected_objects[0]
    if not isinstance(armature_obj.data, Armature):
        raise PluginError("Selected object is not an armature.")

    if requires_animation_data and armature_obj.animation_data is None:
        raise PluginError("Armature has no animation data.")


def get_action(action_name: str):
    if action_name == "":
        raise PluginError("Empty action name.")
    if not action_name in bpy.data.actions:
        raise PluginError(f"Action ({action_name}) is not in this file´s action data.")

    return bpy.data.actions[action_name]


def sm64_to_radian(signed_sm64_angle: int) -> float:
    unsigned_sm64_angle = signed_sm64_angle + (1 << 16)
    degree = unsigned_sm64_angle * (360.0 / (1 << 16))
    return math.radians(degree % 360.0)


def get_anim_pose_bones(armature_obj: Armature):
    bones_to_process: list[str] = findStartBones(armature_obj)
    current_bone = armature_obj.data.bones[bones_to_process[0]]
    anim_bones: list[bpy.types.Bone] = []

    # Get animation bones in order
    while len(bones_to_process) > 0:
        bone_name = bones_to_process[0]
        current_bone = armature_obj.data.bones[bone_name]
        current_pose_bone = armature_obj.pose.bones[bone_name]
        bones_to_process = bones_to_process[1:]

        # Only handle 0x13 bones for animation
        if current_bone.geo_cmd in animatableBoneTypes:
            anim_bones.append(current_pose_bone)

        # Traverse children in alphabetical order.
        children_names = sorted([bone.name for bone in current_bone.children])
        bones_to_process = children_names + bones_to_process

    return anim_bones
