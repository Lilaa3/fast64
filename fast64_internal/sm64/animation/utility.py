import dataclasses
import math
import re

import bpy
from mathutils import Euler, Quaternion, Vector
from bpy.types import Context, Object, Action, PoseBone

from ...utility_anim import getFrameInterval
from ...utility import findStartBones, PluginError, toAlnum
from ..sm64_geolayout_bone import animatableBoneTypes

from .constants import FLAG_PROPS


def animation_operator_checks(context: Context, requires_animation=True, multiple_objects=False):
    if len(context.selected_objects) == 0 and context.object is None:
        raise PluginError("No armature selected.")
    if not multiple_objects and len(context.selected_objects) > 1:
        raise PluginError("Multiple objects selected at once.")

    for obj in context.selected_objects:
        if obj.type != "ARMATURE":
            raise PluginError(f'Selected object "{obj.name}" is not an armature.')
        if requires_animation and obj.animation_data is None:
            raise PluginError(f'Armature "{obj.name}" has no animation data.')


def get_animation_props(context: Context) -> "AnimProperty":
    if context.space_data.type != "VIEW_3D" and context.object and context.object.type == "ARMATURE":
        return context.object.data.fast64.sm64.animation
    return context.scene.fast64.sm64.animation


def get_action(name: str):
    if name == "":
        raise PluginError("Empty action name.")
    if not name in bpy.data.actions:
        raise PluginError(f"Action ({name}) is not in this file´s action data.")
    return bpy.data.actions[name]


def sm64_to_radian(signed_angle: int):
    unsigned_angle = signed_angle + (1 << 16)
    degree = unsigned_angle * (360.0 / (2**16))
    return math.radians(degree % 360.0)


def get_anim_pose_bones(armature_obj: Object) -> list[PoseBone]:
    bones_to_process: list[str] = findStartBones(armature_obj)
    current_bone = armature_obj.data.bones[bones_to_process[0]]
    anim_bones = []

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


def get_frame_range(action: Action, header_props: "HeaderProperty") -> tuple[int, int, int]:
    if header_props.manual_loop:
        return (header_props.start_frame, header_props.loop_start, header_props.loop_end)
    loop_start, loop_end = getFrameInterval(action)
    return (0, loop_start, loop_end + 1)


def get_anim_name(actor_name: str, action: Action, header_props: "HeaderProperty") -> str:
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


def get_anim_enum(actor_name: str, action: Action, header_props: "HeaderProperty") -> str:
    if header_props.set_custom_enum:
        return header_props.custom_enum
    anim_name = get_anim_name(actor_name, action, header_props)
    enum_name = anim_name.upper()
    if anim_name == enum_name:
        enum_name = f"_{enum_name}"
    return enum_name


def get_int_flags(header_props: "HeaderProperty"):
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


def get_element_header(element_props: "TableElementProperty", use_reference: bool) -> "HeaderProperty":
    if use_reference and element_props.reference:
        return None
    action = get_element_action(element_props, use_reference)
    if not action:
        return None
    return action.fast64.sm64.headers[element_props.variant]


def get_element_action(element_props: "TableElementProperty", use_reference: bool) -> Action:
    if use_reference and element_props.reference:
        return None
    return element_props.action_prop


def get_table_name(table_props: "TableProperty", actor_name: str) -> str:
    if table_props.use_custom_table_name:
        return table_props.custom_table_name
    return f"{actor_name}_anims"


def get_enum_list_name(table_props: "TableProperty", actor_name: str):
    table_name = get_table_name(table_props, actor_name)
    return table_name.title().replace("_", "")


def get_enum_list_end(table_props: "TableProperty", actor_name: str):
    table_name = get_table_name(table_props, actor_name)
    return f"{table_name.upper()}_END"


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
        a2 += (-2 if a1 < a2 else 2) * math.pi
    return a2


def can_interpolate(time_frames: list[tuple[int, Vector]], threshold: float):
    assert len(time_frames) >= 3
    time_start, frame_start = time_frames[0]
    time_end, frame_end = time_frames[-1]
    inbetween_frames = time_frames[1:-1]
    time_difference = time_end - time_start
    for time, frame in inbetween_frames:
        time_step = time - time_start
        interpolated_frame = frame_start + ((frame_end - frame_start) * time_step / time_difference)
        dist = value_distance(frame, interpolated_frame)
        if dist > threshold:
            return False
    return True


