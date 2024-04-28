import ast
import copy
import dataclasses
import math

import bpy
from bpy.types import Object, Armature

from ...utility import findStartBones, PluginError, decodeSegmentedAddr
from ..sm64_geolayout_bone import animatableBoneTypes


@dataclasses.dataclass
class RomReading:
    """
    Simple class that simplifies reading data continously from a starting address.
    Accounts for insertable binary data.
    """

    def __init__(
        self,
        data: bytes,
        start_address: int,
        insertable_ptrs: list[int] | None = None,
        rom_data: bytes | None = None,
        segment_data: dict[int, tuple[int, int]] | None = None,
    ):
        self.start_address = start_address
        self.address = start_address
        self.data = data
        self.rom_data = rom_data
        if not insertable_ptrs:
            insertable_ptrs = []
        self.insertable_ptrs = insertable_ptrs
        self.segment_data = segment_data

    def branch(self, start_address: int | None = None, data: bytes | None = None):
        branch = RomReading(
            data if data else self.data,
            start_address if start_address else self.address,
            self.insertable_ptrs,
            self.rom_data,
            self.segment_data,
        )
        return branch

    def read_ptr(self):
        in_bytes = self.data[self.address : self.address + 4]
        self.address += 4
        ptr = int.from_bytes(in_bytes, "big", signed=False)

        if ptr == 0:
            return None

        if not ptr in self.insertable_ptrs and self.segment_data:
            ptr_in_bytes: bytes = ptr.to_bytes(4, "big")
            if ptr_in_bytes[0] not in self.segment_data:
                raise PluginError(f"Address {ptr} does not belong to the current segment.")
            return decodeSegmentedAddr(ptr_in_bytes, self.segment_data)
        return ptr

    def read_value(self, size, offset: int = None, signed=True):
        if offset:
            self.address = self.start_address + offset
        in_bytes = self.data[self.address : self.address + size]
        self.address += size
        return int.from_bytes(in_bytes, "big", signed=signed)


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
