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


# Header properties utility
def get_frame_range(self, action: Action) -> tuple[int, int, int]:
    if self.manual_frame_range:
        return (self.start_frame, self.loop_start, self.loop_end)
    loop_start, loop_end = getFrameInterval(action)
    return (0, loop_start, loop_end + 1)


def get_anim_name(self, actor_name: str, action: Action) -> str:
    if self.override_name:
        return self.custom_name
    if self.header_variant == 0:
        if actor_name:
            name = f"{actor_name}_anim_{action.name}"
        else:
            name = f"anim_{action.name}"
        return toAlnum(name)
    main_header_name = action.fast64.sm64.headers[0].get_anim_name(actor_name, action)
    name = f"{main_header_name}_{self.header_variant}"

    return toAlnum(name)


def get_anim_enum(self, actor_name: str, action: Action) -> str:
    if self.override_enum:
        return self.custom_enum
    anim_name = self.get_anim_name(actor_name, action)
    enum_name = anim_name.upper()
    if anim_name == enum_name:
        enum_name = f"_{enum_name}"
    return enum_name


def get_int_flags(self):
    flags: int = 0
    for i, flag in enumerate(FLAG_PROPS):
        flags |= 1 << i if getattr(self, flag) else 0
    return flags


# Action properties utility
def update_header_variant_numbers(self):
    for i, variant in enumerate(self.headers):
        variant.header_variant = i


def get_anim_file_name(self, action: Action):
    if self.override_file_name:
        name = self.custom_file_name
    else:
        name = f"anim_{action.name}.inc.c"

    # Replace any invalid characters with an underscore
    # TODO: Could this be an issue anywhere else in fast64?
    name = re.sub(r'[/\\?%*:|"<>]', " ", name)

    return name


def get_max_frame(self, action: Action) -> int:
    if self.override_max_frame:
        return self.custom_max_frame

    loop_ends: list[int] = [getFrameInterval(action)[1]]
    for header in self.headers:
        loop_end = header.get_frame_range(action)[2]
        loop_ends.append(loop_end)

    return max(loop_ends)


def get_enum_and_header_names(self, action: Action, actor_name: str):
    return [
        (header.get_anim_enum(actor_name, action), header.get_anim_name(actor_name, action)) for header in self.headers
    ]
