from bpy.utils import register_class, unregister_class
from bpy.types import Context, Panel

from ...panels import SM64_Panel

from .utility import get_animation_props

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..settings.properties import SM64_Properties
    from .properties import AnimProperty


# Base
class AnimationPanel(Panel):
    bl_label = "SM64 Animations"

    def draw(self, context: Context):
        sm64_props: SM64_Properties = context.scene.fast64.sm64
        get_animation_props(context).draw_props(self.layout, sm64_props.export_type)


# Base panels
class SceneAnimPanel(AnimationPanel, SM64_Panel):
    bl_idname = "SM64_PT_anim"
    goal = "Object/Actor/Anim"
    bl_parent_id = bl_idname


class ObjAnimPanel(AnimationPanel):
    bl_idname = "OBJECT_PT_SM64_Animation_Inspector"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "object"
    bl_parent_id = bl_idname


# Main tab
class SceneAnimPanelMain(SceneAnimPanel):
    bl_parent_id = ""


class ObjAnimPanelMain(ObjAnimPanel):
    bl_parent_id = ""

    @classmethod
    def poll(cls, context: Context):
        if not context.object or context.object.type != "ARMATURE":
            return False
        scene = context.scene
        if scene.gameEditorMode != "SM64":
            return False
        scene_goal = scene.fast64.sm64.goal
        return scene_goal in {"All", "Object/Actor/Anim"}


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

    def draw(self, context: Context):
        get_animation_props(context).importing.draw_props(self.layout, context.scene.fast64.sm64.import_rom)


class SceneAnimPanelImport(SceneAnimPanel, AnimationPanelImport):
    bl_idname = "SM64_PT_anim_panel_import"
    import_panel = True


class ObjAnimPanelImport(ObjAnimPanel, AnimationPanelImport):
    bl_idname = "DATA_PT_SM64_anim_panel_import"

    @classmethod
    def poll(cls, context: Context):
        return context.scene.fast64.sm64.show_importing_menus


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
