from bpy.utils import register_class, unregister_class
from bpy.props import EnumProperty
from bpy.types import Context

from ...operators import OperatorBase

from .converter import obj_to_f3d, obj_to_bsdf

converter_enum = [("Object", "Selected Objects", "Object"), ("Scene", "Scene", "Scene")]


class F3D_ConvertF3DToBSDF(OperatorBase):
    bl_idname = "scene.f3d_convert_to_bsdf"
    bl_label = "Convert F3D to BSDF"
    bl_options = {"REGISTER", "UNDO", "PRESET"}
    icon = "MATERIAL"

    converter_type: EnumProperty(items=converter_enum)

    def execute_operator(self, context: Context):
        if self.converter_type == "Object":
            for obj in context.selected_objects:
                obj_to_f3d(obj)
        elif self.converter_type == "Scene":
            for obj in context.scene.objects:
                obj_to_f3d(obj)
        self.report({"INFO"}, "Done.")


class F3D_ConvertBSDFToF3D(OperatorBase):
    bl_idname = "scene.bsdf_convert_to_f3d"
    bl_label = "Convert BSDF to F3D"
    bl_options = {"REGISTER", "UNDO", "PRESET"}
    icon = "NODE_MATERIAL"

    converter_type: EnumProperty(items=converter_enum)

    def execute_operator(self, context: Context):
        if self.converter_type == "Object":
            for obj in context.selected_objects:
                obj_to_bsdf(obj)
        elif self.converter_type == "Scene":
            for obj in context.scene.objects:
                obj_to_bsdf(obj)
        self.report({"INFO"}, "Done.")


classes = (F3D_ConvertF3DToBSDF, F3D_ConvertBSDFToF3D)


def bsdf_converter_ops_register():
    for cls in classes:
        register_class(cls)


def bsdf_converter_ops_unregister():
    for cls in reversed(classes):
        unregister_class(cls)
