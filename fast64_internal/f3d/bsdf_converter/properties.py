from bpy.utils import register_class, unregister_class
from bpy.types import PropertyGroup, UILayout
from bpy.props import EnumProperty, BoolProperty

from ...utility import prop_split, multilineLabel


class F3D_BSDFConverterProperties(PropertyGroup):
    """
    Properties in scene.fast64.f3d.bsdf_converter
    """

    converter_type: EnumProperty(items=[("Object", "Selected Objects", "Object"), ("Scene", "Scene", "Scene")])
    backup: BoolProperty(default=True, name="Backup")

    def draw_props(self, layout: UILayout):
        col = layout.column()
        prop_split(col, self, "converter_type", "Converter Type")
        col.prop(self, "backup")


classes = (F3D_BSDFConverterProperties,)


def bsdf_converter_props_register():
    for cls in classes:
        register_class(cls)


def bsdf_converter_props_unregister():
    for cls in reversed(classes):
        unregister_class(cls)
