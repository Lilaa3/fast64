import bpy
from bpy.utils import register_class, unregister_class

from ...utility import draw_and_check_tab
from ...panels import SM64_Panel


class SM64_CollisionPanel(bpy.types.Panel):
    bl_label = "SM64 Collision"
    bl_idname = "MATERIAL_PT_SM64_Collision_Inspector"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "material"
    bl_options = {"HIDE_HEADER"}

    @classmethod
    def poll(cls, context):
        return context.scene.gameEditorMode == "SM64" and context.material is not None

    def draw(self, context):
        box = self.layout.box().column()
        collision_props = context.material.fast64.sm64.collision
        if draw_and_check_tab(box, collision_props, "material_menu_tab"):
            collision_props.draw_props(box, context.scene.fast64.sm64.collision.format)


class SM64_ExportCollisionPanel(SM64_Panel):
    bl_idname = "SM64_PT_export_collision"
    bl_label = "SM64 Collision"
    goal = "Object/Actor/Anim"

    def draw(self, context):
        sm64_props = context.scene.fast64.sm64
        sm64_props.collision.draw_props(self.layout, sm64_props.export_type)


panels = [SM64_CollisionPanel, SM64_ExportCollisionPanel]


def collision_panels_register():
    for cls in panels:
        register_class(cls)


def collision_panels_unregister():
    for cls in reversed(panels):
        unregister_class(cls)
