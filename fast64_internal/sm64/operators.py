import os
import bpy

from bpy.props import (
    StringProperty,
    FloatProperty,
    BoolProperty,
    IntProperty,
)

from ..utility import PluginError, raisePluginError, get_mode_set_from_context_mode

from .geolayout.utility import createBoneGroups


class SM64_AddrConv(bpy.types.Operator):
    # set bl_ properties
    bl_idname = "object.addr_conv"
    bl_label = "Convert Address"
    bl_options = {"REGISTER", "UNDO", "PRESET"}

    segToVirt: BoolProperty()

    def execute(self, context):
        romfileSrc = None
        try:
            scene = context.scene
            sm64_props = context.scene.fast64.sm64
            address = int(sm64_props.convertible_addr, 16)
            import_rom = sm64_props.import_rom
            romfileSrc = open(abspath(import_rom), "rb")
            checkExpanded(abspath(import_rom))
            levelParsed = parseLevelAtPointer(romfileSrc, level_pointers[scene.level_convert])
            segmentData = levelParsed.segmentData
            if self.segToVirt:
                ptr = decodeSegmentedAddr(address.to_bytes(4, "big"), segmentData)
                self.report({"INFO"}, "Virtual pointer is 0x" + format(ptr, "08X"))
            else:
                ptr = int.from_bytes(encodeSegmentedAddr(address, segmentData), "big")
                self.report({"INFO"}, "Segmented pointer is 0x" + format(ptr, "08X"))
            romfileSrc.close()
            return {"FINISHED"}
        except Exception as e:
            if romfileSrc is not None:
                romfileSrc.close()
            raisePluginError(self, e)
            return {"CANCELLED"}  # must return a set


class SM64_AddBoneGroups(bpy.types.Operator):
    # set bl_ properties
    bl_description = (
        "Add bone groups respresenting other node types in " + "SM64 geolayouts (ex. Shadow, Switch, Function)."
    )
    bl_idname = "object.add_bone_groups"
    bl_label = "Add Bone Groups"
    bl_options = {"REGISTER", "UNDO", "PRESET"}

    # Called on demand (i.e. button press, menu item)
    # Can also be called from operator search menu (Spacebar)
    def execute(self, context):
        try:
            if context.mode != "OBJECT" and context.mode != "POSE":
                raise PluginError("Operator can only be used in object or pose mode.")
            elif context.mode == "POSE":
                bpy.ops.object.mode_set(mode="OBJECT")

            if len(context.selected_objects) == 0:
                raise PluginError("Armature not selected.")
            elif type(context.selected_objects[0].data) is not bpy.types.Armature:
                raise PluginError("Armature not selected.")

            armatureObj = context.selected_objects[0]
            createBoneGroups(armatureObj)
        except Exception as e:
            raisePluginError(self, e)
            return {"CANCELLED"}

        self.report({"INFO"}, "Created bone groups.")
        return {"FINISHED"}  # must return a set


class SM64_CreateMetarig(bpy.types.Operator):
    # set bl_ properties
    bl_description = (
        "SM64 imported armatures are usually not good for "
        + "rigging. There are often intermediate bones between deform bones "
        + "and they don't usually point to their children. This operator "
        + "creates a metarig on armature layer 4 useful for IK."
    )
    bl_idname = "object.create_metarig"
    bl_label = "Create Animatable Metarig"
    bl_options = {"REGISTER", "UNDO", "PRESET"}

    # Called on demand (i.e. button press, menu item)
    # Can also be called from operator search menu (Spacebar)
    def execute(self, context):
        from .geolayout.sm64_geolayout_parser import generateMetarig

        try:
            if context.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")

            if len(context.selected_objects) == 0:
                raise PluginError("Armature not selected.")
            elif type(context.selected_objects[0].data) is not bpy.types.Armature:
                raise PluginError("Armature not selected.")

            armatureObj = context.selected_objects[0]
            generateMetarig(armatureObj)
        except Exception as e:
            raisePluginError(self, e)
            return {"CANCELLED"}

        self.report({"INFO"}, "Created metarig.")
        return {"FINISHED"}  # must return a set


