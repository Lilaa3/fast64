from bpy.utils import register_class, unregister_class
from bpy.types import Context

from ...panels import SM64_Panel

from .utility import get_anim_actor_name, get_animation_props, get_selected_action, dma_structure_context
from .operators import SM64_ExportAnim, SM64_ExportAnimTable

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..settings.properties import SM64_Properties, SM64_ActionProperty
    from ..sm64_objects import SM64_CombinedObjectProperties


# Base
class AnimationPanel(SM64_Panel):
    bl_label = "SM64 Animations"
    goal = "Object/Actor/Anim"


# Base panels
class SceneAnimPanel(AnimationPanel):
    bl_idname = "SM64_PT_anim"
    bl_parent_id = bl_idname


class ObjAnimPanel(AnimationPanel):
    bl_idname = "OBJECT_PT_SM64_anim"
    bl_context = "object"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    object_type = {"ARMATURE"}
    bl_parent_id = bl_idname


# Main tab
class SceneAnimPanelMain(SceneAnimPanel):
    bl_parent_id = ""

    @classmethod
    def poll(cls, context):
        sm64_props: SM64_Properties = context.scene.fast64.sm64
        if sm64_props.export_type == "C" and not sm64_props.show_importing_menus:
            return False
        return super().poll(context)

    def draw(self, context: Context):
        sm64_props: SM64_Properties = context.scene.fast64.sm64
        combined_props: SM64_CombinedObjectProperties = sm64_props.combined_export
        if sm64_props.export_type == "C":
            return
        combined_props.draw_anim_props(self.layout, sm64_props.export_type)
        SM64_ExportAnimTable.draw_props(self.layout)


class ObjAnimPanelMain(ObjAnimPanel):
    bl_parent_id = "OBJECT_PT_context_object"

    def draw(self, context: Context):
        sm64_props: SM64_Properties = context.scene.fast64.sm64
        context.object.data.fast64.sm64.animation.draw_props(
            self.layout, sm64_props.export_type, sm64_props.combined_export.export_header_type
        )


# Action tab


class AnimationPanelAction(AnimationPanel):
    bl_label = "Action Inspector"

    def draw(self, context: Context):  # TODO: standard func for getting the action
        sm64_props: SM64_Properties = context.scene.fast64.sm64
        scene_anim_props = sm64_props.animation
        if context.object and context.object.type == "ARMATURE":
            show_file_name, gen_enums = (
                sm64_props.export_type != "Binary",
                context.object.data.fast64.sm64.animation.table.gen_enums,
            )
        else:
            show_file_name, gen_enums = "", True
        self.layout.prop(scene_anim_props, "selected_action")
        action = scene_anim_props.selected_action or get_selected_action(context.object)
        if action is None:
            return
        if sm64_props.export_type != "C":
            SM64_ExportAnim.draw_props(self.layout)
        action_props: SM64_ActionProperty = action.fast64.sm64
        action_props.draw_props(
            layout=self.layout,
            action=action,
            specific_variant=None,
            in_table=False,
            draw_file_name=show_file_name,
            export_type=sm64_props.export_type,
            actor_name=get_anim_actor_name(context),
            gen_enums=gen_enums,
            dma=dma_structure_context(context),
        )


class SceneAnimPanelAction(AnimationPanelAction, SceneAnimPanel):
    bl_idname = "SM64_PT_anim_panel_action"


class ObjAnimPanelAction(AnimationPanelAction, ObjAnimPanel):
    bl_idname = "OBJECT_PT_SM64_anim_action"


class ObjAnimPanelTable(ObjAnimPanel):
    bl_label = "Table"
    bl_idname = "OBJECT_PT_SM64_anim_table"

    def draw(self, context: Context):
        sm64_props: SM64_Properties = context.scene.fast64.sm64
        anim_props = context.object.data.fast64.sm64.animation
        anim_props.table.draw_props(
            self.layout,
            dma_structure_context(context),
            sm64_props.export_type,
            get_anim_actor_name(context),
        )


# Importing tab


class AnimationPanelImport(AnimationPanel):
    bl_label = "Importing"
    import_panel = True

    def draw(self, context: Context):
        sm64_props: SM64_Properties = context.scene.fast64.sm64
        get_animation_props(context).importing.draw_props(self.layout, sm64_props.import_rom, sm64_props.decomp_path)


class SceneAnimPanelImport(SceneAnimPanel, AnimationPanelImport):
    bl_idname = "SM64_PT_anim_panel_import"


class ObjAnimPanelImport(ObjAnimPanel, AnimationPanelImport):
    bl_idname = "OBJECT_PT_SM64_anim_panel_import"


classes = (
    ObjAnimPanelMain,
    ObjAnimPanelTable,
    SceneAnimPanelMain,
    SceneAnimPanelAction,
    SceneAnimPanelImport,
)


def anim_panel_register():
    for cls in classes:
        register_class(cls)


def anim_panel_unregister():
    for cls in reversed(classes):
        unregister_class(cls)
