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


def animation_operator_checks(context: Context, requires_animation=True):
    if len(context.selected_objects) == 0 and context.object is None:
        raise PluginError("No armature selected.")
    if len(context.selected_objects) > 1:
        raise PluginError("Multiple objects selected at once.")

    for obj in context.selected_objects:
        if obj.type != "ARMATURE":
            raise PluginError(f'Selected object "{obj.name}" is not an armature.')
        if requires_animation and obj.animation_data is None:
            raise PluginError(f'Armature "{obj.name}" has no animation data.')


def get_animation_props(context: Context) -> "SM64_AnimProperties":
    if context.space_data.type != "VIEW_3D" and context.object and context.object.type == "ARMATURE":
        return context.object.data.fast64.sm64.animation
    return context.scene.fast64.sm64.animation


def get_action(name: str):
    if name == "":
        raise ValueError("Empty action name.")
    if not name in bpy.data.actions:
        raise IndexError(f"Action ({name}) is not in this file´s action data.")
    return bpy.data.actions[name]


def get_selected_action(animation_props: "SM64_AnimProperties", armature: Object | None) -> Action:
    if animation_props.selected_action:
        return animation_props.selected_action
    elif armature:
        if armature.animation_data and armature.animation_data.action:
            return armature.animation_data.action
        raise ValueError(f'No action selected in armature "{armature.name}".')
    raise ValueError("No action selected in properties.")


def euler_to_quaternion(euler_angles: np.ndarray):
    """euler_angles is an array of shape (-1, 3)"""
    phi = euler_angles[:, 0]
    theta = euler_angles[:, 1]
    psi = euler_angles[:, 2]

    half_phi = phi / 2.0
    half_theta = theta / 2.0
    half_psi = psi / 2.0

    cos_half_phi = np.cos(half_phi)
    sin_half_phi = np.sin(half_phi)
    cos_half_theta = np.cos(half_theta)
    sin_half_theta = np.sin(half_theta)
    cos_half_psi = np.cos(half_psi)
    sin_half_psi = np.sin(half_psi)

    q_w = cos_half_phi * cos_half_theta * cos_half_psi + sin_half_phi * sin_half_theta * sin_half_psi
    q_x = sin_half_phi * cos_half_theta * cos_half_psi - cos_half_phi * sin_half_theta * sin_half_psi
    q_y = cos_half_phi * sin_half_theta * cos_half_psi + sin_half_phi * cos_half_theta * sin_half_psi
    q_z = cos_half_phi * cos_half_theta * sin_half_psi - sin_half_phi * sin_half_theta * cos_half_psi

    quaternions = np.vstack((q_w, q_x, q_y, q_z)).T  # shape (-1, 4)
    return quaternions


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
    if header_props.set_custom_name:
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


def get_anim_enum(actor_name: str, action: Action, header_props: "SM64_AnimHeaderProperties") -> str:
    if header_props.set_custom_enum:
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


def get_anim_file_name(action: Action, action_props: "SM64_ActionProperty") -> str:
    name = action_props.custom_file_name if action_props.use_custom_file_name else f"anim_{action.name}.inc.c"
    # Replace any invalid characters with an underscore
    # TODO: Could this be an issue anywhere else in fast64?
    name = re.sub(r'[/\\?%*:|"<>]', " ", name)
    return name


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


def get_table_name(table_props: "SM64_AnimTableProperties", actor_name: str) -> str:
    if table_props.use_custom_table_name:
        return table_props.custom_table_name
    return f"{actor_name}_anims"


def get_enum_list_name(table_props: "SM64_AnimTableProperties", actor_name: str):
    table_name = get_table_name(table_props, actor_name)
    return table_name.title().replace("_", "")


def get_enum_list_end(table_props: "SM64_AnimTableProperties", actor_name: str):
    table_name = get_table_name(table_props, actor_name)
    return f"{table_name.upper()}_END"


def value_distance(e1: Euler | list, e2: Euler | list) -> float:
    return math.sqrt((e1[0] - e2[0]) ** 2 + (e1[1] - e2[1]) ** 2 + (e1[2] - e2[2]) ** 2)


def flip_euler(euler: np.ndarray) -> np.ndarray:
    euler = euler.copy()
    euler[1] = -euler[1]
    euler += np.pi
    return euler


def naive_flip_diff(a1: np.ndarray, a2: np.ndarray) -> np.ndarray:
    diff = a1 - a2
    mask = np.abs(diff) > np.pi
    return a2 + mask * np.sign(diff) * 2 * np.pi


