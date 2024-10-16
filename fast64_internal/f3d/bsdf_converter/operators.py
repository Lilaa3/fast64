import copy

import bpy
from bpy.utils import register_class, unregister_class
from bpy.props import EnumProperty, BoolProperty
from bpy.types import Context, Object, Material

from ...operators import OperatorBase
from ...utility import PluginError

from .converter import obj_to_f3d, obj_to_bsdf

converter_enum = [("Object", "Selected Objects", "Object"), ("Scene", "Scene", "Scene")]


class F3D_ConvertBSDF(OperatorBase):
    bl_idname = "scene.f3d_convert_to_bsdf"
    bl_label = "Convert F3D to BSDF"
    bl_options = {"REGISTER", "UNDO", "PRESET"}
    icon = "MATERIAL"

    direction: EnumProperty(items=[("F3D", "BSDF To F3D", "F3D"), ("BSDF", "F3D To BSDF", "BSDF")])
    converter_type: EnumProperty(items=converter_enum)
    backup: BoolProperty(default=True, name="Backup")
    put_alpha_into_color: BoolProperty(default=False, name="Put Alpha Into Color (F3D -> BSDF)")

    def execute_operator(self, context: Context):
        collection = context.scene.collection
        view_layer = context.view_layer
        scene = context.scene

        if self.converter_type == "Object":
            objs = context.selected_objects
        elif self.converter_type == "Scene":
            objs = scene.objects

        if not objs:
            raise PluginError("No objects to convert.")

        objs: list[Object] = [obj for obj in objs if obj.type == "MESH"]
        original_names = [obj.name for obj in objs]
        new_objs: list[Object] = []
        backup_collection = None

        try:
            materials: dict[Material, Material] = {}
            for old_obj in objs:
                obj = old_obj.copy()
                obj.data = old_obj.data.copy()
                scene.collection.objects.link(obj)
                view_layer.objects.active = obj
                new_objs.append(obj)
                if self.direction == "F3D":
                    obj_to_f3d(obj, materials)
                elif self.direction == "BSDF":
                    obj_to_bsdf(obj, materials, self.put_alpha_into_color)

            bpy.ops.object.select_all(action="DESELECT")
            if self.backup:
                name = "BSDF -> F3D Backup" if self.direction == "F3D" else "F3D -> BSDF Backup"
                if name in bpy.data.collections:
                    backup_collection = bpy.data.collections[name]
                else:
                    backup_collection = bpy.data.collections.new(name)
                    scene.collection.children.link(backup_collection)

            for old_obj, obj, name in zip(objs, new_objs, original_names):
                for collection in copy.copy(old_obj.users_collection):
                    collection.objects.unlink(old_obj)  # remove old object from current collection
                view_layer.objects.active = obj
                obj.select_set(True)
                bpy.ops.object.make_single_user(type="SELECTED_OBJECTS")
                obj.select_set(False)

                obj.name = name
                if self.backup:
                    old_obj.name = f"{name}_backup"
                    backup_collection.objects.link(old_obj)
                    view_layer.objects.active = old_obj
                else:
                    bpy.data.objects.remove(old_obj)
            if self.backup:
                for layer_collection in view_layer.layer_collection.children:
                    if layer_collection.collection == backup_collection:
                        layer_collection.exclude = True
        except Exception as exc:
            for obj in new_objs:
                bpy.data.objects.remove(obj)
            if backup_collection is not None:
                bpy.data.collections.remove(backup_collection)
            raise exc
        self.report({"INFO"}, "Done.")


classes = (F3D_ConvertBSDF,)


def bsdf_converter_ops_register():
    for cls in classes:
        register_class(cls)


def bsdf_converter_ops_unregister():
    for cls in reversed(classes):
        unregister_class(cls)
