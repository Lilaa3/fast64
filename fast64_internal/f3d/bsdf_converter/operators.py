from bpy.utils import register_class, unregister_class

from ...operators import OperatorBase


class F3D_ConvertF3DToBSDF(OperatorBase):
    bl_idname = "scene.f3d_convert_to_bsdf"
    bl_label = "Convert F3D to BSDF"
    bl_options = {"REGISTER", "UNDO", "PRESET"}
    icon = "MATERIAL"


class F3D_ConvertBSDFToF3D(OperatorBase):
    bl_idname = "scene.bsdf_convert_to_f3d"
    bl_label = "Convert BSDF to F3D"
    bl_options = {"REGISTER", "UNDO", "PRESET"}
    icon = "NODE_MATERIAL"


classes = (F3D_ConvertF3DToBSDF, F3D_ConvertBSDFToF3D)


def bsdf_converter_ops_register():
    for cls in classes:
        register_class(cls)


def bsdf_converter_ops_unregister():
    for cls in reversed(classes):
        unregister_class(cls)
