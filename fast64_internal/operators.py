import bpy, mathutils, math
from bpy.utils import register_class, unregister_class
from .utility import *
from .f3d.f3d_material import *


def addMaterialByName(obj, matName, preset):
    if matName in bpy.data.materials:
        bpy.ops.object.material_slot_add()
        obj.material_slots[0].material = bpy.data.materials[matName]
    else:
        material = createF3DMat(obj, preset=preset)
        material.name = matName


class AddWaterBox(bpy.types.Operator):
    # set bl_ properties
    bl_idname = "object.add_water_box"
    bl_label = "Add Water Box"
    bl_options = {"REGISTER", "UNDO", "PRESET"}

    scale: bpy.props.FloatProperty(default=10)
    preset: bpy.props.StringProperty(default="Shaded Solid")
    matName: bpy.props.StringProperty(default="water_mat")

    def setEmptyType(self, emptyObj):
        return None

    def execute(self, context):
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        bpy.ops.object.select_all(action="DESELECT")

        location = mathutils.Vector(bpy.context.scene.cursor.location)
        bpy.ops.mesh.primitive_plane_add(size=2 * self.scale, enter_editmode=False, align="WORLD", location=location[:])
        planeObj = context.view_layer.objects.active
        planeObj.ignore_collision = True
        planeObj.name = "Water Box Mesh"

        addMaterialByName(planeObj, self.matName, self.preset)

        location += mathutils.Vector([0, 0, -self.scale])
        bpy.ops.object.empty_add(type="CUBE", radius=self.scale, align="WORLD", location=location[:])
        emptyObj = context.view_layer.objects.active
        emptyObj.name = "Water Box"
        self.setEmptyType(emptyObj)

        parentObject(planeObj, emptyObj)

        return {"FINISHED"}


class WarningOperator(bpy.types.Operator):
    """Extension of Operator that allows collecting and displaying warnings"""

    warnings = set()

    def reset_warnings(self):
        self.warnings.clear()

    def add_warning(self, warning: str):
        self.warnings.add(warning)

    def show_warnings(self):
        if len(self.warnings):
            self.report({"WARNING"}, "Operator completed with warnings:")
            for warning in self.warnings:
                self.report({"WARNING"}, warning)
            self.reset_warnings()


def translation_rotation_from_mtx(mtx: mathutils.Matrix):
    """Strip scale from matrix"""
    t, r, _ = mtx.decompose()
    return Matrix.Translation(t) @ r.to_matrix().to_4x4()


def scale_mtx_from_vector(scale: mathutils.Vector):
    return mathutils.Matrix.Diagonal(scale[0:3]).to_4x4()


def rotate_bounds(bounds, mtx: mathutils.Matrix):
    return [(mtx @ mathutils.Vector(b)).to_tuple() for b in bounds]


def copy_object_and_apply(obj: bpy.types.Object, apply_scale=False, apply_modifiers=False):
    if apply_scale or apply_modifiers:
        # it's a unique mesh, use object name
        obj["instanced_mesh_name"] = obj.name

        obj.original_name = obj.name
        if apply_scale:
            obj["original_mtx"] = translation_rotation_from_mtx(mathutils.Matrix(obj["original_mtx"]))

    obj_copy = obj.copy()
    obj_copy.data = obj_copy.data.copy()

    if apply_modifiers:
        # In order to correctly apply modifiers, we have to go through blender and add the object to the collection, then apply modifiers
        prev_active = bpy.context.view_layer.objects.active
        bpy.context.collection.objects.link(obj_copy)
        obj_copy.select_set(True)
        bpy.context.view_layer.objects.active = obj_copy
        for modifier in obj_copy.modifiers:
            attemptModifierApply(modifier)

        bpy.context.view_layer.objects.active = prev_active

    obj_copy.parent = None
    # reset transformations
    obj_copy.location = mathutils.Vector([0.0, 0.0, 0.0])
    obj_copy.scale = mathutils.Vector([1.0, 1.0, 1.0])
    obj_copy.rotation_quaternion = mathutils.Quaternion([1, 0, 0, 0])

    mtx = transform_mtx_blender_to_n64()
    if apply_scale:
        mtx = mtx @ scale_mtx_from_vector(obj.scale)

    obj_copy.data.transform(mtx)
    # Flag used for finding these temp objects
    obj_copy["temp_export"] = True

    # Override for F3D culling bounds (used in addCullCommand)
    bounds_mtx = transform_mtx_blender_to_n64()
    if apply_scale:
        bounds_mtx = bounds_mtx @ scale_mtx_from_vector(obj.scale)  # apply scale if needed
    obj_copy["culling_bounds"] = rotate_bounds(obj_copy.bound_box, bounds_mtx)


def yield_children(obj: bpy.types.Object):
    yield obj
    if obj.children:
        for o in obj.children:
            yield from yield_children(o)


def store_original_mtx():
    active_obj = bpy.context.view_layer.objects.active
    for obj in yield_children(active_obj):
        obj["original_mtx"] = obj.matrix_local


def store_original_meshes(add_warning: Callable[[str], None]):
    """
    - Creates new objects at 0, 0, 0 with shared mesh
    - Original mesh name is saved to each object
    """
    instanced_meshes = set()
    active_obj = bpy.context.view_layer.objects.active
    for obj in yield_children(active_obj):
        if obj.type != "EMPTY":
            has_modifiers = len(obj.modifiers) != 0
            has_uneven_scale = not obj_scale_is_unified(obj)
            shares_mesh = obj.data.users > 1
            can_instance = not has_modifiers and not has_uneven_scale
            should_instance = can_instance and (shares_mesh or obj.scaleFromGeolayout)

            if should_instance:
                # add `_shared_mesh` to instanced name because `obj.data.name` can be the same as object names
                obj["instanced_mesh_name"] = f"{obj.data.name}_shared_mesh"
                obj.original_name = obj.name

                if obj.data.name not in instanced_meshes:
                    instanced_meshes.add(obj.data.name)
                    copy_object_and_apply(obj)
            else:
                if shares_mesh and has_modifiers:
                    add_warning(
                        f'Object "{obj.name}" cannot be instanced due to having modifiers so an extra displaylist will be created. Remove modifiers to allow instancing.'
                    )
                if shares_mesh and has_uneven_scale:
                    add_warning(
                        f'Object "{obj.name}" cannot be instanced due to uneven object scaling and an extra displaylist will be created. Set all scale values to the same value to allow instancing.'
                    )

                copy_object_and_apply(obj, apply_scale=True, apply_modifiers=has_modifiers)
    bpy.context.view_layer.objects.active = active_obj


def cleanupTempMeshes():
    """Delete meshes that have been duplicated for instancing"""
    remove_data = []
    for obj in bpy.data.objects:
        if obj.get("temp_export"):
            remove_data.append(obj.data)
            bpy.data.objects.remove(obj)
        else:
            if obj.get("instanced_mesh_name"):
                del obj["instanced_mesh_name"]
            if obj.get("original_mtx"):
                del obj["original_mtx"]

    for data in remove_data:
        data_type = type(data)
        if data_type == bpy.types.Mesh:
            bpy.data.meshes.remove(data)
        elif data_type == bpy.types.Curve:
            bpy.data.curves.remove(data)


class ObjectDataExporter(WarningOperator):
    """Operator that uses warnings and can store original matrixes and meshes for use in exporting"""

    def store_object_data(self):
        store_original_mtx()
        store_original_meshes(self.add_warning)

    def cleanup_temp_object_data(self):
        cleanupTempMeshes()
