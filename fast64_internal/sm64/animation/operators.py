import bpy
from bpy.utils import register_class, unregister_class
from bpy.types import Context, Object, Scene, Action
from bpy.props import (
    EnumProperty,
    StringProperty,
    IntProperty,
)

from ...operators import OperatorBase, SearchEnumOperatorBase
from ...utility import copyPropertyGroup

from .importing import import_all_mario_animations, import_animations
from .exporting import export_animation, export_animation_table
from .utility import (
    get_action,
    animation_operator_checks,
    get_anim_name,
    get_frame_range,
    update_header_variant_numbers,
    get_animation_props,
)
from .constants import marioAnimationNames, enumAnimationTables, enumAnimatedBehaviours

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..settings.properties import SM64_Properties
    from .properties import (
        SM64_AnimProps,
        SM64_AnimImportProps,
        SM64_ActionProps,
    )


def emulate_no_loop(scene: Scene):
    if scene.gameEditorMode != "SM64":
        return
    animation_props: SM64_AnimProps = scene.fast64.sm64.animation
    played_action: Action = animation_props.played_action

    if (
        not played_action
        or animation_props.played_header >= len(played_action.fast64.sm64.headers)
        or not bpy.context.screen.is_animation_playing
    ):
        animation_props.played_action = None
        return
    frame = scene.frame_current

    header_props = played_action.fast64.sm64.headers[animation_props.played_header]
    loop_start, loop_end = get_frame_range(played_action, header_props)[1:3]
    if header_props.backwards:
        if frame < loop_start:
            if header_props.no_loop:
                scene.frame_set(loop_start)
            else:
                scene.frame_set(loop_end - 1)
    elif frame >= loop_end:
        if header_props.no_loop:
            scene.frame_set(loop_end - 1)
        else:
            scene.frame_set(loop_start)


class SM64_PreviewAnimOperator(OperatorBase):
    bl_idname = "scene.sm64_preview_animation"
    bl_label = "Preview Animation"
    bl_options = {"REGISTER", "UNDO", "PRESET"}
    context_mode = "OBJECT"

    played_header: IntProperty(name="Header", min=0, default=0)
    played_action: StringProperty(name="Action")

    def execute_operator(self, context: Context):
        animation_operator_checks(context)

        scene = context.scene
        scene_anim_props = scene.fast64.sm64.animation
        if context.space_data.type != "VIEW_3D" and context.space_data.context == "OBJECT":
            animation_props: SM64_AnimProps = context.object.fast64.sm64.animation
        else:
            animation_props: SM64_AnimProps = scene_anim_props

        if self.played_action:
            played_action = get_action(self.played_action)
        else:
            played_action = animation_props.selected_action
        context.selected_objects[0].animation_data.action = played_action
        action_props: SM64_ActionProps = played_action.fast64.sm64
        assert self.played_header < len(action_props.headers), "Invalid header index"
        header_props = action_props.headers[self.played_header]
        start_frame = get_frame_range(played_action, header_props)[0]
        scene.frame_set(start_frame)
        scene.render.fps = 30

        if bpy.context.screen.is_animation_playing:
            bpy.ops.screen.animation_play()  # in case it was already playing, stop it
        bpy.ops.screen.animation_play()

        scene_anim_props.played_header = self.played_header
        scene_anim_props.played_action = played_action

        return {"FINISHED"}


class SM64_TableOperations(OperatorBase):
    bl_idname = "scene.sm64_table_operations"
    bl_label = "Table Operations"
    bl_description = "Move, remove, clear or add table elements"
    bl_options = {"UNDO"}

    index: IntProperty()
    op_name: StringProperty()
    action_name: StringProperty(name="Action")
    header_variant: IntProperty()

    def execute_operator(self, context: Context):
        table_elements = get_animation_props(context).table.elements

        if self.index != -1:
            table_element = table_elements[self.index]
        else:
            table_element = None
        if self.op_name == "MOVE_UP":
            table_elements.move(self.index, self.index - 1)
        elif self.op_name == "MOVE_DOWN":
            table_elements.move(self.index, self.index + 1)
        elif self.op_name == "ADD":
            table_elements.add()
            if self.action_name and self.header_variant:
                table_elements[-1].set_variant(bpy.data.actions[self.action_name], self.header_variant)
            elif table_element:
                copyPropertyGroup(table_element, table_elements[-1])
                table_elements.move(len(table_elements) - 1, self.index + 1)
        elif self.op_name == "ADD_ALL":
            action = bpy.data.actions[self.action_name]
            for header_variant in range(len(action.fast64.sm64.headers)):
                table_elements.add()
                table_elements[-1].set_variant(action, header_variant)
        elif self.op_name == "REMOVE":
            table_elements.remove(self.index)
        if self.op_name == "CLEAR":
            table_elements.clear()

        return {"FINISHED"}


