from bpy.path import abspath
from bpy.utils import register_class, unregister_class
from bpy.types import Context

from ...panels import SM64_Panel


class SM64_GoddardPanel(SM64_Panel):
    bl_idname = "SM64_PT_goddard"
    bl_label = "SM64 Goddard"

    def draw(self, context: Context):
        sm64_props = context.scene.fast64.sm64
        sm64_props.goddard.draw_props(self.layout, abspath(sm64_props.decomp_path))


class SM64_GoddardImportPanel(SM64_Panel):
    bl_idname = "SM64_PT_import_goddard"
    bl_parent_id = "SM64_PT_goddard"
    bl_label = "Import Goddard"
    import_panel = True

    def draw(self, context: Context):
        sm64_props = context.scene.fast64.sm64
        sm64_props.goddard.importing.draw_props(self.layout, abspath(sm64_props.decomp_path))


classes = (SM64_GoddardPanel, SM64_GoddardImportPanel)


def goddard_panels_register():
    for cls in classes:
        register_class(cls)


def goddard_panels_unregister():
    for cls in classes:
        unregister_class(cls)
