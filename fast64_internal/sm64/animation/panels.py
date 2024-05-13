from bpy.utils import register_class, unregister_class
from bpy.types import Context, Panel

from ...utility import draw_and_check_tab
from ...panels import SM64_Panel

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..settings.properties import SM64_Properties
    from .properties import AnimProps


class SceneAnimationPanel(SM64_Panel):
    bl_idname = "SM64_PT_anim_panel"
    bl_label = "SM64 Animations"
    goal = "Export Object/Actor/Anim"

    def draw(self, context: Context):
        col = self.layout.column()
        sm64_props: SM64_Properties = context.scene.fast64.sm64
        animation_props: AnimProps = sm64_props.animation
        animation_props.draw_props(
            col,
            sm64_props.export_type,
            sm64_props.show_importing_menus,
            sm64_props.import_rom,
        )


class ObjectAnimationPanel(Panel):
    bl_label = "Object Animation Inspector"
    bl_idname = "OBJECT_PT_SM64_anim_panel"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "bone"
    bl_options = {"HIDE_HEADER"}

    @classmethod
    def poll(cls, context: Context):
        if not context.object or context.object.type != "ARMATURE":
            return False
        scene = context.scene
        if scene.gameEditorMode != "SM64":
            return False
        scene_goal = scene.fast64.sm64.goal
        return scene_goal == "All" or scene_goal == "Export Object/Actor/Anim"

    def draw(self, context: Context):
        col = self.layout.column()
        sm64_props: SM64_Properties = context.scene.fast64.sm64
        animation_props: AnimProps = context.object.fast64.sm64.animation
        if draw_and_check_tab(col, animation_props, "object_menu_tab", icon="ANIM"):
            animation_props.draw_props(
                col,
                sm64_props.export_type,
                sm64_props.show_importing_menus,
                sm64_props.import_rom,
            )
        col.separator()


panels = (
    SceneAnimationPanel,
    ObjectAnimationPanel,
)


def anim_panel_register():
    for cls in panels:
        register_class(cls)


def anim_panel_unregister():
    for cls in reversed(panels):
        unregister_class(cls)
