from bpy.types import Context

import bpy

from ...operators import OperatorBase

from ..f3d_material import createF3DMat, getDefaultMaterialPreset


class CreateDebugMat(OperatorBase):
    bl_idname = "object.create_debug_mat"
    bl_label = "Create Culling Debug Material"
    bl_options = {"REGISTER", "UNDO", "PRESET"}
    icon = "MATERIAL"

    def execute_operator(self, context: Context):
        mat = createF3DMat(obj=None, preset=getDefaultMaterialPreset("Shaded Solid"))
        context.scene.fast64.f3d.culling.debug_mat = mat
        self.report({"INFO"}, "Created new Fast3D material.")
        return {"FINISHED"}


classes = (CreateDebugMat,)


def register_culling_ops():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister_culling_ops():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
