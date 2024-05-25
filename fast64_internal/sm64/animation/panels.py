from bpy.utils import register_class, unregister_class
from bpy.types import Context

from ...panels import SM64_Panel

from .utility import get_animation_props

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..settings.properties import SM64_Properties


# Base
class AnimationPanel(SM64_Panel):
    bl_label = "SM64 Animations"
    goal = "Object/Actor/Anim"

    def draw(self, context: Context):
        sm64_props: SM64_Properties = context.scene.fast64.sm64
        get_animation_props(context).draw_props(self.layout, sm64_props.export_type)


# Base panels
class SceneAnimPanel(AnimationPanel):
    bl_idname = "SM64_PT_anim"
    bl_parent_id = bl_idname


class ObjAnimPanel(AnimationPanel):
    bl_idname = "OBJECT_PT_SM64_Animation_Inspector"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "object"
    object_type = {"ARMATURE"}
    bl_parent_id = bl_idname


# Main tab
class SceneAnimPanelMain(SceneAnimPanel):
    bl_parent_id = ""


class ObjAnimPanelMain(ObjAnimPanel):
    bl_parent_id = ""


# Action tab


class AnimationPanelAction(AnimationPanel):
    bl_label = "Action"

    def draw(self, context: Context):
        get_animation_props(context).draw_action(self.layout, context.scene.fast64.sm64.export_type)


class SceneAnimPanelAction(AnimationPanelAction, SceneAnimPanel):
    bl_idname = "SM64_PT_anim_panel_action"


class ObjAnimPanelAction(AnimationPanelAction, ObjAnimPanel):
    bl_idname = "DATA_PT_SM64_anim_panel_action"


# Table tab
class AnimationPanelTable(AnimationPanel):
    bl_label = "Table"

    def draw(self, context: Context):
        get_animation_props(context).draw_table(self.layout, context.scene.fast64.sm64.export_type)


class SceneAnimPanelTable(AnimationPanelTable, SceneAnimPanel):
    bl_idname = "SM64_PT_anim_panel_table"


class ObjAnimPanelTable(AnimationPanelTable, ObjAnimPanel):
    bl_idname = "DATA_PT_SM64_anim_panel_table"


# Tools tab
class AnimationPanelTools(AnimationPanel):
    bl_label = "Tools"

    def draw(self, context: Context):
        get_animation_props(context).draw_tools(self.layout)


class SceneAnimPanelTools(AnimationPanelTools, SceneAnimPanel):
    bl_idname = "SM64_PT_anim_panel_tools"


class ObjAnimPanelTools(AnimationPanelTools, ObjAnimPanel):
    bl_idname = "DATA_PT_SM64_anim_panel_tools"


# Importing tab


class AnimationPanelImport(AnimationPanel):
    bl_label = "Importing"
    import_panel = True

    def draw(self, context: Context):
        sm64_props: SM64_Properties = context.scene.fast64.sm64
        get_animation_props(context).importing.draw_props(self.layout, sm64_props.import_rom)


class SceneAnimPanelImport(SceneAnimPanel, AnimationPanelImport):
    bl_idname = "SM64_PT_anim_panel_import"


class ObjAnimPanelImport(ObjAnimPanel, AnimationPanelImport):
    bl_idname = "DATA_PT_SM64_anim_panel_import"


panels = (
    ObjAnimPanelMain,
    ObjAnimPanelAction,
    ObjAnimPanelTable,
    ObjAnimPanelImport,
    ObjAnimPanelTools,
    SceneAnimPanelMain,
    SceneAnimPanelAction,
    SceneAnimPanelTable,
    SceneAnimPanelImport,
    SceneAnimPanelTools,
)


def anim_panel_register():
    for cls in panels:
        register_class(cls)


def anim_panel_unregister():
    for cls in reversed(panels):
        unregister_class(cls)
