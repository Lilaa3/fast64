import math
import re

import bpy
from bpy.types import Context, Object, Armature, Action

from ...utility_anim import getFrameInterval
from ...utility import findStartBones, PluginError, toAlnum
from ..sm64_geolayout_bone import animatableBoneTypes

from .constants import FLAG_PROPS


def animation_operator_checks(context: Context, requires_animation_data=True):
    if len(context.selected_objects) > 1:
        raise PluginError("Multiple objects selected at once, make sure to select only one armature.")
    if len(context.selected_objects) == 0:
        raise PluginError("No armature selected.")

    armature_obj: Object = context.selected_objects[0]
    if armature_obj.type != "ARMATURE":
        raise PluginError("Selected object is not an armature.")
    if requires_animation_data and armature_obj.animation_data is None:
        raise PluginError("Armature has no animation data.")


def get_animation_props(context: Context) -> "SM64_AnimProps":
    scene = context.scene
    sm64_props: "SM64_Properties" = scene.fast64.sm64
    if context.space_data.type != "VIEW_3D" and context.object and context.object.type == "ARMATURE":
        return context.object.fast64.sm64.animation
    return sm64_props.animation


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


def get_frame_range(action: Action, header_props: "SM64_AnimHeaderProps") -> tuple[int, int, int]:
    if header_props.manual_frame_range:
        return (header_props.start_frame, header_props.loop_start, header_props.loop_end)
    loop_start, loop_end = getFrameInterval(action)
    return (0, loop_start, loop_end + 1)


def get_anim_name(actor_name: str, action: Action, header_props: "SM64_AnimHeaderProps") -> str:
    if header_props.override_name:
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


def get_anim_enum(actor_name: str, action: Action, header_props: "SM64_AnimHeaderProps") -> str:
    if header_props.override_enum:
        return header_props.custom_enum
    anim_name = get_anim_name(actor_name, action, header_props)
    enum_name = anim_name.upper()
    if anim_name == enum_name:
        enum_name = f"_{enum_name}"
    return enum_name


def get_int_flags(header_props: "SM64_AnimHeaderProps"):
    flags: int = 0
    for i, flag in enumerate(FLAG_PROPS):
        flags |= 1 << i if getattr(header_props, flag) else 0
    return flags


def update_header_variant_numbers(action_props: "SM64_ActionProps"):
    for i, variant in enumerate(action_props.headers):
        variant.header_variant = i


def get_anim_file_name(action: Action, action_props: "SM64_ActionProps") -> str:
    name = action_props.custom_file_name if action_props.override_file_name else f"anim_{action.name}.inc.c"
    # Replace any invalid characters with an underscore
    # TODO: Could this be an issue anywhere else in fast64?
    name = re.sub(r'[/\\?%*:|"<>]', " ", name)
    return name


def get_max_frame(action: Action, action_props: "SM64_ActionProps") -> int:
    if action_props.override_max_frame:
        return action_props.custom_max_frame

    loop_ends: list[int] = [getFrameInterval(action)[1]]
    for header_props in action_props.headers:
        loop_end = get_frame_range(action, header_props)[2]
        loop_ends.append(loop_end)

    return max(loop_ends)


def get_element_header(
    element_props: "SM64_AnimTableElementProps",
    use_reference: bool,
) -> "SM64_AnimHeaderProps":
    if use_reference and element_props.reference:
        return None
    action = get_element_action(element_props, use_reference)
    if not action:
        return None
    if element_props.use_main_variant:
        return action.fast64.sm64.header
    return action.fast64.sm64.headers[element_props.variant]


def get_element_action(element_props: "SM64_AnimTableElementProps", use_reference: bool) -> Action:
    if use_reference and element_props.reference:
        return None
    return element_props.action_prop


def get_anim_table_name(table_props: "SM64_AnimTableProps", actor_name: str) -> str:
    if table_props.override_table_name:
        return table_props.custom_table_name
    return f"{actor_name}_anims"
