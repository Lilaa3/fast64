import bpy
from bpy.utils import register_class, unregister_class
from .functions.expand import expandRom

from ...utility import (
    PluginError,
    raisePluginError
)

class SM64_ExpandROMOperator(bpy.types.Operator):
    bl_idname = "scene.sm64_expand_rom"
    bl_label = "Expand ROM"
    bl_options = {"REGISTER"}

    def executeOperation(self, context):
        expandRom(context)
        return {"FINISHED"}

    def execute(self, context):
        try:
            return self.executeOperation(context)
        except Exception as e:
            raisePluginError(self, e)
            return {"CANCELLED"}


sm64_expansion_operators = [SM64_ExpandROMOperator]


def sm64_expansion_operator_register():
    for cls in sm64_expansion_operators:
        register_class(cls)


def sm64_expansion_operator_unregister():
    for cls in reversed(sm64_expansion_operators):
        unregister_class(cls)