def create_sm64_empty(name: str, type: str, location=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0)):
    context = bpy.context
    objects = bpy.data.objects

    num = 0
    while (num == 0 and name in objects) or f"{name}.{num}" in objects:
        num += 1
    if num > 0:
        name = f"{name}.{num}"

    bpy.ops.object.empty_add(type="CUBE", align="CURSOR", location=location, rotation=rotation)
    object = context.view_layer.objects.active
    object.name, object.sm64_obj_type = name, type
    # object.fast64.sm64.obj_type = "Level"

    return object


class SM64_CreateSimpleLevel(bpy.types.Operator):
    bl_idname = "object.create_simple_level"
    bl_label = "Create Simple Level"
    bl_options = {"REGISTER", "UNDO", "PRESET"}

    area_amount: IntProperty(name="Area Amount", default=1, min=1, max=8)
    add_death_plane: BoolProperty(name="Add Death Plane")


    def execute_operator(self, context):
        from ..f3d.f3d_material import getDefaultMaterialPreset, createF3DMat, add_f3d_mat_to_obj
        from ..utility import parentObject

        level_object = create_sm64_empty("Example Level", "Level Root", (0, 0, -2))

        preset = getDefaultMaterialPreset("Shaded Solid")
        example_mat = createF3DMat(None, preset)

        example_mat.name = "Grass Example"
        example_mat.f3d_mat.default_light_color = (0, 1, 0, 1)
        example_mat.fast64.sm64.collision.vanilla.simple_type = "SURFACE_NOISE_DEFAULT"

        preset = getDefaultMaterialPreset("Shaded Solid")
        death_mat = createF3DMat(None, preset)

        death_mat.name = "Death Plane"
        death_mat.fast64.sm64.collision.vanilla.simple_type = "SURFACE_DEATH_PLANE"

        for i in range(self.area_amount - 1, -1, -1): # Start from end to 0, prevents weird naming
            location_offset = (0, 25 * i, 0)

            area_num = i + 1
            area_object = create_sm64_empty(f"Area {area_num}", "Area Root", location_offset)
            area_object.areaIndex = area_num
            parentObject(level_object, area_object)

            bpy.ops.mesh.primitive_plane_add(size=10, align="CURSOR", location=location_offset)
            plane_obj = context.view_layer.objects.active
            plane_obj.name = "Mesh"
            plane_obj.data.name = "Mesh"
            add_f3d_mat_to_obj(plane_obj, example_mat)
            parentObject(area_object, plane_obj)

            if self.add_death_plane:
                bpy.ops.mesh.primitive_plane_add(size=25, align="CURSOR", location=(0, 25 * i, -25))
                death_plane_obj = context.view_layer.objects.active
                death_plane_obj.name = "(Collision Only) Death Plane"
                death_plane_obj.data.name = "Death Plane"
                death_plane_obj.ignore_render = True
                add_f3d_mat_to_obj(death_plane_obj, death_mat)
                parentObject(area_object, death_plane_obj)

    def execute(self, context):
        starting_context_mode = context.mode
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.select_all(action="DESELECT")
        try:
            self.execute_operator(context)
            bpy.ops.object.mode_set(mode=get_mode_set_from_context_mode(starting_context_mode))
            return {"FINISHED"}
        except Exception as e:
            bpy.ops.object.mode_set(mode=get_mode_set_from_context_mode(starting_context_mode))
            raisePluginError(self, e)
            return {"CANCELLED"}

from ..operators import AddWaterBox
class SM64_AddWaterBox(AddWaterBox):
    bl_idname = "object.sm64_add_water_box"

    scale: FloatProperty(default=10)
    preset: StringProperty(default="Shaded Solid")
    matName: StringProperty(default="sm64_water_mat")

    def setEmptyType(self, emptyObj):
        emptyObj.sm64_obj_type = "Water Box"
