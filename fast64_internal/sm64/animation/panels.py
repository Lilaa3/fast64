from bpy.utils import register_class, unregister_class
from bpy.types import Context, Panel

from ...utility import draw_and_check_tab
from ...panels import SM64_Panel

from .utility import get_animation_props

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..settings.properties import SM64_Properties
    from .properties import AnimProperty


class SceneAnimationPanel(SM64_Panel):
    bl_idname = "SM64_PT_anim_panel"
    bl_label = "SM64 Animations"
    goal = "Object/Actor/Anim"

    def draw(self, context: Context):
        col = self.layout.column()
        sm64_props: SM64_Properties = context.scene.fast64.sm64
        anim_props: AnimProperty = get_animation_props(context)
        anim_props.draw_props(
            col,
            sm64_props.export_type,
            sm64_props.show_importing_menus,
            sm64_props.import_rom,
        )


class ObjectAnimationPanel(Panel):
    bl_label = "Animation Inspector"
    bl_idname = "DATA_PT_SM64_anim_panel"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "data"
    bl_options = {"HIDE_HEADER"}

    @classmethod
    def poll(cls, context: Context):
        if not context.object or context.object.type != "ARMATURE":
            return False
        scene = context.scene
        if scene.gameEditorMode != "SM64":
            return False
        scene_goal = scene.fast64.sm64.goal
        return scene_goal == "All" or scene_goal == "Object/Actor/Anim"

    def draw(self, context: Context):
        col = self.layout.column()
        sm64_props: SM64_Properties = context.scene.fast64.sm64
        anim_props: AnimProperty = get_animation_props(context)
        if draw_and_check_tab(col, anim_props, "object_menu_tab", icon="ANIM"):
            anim_props.draw_props(
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