class SM64_AnimVariantOperations(OperatorBase):
    bl_idname = "scene.sm64_header_variant_operations"
    bl_label = "Header Variant Operations"
    bl_description = "Move, remove, clear or add variants"
    bl_options = {"UNDO"}

    index: IntProperty()
    op_name: StringProperty()
    action_name: StringProperty(name="Action")

    def execute_operator(self, context):
        action = bpy.data.actions[self.action_name]
        action_props: SM64_ActionProps = action.fast64.sm64
        variants = action_props.header_variants
        position = len(variants) - 1 if self.index == -1 else self.index
        if self.op_name == "MOVE_UP":
            variants.move(self.index, position - 1)
        elif self.op_name == "MOVE_DOWN":
            variants.move(self.index, position + 1)
        elif self.op_name == "ADD":
            variants.add()
            added_variant = variants[-1]
            added_variant.action = action

            copyPropertyGroup(action_props.headers[self.index + 1], added_variant)

            variants.move(len(variants) - 1, position)
            update_header_variant_numbers(action_props)

            added_variant.expand_tab = True
            added_variant.override_name = False
            added_variant.override_enum = False
            added_variant.custom_name = get_anim_name(
                context.scene.fast64.sm64.animation.actor_name, action, added_variant
            )
        elif self.op_name == "REMOVE":
            variants.remove(self.index)
        if self.op_name == "CLEAR":
            variants.clear()
        update_header_variant_numbers(action_props)


class SM64_ExportAnimTable(OperatorBase):
    bl_idname = "scene.sm64_export_anim_table"
    bl_label = "Export"
    bl_description = "Exports the animation table found in the call context, scene or object"
    bl_options = {"REGISTER", "UNDO", "PRESET"}
    context_mode = "OBJECT"

    def execute_operator(self, context: Context):
        export_animation_table(context)
        self.report({"INFO"}, "Exported animation table successfully!")


class SM64_ExportAnim(OperatorBase):
    bl_idname = "scene.sm64_export_anim"
    bl_label = "Export"
    bl_description = "Exports the select action found in the call context, scene or object"
    bl_options = {"REGISTER", "UNDO", "PRESET"}
    context_mode = "OBJECT"

    def execute_operator(self, context: Context):
        export_animation(context)
        self.report({"INFO"}, "Exported animation successfully!")


class SM64_ImportAllMarioAnims(OperatorBase):
    bl_idname = "scene.sm64_import_mario_anims"
    bl_label = "Import All Mario Animations"
    bl_description = "Imports all of Mario's animations into the call context's animation propreties, scene or object"
    bl_options = {"REGISTER", "UNDO", "PRESET"}
    context_mode = "OBJECT"

    def execute_operator(self, context):
        import_all_mario_animations(context)


class SM64_ImportAnim(OperatorBase):
    bl_idname = "scene.sm64_import_anim"
    bl_label = "Import Animation(s)"
    bl_description = "Imports animations into the call context's animation propreties, scene or object"
    bl_options = {"REGISTER", "UNDO", "PRESET"}
    context_mode = "OBJECT"

    def execute_operator(self, context):
        import_animations(context)


class SM64_SearchMarioAnim(SearchEnumOperatorBase):
    bl_idname = "scene.search_mario_anim_enum_operator"
    bl_property = "mario_animations"
    mario_animations: EnumProperty(items=marioAnimationNames)

    def update_enum(self, context: Context):
        get_animation_props(context).importing.mario_animation = self.mario_animations


class SM64_SearchTableAnim(SearchEnumOperatorBase):
    bl_idname = "scene.search_anim_table_enum_operator"
    bl_property = "preset"
    preset: EnumProperty(items=enumAnimationTables)

    def update_enum(self, context: Context):
        get_animation_props(context).importing.preset = self.preset


class SM64_SearchAnimatedBehavior(SearchEnumOperatorBase):
    bl_idname = "scene.search_animated_behavior_enum_operator"
    bl_property = "behaviour"
    behaviour: EnumProperty(items=enumAnimatedBehaviours)

    def update_enum(self, context: Context):
        get_animation_props(context).table.behaviour = self.behaviour


class CleanObjectAnimations(OperatorBase):
    bl_description = "Clean object animations"
    bl_idname = "object.clean_object_animations"
    bl_label = "Clean Object Animations"
    bl_options = {"REGISTER", "UNDO", "PRESET"}

    def execute_operator(self, context: Context):
        pass


operators = (
    SM64_ExportAnimTable,
    SM64_ExportAnim,
    SM64_PreviewAnimOperator,
    SM64_TableOperations,
    SM64_AnimVariantOperations,
    SM64_ImportAnim,
    SM64_ImportAllMarioAnims,
    SM64_SearchMarioAnim,
    SM64_SearchAnimatedBehavior,
    SM64_SearchTableAnim,
    CleanObjectAnimations,
)


def anim_operator_register():
    for cls in operators:
        register_class(cls)

    bpy.app.handlers.frame_change_pre.append(emulate_no_loop)


def anim_operator_unregister():
    for cls in reversed(operators):
        unregister_class(cls)

    if emulate_no_loop in bpy.app.handlers.frame_change_pre:
        bpy.app.handlers.frame_change_pre.remove(emulate_no_loop)