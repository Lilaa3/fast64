import bpy
from bpy.utils import register_class, unregister_class
from bpy.types import Context, Scene, Action
from bpy.props import EnumProperty, StringProperty, IntProperty

from ...operators import OperatorBase, SearchEnumOperatorBase
from ...utility import copyPropertyGroup

from .importing import import_animations, get_enum_from_import_preset
from .exporting import export_animation, export_animation_table
from .utility import (
    get_action,
    animation_operator_checks,
    get_scene_anim_props,
    get_anim_props,
    get_anim_actor_name,
)
from .constants import enumAnimationTables, enumAnimatedBehaviours

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .properties import SM64_AnimProperties, SM64_AnimHeaderProperties, SM64_ActionProperty


def emulate_no_loop(scene: Scene):
    if scene.gameEditorMode != "SM64":
        return
    anim_props: SM64_AnimProperties = scene.fast64.sm64.animation
    played_action: Action = anim_props.played_action
    if not played_action:
        return
    if not bpy.context.screen.is_animation_playing or anim_props.played_header >= len(
        played_action.fast64.sm64.headers
    ):
        anim_props.played_action = None
        return

    frame = scene.frame_current
    header_props: SM64_AnimHeaderProperties = played_action.fast64.sm64.headers[anim_props.played_header]
    _start, loop_start, end = header_props.get_loop_points(played_action)
    if header_props.backwards:
        if frame < loop_start:
            if header_props.no_loop:
                scene.frame_set(loop_start)
            else:
                scene.frame_set(end - 1)
    elif frame >= end:
        if header_props.no_loop:
            scene.frame_set(end - 1)
        else:
            scene.frame_set(loop_start)


class SM64_PreviewAnim(OperatorBase):
    bl_idname = "scene.sm64_preview_animation"
    bl_label = "Preview Animation"
    bl_options = {"REGISTER", "UNDO", "PRESET"}
    context_mode = "OBJECT"
    icon = "PLAY"

    played_header: IntProperty(name="Header", min=0, default=0)
    played_action: StringProperty(name="Action")

    def execute_operator(self, context: Context):
        animation_operator_checks(context)
        played_action = get_action(self.played_action)
        scene = context.scene
        anim_props = scene.fast64.sm64.animation

        context.object.animation_data.action = played_action
        action_props: SM64_ActionProperty = played_action.fast64.sm64

        if self.played_header >= len(action_props.headers):
            raise ValueError("Invalid Header Index")
        header_props: SM64_AnimHeaderProperties = action_props.headers[self.played_header]
        start_frame = header_props.get_loop_points(played_action)[0]
        scene.frame_set(start_frame)
        scene.render.fps = 30

        if bpy.context.screen.is_animation_playing:
            bpy.ops.screen.animation_play()  # in case it was already playing, stop it
        bpy.ops.screen.animation_play()

        anim_props.played_header = self.played_header
        anim_props.played_action = played_action


class SM64_AnimTableOps(OperatorBase):
    bl_idname = "scene.sm64_table_operations"
    bl_label = "Table Operations"
    bl_description = "Move, remove, clear or add table elements"
    bl_options = {"UNDO"}

    index: IntProperty()
    op_name: StringProperty()
    action_name: StringProperty()
    header_variant: IntProperty()

    def execute_operator(self, context: Context):
        table_elements = get_anim_props(context).table.elements
        if self.op_name == "MOVE_UP":
            table_elements.move(self.index, self.index - 1)
        elif self.op_name == "MOVE_DOWN":
            table_elements.move(self.index, self.index + 1)
        elif self.op_name == "ADD":
            if self.index != -1:
                table_element = table_elements[self.index]
            table_elements.add()
            if self.action_name:  # set based on action variant
                table_elements[-1].set_variant(bpy.data.actions[self.action_name], self.header_variant)
            elif self.index != -1:  # copy from table
                copyPropertyGroup(table_element, table_elements[-1])
            if self.index != -1:
                table_elements.move(len(table_elements) - 1, self.index + 1)
        elif self.op_name == "ADD_ALL":
            action = bpy.data.actions[self.action_name]
            for header_variant in range(len(action.fast64.sm64.headers)):
                table_elements.add()
                table_elements[-1].set_variant(action, header_variant)
        elif self.op_name == "REMOVE":
            table_elements.remove(self.index)
        elif self.op_name == "CLEAR":
            table_elements.clear()
        else:
            raise NotImplementedError(f"Unimplemented table op {self.op_name}")