@dataclasses.dataclass
class FrameStore:
    frames: dict[int, Vector] = dataclasses.field(default_factory=dict)

    @property
    def sorted_frames(self):
        return sorted(self.frames.items(), key=lambda x: x[0])

    def add(self, timestamp: int, frame: Vector):
        self.frames[timestamp] = frame

    def clean(self, threshold: float):
        if not self.frames:
            return
        sorted_frames = self.sorted_frames
        cleaned = FrameStore()
        i = 0
        while i < len(sorted_frames):
            sucess = None
            if i and value_distance(sorted_frames[i - 1][1], sorted_frames[i][1]) <= threshold:
                sucess = i + 1
            for j in range(i, len(sorted_frames)):
                frames = sorted_frames[i : j + 1]
                if len(frames) >= 3 and can_interpolate(frames, threshold):
                    sucess = j
            frame = sorted_frames[i]
            if sucess:
                i = sucess
            cleaned.add(*frame)
            i += 1
        self.frames = cleaned.frames  # Update frames with cleaned frames

    def populate_action(self, action: Action, pose_bone: PoseBone, path: str):
        for property_index in range(3):
            f_curve = action.fcurves.new(
                data_path=pose_bone.path_from_id(path),
                index=property_index,
                action_group=pose_bone.name,
            )
            for time, frame in self.sorted_frames:
                f_curve.keyframe_points.insert(time, frame[property_index])


@dataclasses.dataclass
class RotationFrameStore(FrameStore):
    def add_rotation_frame(self, timestamp: int, rotation: Quaternion):
        self.add(timestamp, Vector(rotation))

    @property
    def quaternion(self):
        return [(i, Quaternion(x)) for i, x in self.sorted_frames]

    def get_euler(self, order: str):
        return [(i, x.to_euler(order)) for i, x in self.quaternion]

    @property
    def axis_angle(self):
        return [(i, x.to_axis_angle()) for i, x in self.quaternion]

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
            for frame, rotation in rotations:
                if rotation_mode == "AXIS_ANGLE":
                    rotation = [rotation[1]] + list(rotation[0])
                f_curve.keyframe_points.insert(frame, rotation[property_index])


@dataclasses.dataclass
class AnimationBone:
    translation: FrameStore = dataclasses.field(default_factory=FrameStore)
    rotation: RotationFrameStore = dataclasses.field(default_factory=RotationFrameStore)
    scale: FrameStore = dataclasses.field(default_factory=FrameStore)

    def read_pairs(self, pairs: list["AnimationPair"]):
        array: list[int] = []
        max_frame = max(len(pair.values) for pair in pairs)
        array = [[x.get_frame(frame) for x in pairs] for frame in range(max_frame)]
        return array

    def read_translation(self, pairs: list["AnimationPair"], scale: float):
        for frame, translation in enumerate(self.read_pairs(pairs)):
            self.translation.add(frame, Vector(translation) / scale)

    def continuity_filter(self, frames: list[Euler]):
        prev = Euler([0, 0, 0])
        for frame, euler in enumerate(frames):
            euler = Euler([naive_flip_diff(prev[i], x) for i, x in enumerate(euler)])
            flipped_euler = Euler([naive_flip_diff(prev[i], x) for i, x in enumerate(flip_euler(euler))])
            distance = value_distance(prev, euler)
            distance_flipped = value_distance(prev, flipped_euler)
            if distance_flipped < distance:
                euler = flipped_euler
            frames[frame] = prev = euler
        return frames

    def read_rotation(self, pairs: list["AnimationPair"], continuity_filter: bool):
        frames: list[Euler] = [Euler([sm64_to_radian(x) for x in rot]) for rot in self.read_pairs(pairs)]
        if continuity_filter:
            frames = self.continuity_filter(frames)
        for frame, rot in enumerate(frames):
            self.rotation.add_rotation_frame(frame, rot.to_quaternion())

    def clean(self, translation_threshold: float, rotation_threshold: float, scale_threshold: float):
        self.translation.clean(translation_threshold)
        self.rotation.clean(rotation_threshold)
        self.scale.clean(scale_threshold)

    def populate_action(self, action: Action, pose_bone: PoseBone):
        self.translation.populate_action(action, pose_bone, "location")
        self.rotation.populate_action(action, pose_bone)
        self.scale.populate_action(action, pose_bone, "scale")


def populate_action(action: Action, bones: list[PoseBone], anim_data: list[AnimationBone], force_quaternion: bool):
    for pose_bone, bone_data in zip(bones, anim_data):
        if force_quaternion:
            pose_bone.rotation_mode = "QUATERNION"
        bone_data.populate_action(action, pose_bone)


def clean_object_animations(context: Context):
    animation_operator_checks(context, True, True)
    selected_objects = context.selected_objects if context.selected_objects else context.object
    for obj in selected_objects:
        continue
    raise NotImplementedError("Not implemented")
