from bpy.utils import register_class, unregister_class
from bpy.types import Context

from ...utility_anim import is_action_stashed, CreateAnimData, AddBasicAction, StashAction
from ...panels import SM64_Panel

from .utility import get_anim_actor_name, get_anim_props, get_selected_action, dma_structure_context
from .operators import SM64_ExportAnim, SM64_ExportAnimTable

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..settings.properties import SM64_Properties
    from ..sm64_objects import SM64_CombinedObjectProperties
    from properties import SM64_ActionProperty


# Base
class AnimationPanel(SM64_Panel):
    bl_label = "SM64 Animation Inspector"
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

    def draw(self, context: Context):
        sm64_props: SM64_Properties = context.scene.fast64.sm64
        combined_props: SM64_CombinedObjectProperties = sm64_props.combined_export

        if sm64_props.export_type != "C":
            combined_props.draw_anim_props(self.layout, sm64_props.export_type, dma_structure_context(context))
            SM64_ExportAnimTable.draw_props(self.layout)
        if not (context.object and context.object.type == "ARMATURE"):
            self.layout.box().label(text="No selected armature")
        else:
            self.layout.box().label(text=f'Armature "{context.object.name}"')


class ObjAnimPanelMain(ObjAnimPanel):
    bl_parent_id = "OBJECT_PT_context_object"

    def draw(self, context: Context):
        sm64_props: SM64_Properties = context.scene.fast64.sm64
        get_anim_props(context).draw_props(
            self.layout, sm64_props.export_type, sm64_props.combined_export.export_header_type
        )


# Action tab


class AnimationPanelAction(AnimationPanel):
    bl_label = "Action Inspector"

    def draw(self, context: Context):
        col = self.layout.column()

        if context.object.animation_data is None:
            col.box().label(text="Select object has no animation data")
            CreateAnimData.draw_props(col)
            action = None
        else:
            col.prop(context.object.animation_data, "action", text="Selected Action")
            action = get_selected_action(context.object, False)
        if action is None:
            AddBasicAction.draw_props(col)
            return

        if not is_action_stashed(context.object, action):
            warn_col = col.column()
            StashAction.draw_props(warn_col, action=action.name)
            warn_col.alert = True

        sm64_props: SM64_Properties = context.scene.fast64.sm64
        if sm64_props.export_type != "C":
            SM64_ExportAnim.draw_props(col)
        action_props: SM64_ActionProperty = action.fast64.sm64
        action_props.draw_props(
            layout=col,
            action=action,
            specific_variant=None,
            in_table=False,
            updates_table=get_anim_props(context).update_table,
            draw_file_name=sm64_props.export_type != "Binary",
            export_type=sm64_props.export_type,
            actor_name=get_anim_actor_name(context),
            gen_enums=get_anim_props(context).table.gen_enums,
            dma=dma_structure_context(context),
        )


class SceneAnimPanelAction(AnimationPanelAction, SceneAnimPanel):
    bl_idname = "SM64_PT_anim_panel_action"

    @classmethod
    def poll(cls, context: Context):
        return context.object and context.object.type == "ARMATURE" and SceneAnimPanel.poll(context)


class ObjAnimPanelAction(AnimationPanelAction, ObjAnimPanel):
    bl_idname = "OBJECT_PT_SM64_anim_action"


class ObjAnimPanelTable(ObjAnimPanel):
    bl_label = "Table"
    bl_idname = "OBJECT_PT_SM64_anim_table"

    def draw(self, context: Context):
        sm64_props: SM64_Properties = context.scene.fast64.sm64
        get_anim_props(context).table.draw_props(
            self.layout,
            dma_structure_context(context),
            get_anim_props(context).update_table,
            sm64_props.export_type,
            get_anim_actor_name(context),
        )


# Importing tab


class AnimationPanelImport(AnimationPanel):
    bl_label = "Importing"
    import_panel = True

    def draw(self, context: Context):
        sm64_props: SM64_Properties = context.scene.fast64.sm64
        sm64_props.animation.importing.draw_props(self.layout, sm64_props.import_rom, sm64_props.decomp_path)


class SceneAnimPanelImport(SceneAnimPanel, AnimationPanelImport):
    bl_idname = "SM64_PT_anim_panel_import"

    @classmethod
    def poll(cls, context: Context):
        return context.object and context.object.type == "ARMATURE" and AnimationPanelImport.poll(context)


class ObjAnimPanelImport(ObjAnimPanel, AnimationPanelImport):
    bl_idname = "OBJECT_PT_SM64_anim_panel_import"


classes = (
    ObjAnimPanelMain,
    ObjAnimPanelTable,
    ObjAnimPanelAction,
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