class SM64_AnimVariantOps(OperatorBase):
    bl_idname = "scene.sm64_header_variant_operations"
    bl_label = "Header Variant Operations"
    bl_description = "Move, remove, clear or add variants"
    bl_options = {"UNDO"}

    index: IntProperty()
    op_name: StringProperty()
    action_name: StringProperty()

    def execute_operator(self, context):
        action = bpy.data.actions[self.action_name]
        action_props: SM64_ActionProperty = action.fast64.sm64
        headers = action_props.headers
        variants = action_props.header_variants
        variant_position = self.index - 1
        if self.op_name == "MOVE_UP":
            if self.index - 1 == 0:
                variants.add()
                copyPropertyGroup(headers[0], variants[-1])
                copyPropertyGroup(headers[self.index], headers[0])
                copyPropertyGroup(variants[-1], headers[self.index])
                variants.remove(len(variants) - 1)
            else:
                variants.move(variant_position, variant_position - 1)
        elif self.op_name == "MOVE_DOWN":
            if self.index == 0:
                variants.add()
                copyPropertyGroup(headers[0], variants[-1])
                copyPropertyGroup(headers[1], headers[0])
                copyPropertyGroup(variants[-1], headers[1])
                variants.remove(len(variants) - 1)
            else:
                variants.move(variant_position, variant_position + 1)
        elif self.op_name == "ADD":
            variants.add()
            added_variant = variants[-1]

            copyPropertyGroup(action_props.headers[self.index], added_variant)
            variants.move(len(variants) - 1, variant_position + 1)
            action_props.update_variant_numbers()
            added_variant.action = action
            added_variant.expand_tab = True
            added_variant.use_custom_name = False
            added_variant.use_custom_enum = False
            added_variant.custom_name = added_variant.get_name(get_anim_actor_name(context), action)
        elif self.op_name == "REMOVE":
            variants.remove(variant_position)
        elif self.op_name == "CLEAR":
            variants.clear()
        else:
            raise NotImplementedError(f"Unimplemented table op {self.op_name}")
        action_props.update_variant_numbers()


class SM64_ExportAnimTable(OperatorBase):
    bl_idname = "scene.sm64_export_anim_table"
    bl_label = "Export Animation Table"
    bl_description = "Exports the animation table of the selected armature"
    bl_options = {"REGISTER", "UNDO", "PRESET"}
    context_mode = "OBJECT"
    icon = "EXPORT"

    @classmethod
    def poll(cls, context: Context):
        return context.mode == "OBJECT" and context.object and context.object.type == "ARMATURE"

    def execute_operator(self, context: Context):
        animation_operator_checks(context)
        export_animation_table(context, context.object)
        self.report({"INFO"}, "Exported animation table successfully!")


class SM64_ExportAnim(OperatorBase):
    bl_idname = "scene.sm64_export_anim"
    bl_label = "Export Individual Animation"
    bl_description = "Exports the select action of the selected armature"
    bl_options = {"REGISTER", "UNDO", "PRESET"}
    context_mode = "OBJECT"
    icon = "ACTION"

    @classmethod
    def poll(cls, context: Context):
        return context.mode == "OBJECT" and context.object and context.object.type == "ARMATURE"

    def execute_operator(self, context: Context):
        animation_operator_checks(context)
        export_animation(context, context.object)
        self.report({"INFO"}, "Exported animation successfully!")


class SM64_ImportAnim(OperatorBase):
    bl_idname = "scene.sm64_import_anim"
    bl_label = "Import Animation(s)"
    bl_description = "Imports animations into the call context's animation propreties, scene or object"
    bl_options = {"REGISTER", "UNDO", "PRESET"}
    context_mode = "OBJECT"
    icon = "IMPORT"

    def execute_operator(self, context):
        import_animations(context)


class SM64_SearchAnimPresets(SearchEnumOperatorBase):
    bl_idname = "scene.search_mario_anim_enum_operator"
    bl_property = "preset_animation"

    preset_animation: EnumProperty(items=get_enum_from_import_preset)

    def update_enum(self, context: Context):
        get_scene_anim_props(context).importing.preset_animation = self.preset_animation


class SM64_SearchAnimTablePresets(SearchEnumOperatorBase):
    bl_idname = "scene.search_anim_table_enum_operator"
    bl_property = "preset"

    preset: EnumProperty(items=enumAnimationTables)

    def update_enum(self, context: Context):
        get_scene_anim_props(context).importing.preset = self.preset


class SM64_SearchAnimatedBhvs(SearchEnumOperatorBase):
    bl_idname = "scene.search_animated_behavior_enum_operator"
    bl_property = "behaviour"

    behaviour: EnumProperty(items=enumAnimatedBehaviours)

    def update_enum(self, context: Context):
        get_anim_props(context).table.behaviour = self.behaviour


classes = (
    SM64_ExportAnimTable,
    SM64_ExportAnim,
    SM64_PreviewAnim,
    SM64_AnimTableOps,
    SM64_AnimVariantOps,
    SM64_ImportAnim,
    SM64_SearchAnimPresets,
    SM64_SearchAnimatedBhvs,
    SM64_SearchAnimTablePresets,
)


def anim_ops_register():
    for cls in classes:
        register_class(cls)

    bpy.app.handlers.frame_change_pre.append(emulate_no_loop)


def anim_ops_unregister():
    for cls in reversed(classes):
        unregister_class(cls)

    if emulate_no_loop in bpy.app.handlers.frame_change_pre:
        bpy.app.handlers.frame_change_pre.remove(emulate_no_loop)