def can_interpolate(time_frames: list[tuple[int, Vector]], threshold: float):
    assert len(time_frames) >= 3
    time_start, frame_start = time_frames[0]
    time_end, frame_end = time_frames[-1]
    inbetween_frames = time_frames[1:-1]
    time_difference = time_end - time_start
    for time, frame in inbetween_frames:
        time_step = time - time_start
        interpolated_frame = frame_start + ((frame_end - frame_start) * time_step / time_difference)
        if value_distance(frame, interpolated_frame) > threshold:
            return False
    return True


@dataclasses.dataclass
class FrameStore:
    frames: np.ndarray = dataclasses.field(default_factory=list)

    def populate_action(self, action: Action, pose_bone: PoseBone, path: str):
        for property_index in range(3):
            f_curve = action.fcurves.new(
                data_path=pose_bone.path_from_id(path),
                index=property_index,
                action_group=pose_bone.name,
            )
            for time, frame in enumerate(self.frames):
                f_curve.keyframe_points.insert(time, frame[property_index])


@dataclasses.dataclass
class RotationFrameStore(FrameStore):
    @property
    def quaternion(self):
        return euler_to_quaternion(self.frames)

    def get_euler(self, order: str):
        if order == "XYZ":
            return self.frames
        return [Quaternion(x).to_euler(order) for x in self.quaternion]

    @property
    def axis_angle(self):
        for x in self.quaternion:
            x = Quaternion(x).to_axis_angle()
            yield [x[1]] + list(x[0])

    def populate_action(self, action: Action, pose_bone: PoseBone):
        rotation_mode = pose_bone.rotation_mode
        rotation_mode_name = {
            "QUATERNION": "rotation_quaternion",
            "AXIS_ANGLE": "rotation_axis_angle",
        }.get(rotation_mode, "rotation_euler")
        data_path = pose_bone.path_from_id(rotation_mode_name)

        size = 4
        if rotation_mode == "QUATERNION":
            rotations = self.quaternion
        elif rotation_mode == "AXIS_ANGLE":
            rotations = self.axis_angle
        else:
            rotations = self.get_euler(rotation_mode)
            size = 3
        for property_index in range(size):
            f_curve = action.fcurves.new(
                data_path=data_path,
                index=property_index,
                action_group=pose_bone.name,
            )
            for frame, rotation in enumerate(rotations):
                f_curve.keyframe_points.insert(frame, rotation[property_index])


@dataclasses.dataclass
class AnimationBone:
    translation: FrameStore = dataclasses.field(default_factory=FrameStore)
    rotation: RotationFrameStore = dataclasses.field(default_factory=RotationFrameStore)
    scale: FrameStore = dataclasses.field(default_factory=FrameStore)

    def read_pairs(self, pairs: list["AnimationPair"]):
        pair_count = len(pairs)
        max_length = max(len(pair.values) for pair in pairs)
        result = np.empty((max_length, pair_count), dtype=np.int16)

        for i, pair in enumerate(pairs):
            current_length = len(pair.values)
            result[:current_length, i] = pair.values
            result[current_length:, i] = pair.values[-1]
        return result

    def read_translation(self, pairs: list["AnimationPair"], scale: float):
        self.translation.frames = self.read_pairs(pairs) / scale

    def continuity_filter(self, frames: np.ndarray) -> np.ndarray:
        if len(frames) <= 1:
            return frames

        # There is no way to fully vectorize this function
        prev = frames[0]
        for frame, euler in enumerate(frames):
            euler = naive_flip_diff(prev, euler)
            flipped_euler = naive_flip_diff(prev, flip_euler(euler))
            if np.all((prev - flipped_euler) ** 2 < (prev - euler) ** 2):
                euler = flipped_euler
            frames[frame] = prev = euler

        return frames

    def read_rotation(self, pairs: list["AnimationPair"], continuity_filter: bool):
        frames = self.read_pairs(pairs).astype(np.uint16).astype(np.float32)
        frames *= 360.0 / (2**16)
        frames = np.radians(frames)
        if continuity_filter:
            frames = self.continuity_filter(frames)
        self.rotation.frames = frames

    def populate_action(self, action: Action, pose_bone: PoseBone):
        self.translation.populate_action(action, pose_bone, "location")
        self.rotation.populate_action(action, pose_bone)


def populate_action(action: Action, bones: list[PoseBone], anim_data: list[AnimationBone], force_quaternion: bool):
    for pose_bone, bone_data in zip(bones, anim_data):
        if force_quaternion:
            pose_bone.rotation_mode = "QUATERNION"
        bone_data.populate_action(action, pose_bone)
