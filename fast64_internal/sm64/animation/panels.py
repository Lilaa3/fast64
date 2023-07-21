import bpy
from bpy.utils import register_class, unregister_class

from ..utility import box_sm64_panel
from ..panels import SM64_Panel

class SM64_ExportAnimPanel(SM64_Panel):
    bl_idname = "SM64_PT_export_anim"
    bl_label = "Animation Exporting"
    goal = "Object/Actor/Anim"

    def draw(self, context: bpy.types.Context):
        context.scene.fast64.sm64.anim_export.draw_props(context, box_sm64_panel(self.layout))


class SM64_ImportAnimPanel(SM64_Panel):
    bl_idname = "SM64_PT_import_anim"
    bl_label = "Animation Importing"
    goal = "Object/Actor/Anim"
    isImport = True

    def draw(self, context: bpy.types.Context):
        sm64Props = context.scene.fast64.sm64
        sm64Props.anim_import.draw_props(box_sm64_panel(self.layout))


sm64_anim_panels = [SM64_ExportAnimPanel, SM64_ImportAnimPanel]


def sm64_anim_panel_register():
    for cls in sm64_anim_panels:
        register_class(cls)


def sm64_anim_panel_unregister():
    for cls in reversed(sm64_anim_panels):
        unregister_class(cls)
