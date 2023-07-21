import bpy
from bpy.utils import register_class, unregister_class

from ..panels import SM64_Panel

class SM64_ExpandRom(SM64_Panel):
    bl_idname = "SM64_PT_expand_rom"
    bl_label = "Expand ROM"
    isImport = True

    def draw(self, context: bpy.types.Context):
        sm64Props = context.scene.fast64.sm64
        col = self.layout.column()

        sm64Props.rom_expansion.draw_props(col.box()) 


sm64_expansion_panels = [SM64_ExpandRom]


def sm64_expansion_panel_register():
    register_class(SM64_ExpandRom)


def sm64_expansion_panel_unregister():
    unregister_class(SM64_ExpandRom)
