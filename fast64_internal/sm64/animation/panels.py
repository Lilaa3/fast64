from bpy.utils import register_class, unregister_class
from bpy.types import Context, Panel

from ...panels import SM64_Panel

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..settings.properties import SM64_Properties


class SM64_AnimPanel(SM64_Panel):
    bl_idname = "SM64_PT_export_anim"
    bl_label = "SM64 Animations"
    goal = "Export Object/Actor/Anim"

    def draw(self, context: Context):
        sm64_props: SM64_Properties = context.scene.fast64.sm64
        sm64_props.animation.draw_props(
            self.layout.column(),
            sm64_props.export_type,
            sm64_props.show_importing_menus,
            sm64_props.import_rom,
        )


class SM64_ObjAnimPanel(Panel):
    bl_label = "Object Animation Inspector"
    bl_idname = "OBJECT_PT_SM64_Obj_Anim_Inspector"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "object"
    bl_options = {"HIDE_HEADER"}

    @classmethod
    def poll(cls, context):
        scene = context.scene
        if scene.gameEditorMode != "SM64":
            return False
        scene_goal = scene.fast64.sm64.goal
        return scene_goal == "All" or scene_goal == "Export Object/Actor/Anim"

    def draw(self, context: Context):
        box = self.layout.box().column()
        box.box().label(text=self.bl_label)
        sm64_props: SM64_Properties = context.scene.fast64.sm64
        context.object.fast64.sm64.animation.draw_props(
            self.layout.column(),
            sm64_props.export_type,
            sm64_props.show_importing_menus,
            sm64_props.import_rom,
        )


panels = (
    SM64_AnimPanel,
    SM64_ObjAnimPanel,
)


def anim_panel_register():
    for cls in panels:
        register_class(cls)


def anim_panel_unregister():
    for cls in reversed(panels):
        unregister_class(cls)
