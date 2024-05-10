import bpy
from bpy.utils import register_class, unregister_class

from ..utility import box_sm64_panel
from ..panels import SM64_Panel

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
        box = box_sm64_panel(self.layout)
        box.box().label(text="Collision Inspector")
        context.material.fast64.sm64.collision.draw_props(box, context.scene.fast64.sm64)

class SM64_ExportCollisionPanel(SM64_Panel):
    bl_idname = "SM64_PT_export_collision"
    bl_label = "Collision Exporter"
    goal = "Object/Actor/Anim"

    # called every frame
    def draw(self, context):
        sm64_props = context.scene.fast64.sm64
        sm64_props.collision_export.draw_props(box_sm64_panel(self.layout), sm64_props.export)


panels = [SM64_CollisionPanel, SM64_ExportCollisionPanel]

def sm64_collision_panel_register():
    for cls in panels:
        register_class(cls)


def sm64_collision_panel_unregister():
    for cls in reversed(panels):
        unregister_class(cls)
