import math
import shutil, bpy, mathutils

from bpy.types import Bone, Object, Operator, Armature, Mesh, Material, PropertyGroup
from bpy.utils import register_class, unregister_class
from ..sm64_level_parser import parseLevelAtPointer
from ..utility import apply_basic_tweaks, checkExpanded, starSelectWarning

from ...utility import PluginError, applyRotation, prop_split, obj_scale_is_unified, raisePluginError, tempName
from ...f3d.f3d_material import sm64EnumDrawLayers
from ...operators import ObjectDataExporter
from .utility import createBoneGroups, addBoneToGroup

from ...f3d.f3d_gbi import DLFormat

from bpy.props import (
    StringProperty,
    IntProperty,
    FloatProperty,
    BoolProperty,
    PointerProperty,
    CollectionProperty,
    EnumProperty,
    FloatVectorProperty,
)

from .constants import (
    enumGeoStaticType,
)


def drawLayerWarningBox(layout, prop, data):
    warningBox = layout.box().column()
    prop_split(warningBox, prop, data, "Draw Layer (v3)")
    warningBox.label(text="This applies to v3 materials and down only.", icon="LOOP_FORWARDS")
    warningBox.label(text="This is moved to material settings in v4+.")


class SM64_DefineOptionOperations(bpy.types.Operator):
    bl_idname = "bone.sm64_define_option_operations"
    bl_label = ""
    bl_options = {"UNDO"}
    option: IntProperty()
    type: StringProperty()

    def executeOperator(self, context):
        boneProps = context.bone.fast64.sm64
        defineOptions = boneProps.define_variants

        if self.type == "MOVE_UP":
            defineOptions.move(self.option, self.option - 1)
        elif self.type == "MOVE_DOWN":
            defineOptions.move(self.option, self.option + 1)
        elif self.type == "ADD":
            defineOptions.add()
            if len(defineOptions) > 1:
                defineOptions[-1].copyDefineOption(defineOptions[self.option])
            defineOptions.move(len(defineOptions) - 1, self.option + 1)
        elif self.type == "REMOVE":
            defineOptions.remove(self.option)
        elif self.type == "CLEAR":
            for i in range(len(defineOptions)):
                defineOptions.remove(0)

        return {"FINISHED"}

    def execute(self, context):
        try:
            return self.executeOperator(context)
        except Exception as e:
            raisePluginError(self, e)
            return {"CANCELLED"}


class SM64_SwitchMaterialOperations(bpy.types.Operator):
    bl_idname = "bone.sm64_switch_material_operations"
    bl_label = ""
    bl_options = {"UNDO"}
    type: StringProperty()
    option: IntProperty()
    index: IntProperty()
    isSpecific: BoolProperty()
    array: StringProperty()

    def executeOperator(self, context):
        boneProps = context.bone.fast64.sm64
        if self.array == "Switch":
            option = boneProps.switch_options[self.option]
        elif self.array == "Define":
            option = boneProps.define_variants[self.option].option

        if self.isSpecific:
            array = option.specific_override_array
        else:
            array = option.specific_ignore_array

        if self.type == "MOVE_UP":
            array.move(self.index, self.index - 1)
        elif self.type == "MOVE_DOWN":
            array.move(self.index, self.index + 1)
        elif self.type == "ADD":
            array.add()
            if len(array) > 1:
                array[-1].copyMaterial(array[self.index])
            array.move(len(array) - 1, self.index + 1)
        elif self.type == "REMOVE":
            array.remove(self.index)
        elif self.type == "CLEAR":
            for i in range(len(array)):
                array.remove(0)

        return {"FINISHED"}

    def execute(self, context):
        try:
            return self.executeOperator(context)
        except Exception as e:
            raisePluginError(self, e)
            return {"CANCELLED"}


class SM64_SwitchOptionOperations(bpy.types.Operator):
    bl_idname = "bone.sm64_switch_option_operations"
    bl_label = ""
    bl_options = {"UNDO"}
    option: IntProperty()
    type: StringProperty()

    def executeOperator(self, context):
        boneProps = context.bone.fast64.sm64
        switchOptions = boneProps.switch_options

        if self.type == "MOVE_UP":
            switchOptions.move(self.option, self.option - 1)
        elif self.type == "MOVE_DOWN":
            switchOptions.move(self.option, self.option + 1)
        elif self.type == "ADD":
            switchOptions.add()
            if len(switchOptions) > 1:
                switchOptions[-1].copySwitchOption(switchOptions[self.option])
            switchOptions.move(len(switchOptions) - 1, self.option + 1)
        elif self.type == "REMOVE":
            switchOptions.remove(self.option)
        elif self.type == "CLEAR":
            for i in range(len(switchOptions)):
                switchOptions.remove(0)

        return {"FINISHED"}

    def execute(self, context):
        try:
            return self.executeOperator(context)
        except Exception as e:
            raisePluginError(self, e)
            return {"CANCELLED"}


def updateBone(self, context):
    from .properties import SM64_BoneProperties

    if not hasattr(context, "bone"):
        print("No bone in context.")
        return
    armatureObj = context.object

    bone = context.bone
    bone_props: SM64_BoneProperties = bone.fast64.sm64
    createBoneGroups(armatureObj)
    if bone_props.is_animatable():
        addBoneToGroup(armatureObj, bone.name, bone_props.geo_cmd)
        bpy.ops.object.mode_set(mode="POSE")
    else:
        addBoneToGroup(armatureObj, bone.name, None)
        bpy.ops.object.mode_set(mode="POSE")


class SM64_ExportGeolayoutObject(ObjectDataExporter):
    # set bl_ properties
    bl_idname = "object.sm64_export_geolayout_object"
    bl_label = "Export Object Geolayout"
    bl_options = {"REGISTER", "UNDO", "PRESET"}

    # Called on demand (i.e. button press, menu item)
    # Can also be called from operator search menu (Spacebar)
    def executeOperator(self, context):
        from .sm64_geolayout_writer import exportGeolayoutObjectC
        from ..properties import SM64_Properties, SM64_GlobalExportProperties, SM64_ExportGeolayoutProps

        scene = context.scene
        sm64_props: SM64_Properties = scene.fast64.sm64
        export_props: SM64_GlobalExportProperties = sm64_props.export
        geo_export_props: SM64_ExportGeolayoutProps = sm64_props.geolayout_export

        romfileOutput = None
        tempROM = None

        obj = None
        if context.mode != "OBJECT":
            raise PluginError("Operator can only be used in object mode.")
        if len(context.selected_objects) == 0:
            raise PluginError("Object not selected.")
        obj = context.active_object
        if not isinstance(obj.data, bpy.types.Mesh) and not (
            obj.data is None and (obj.sm64_obj_type == "None" or obj.sm64_obj_type == "Switch")
        ):
            raise PluginError('Selected object must be a mesh or an empty with the "None" or "Switch" type.')

        # finalTransform = mathutils.Matrix.Identity(4)
        scaleValue = bpy.context.scene.fast64.sm64.blender_to_sm64_scale
        finalTransform = mathutils.Matrix.Diagonal(mathutils.Vector((scaleValue, scaleValue, scaleValue))).to_4x4()

        try:
            self.store_object_data()

            # Rotate all armatures 90 degrees
            applyRotation([obj], math.radians(90), "X")

            saveTextures = bpy.context.scene.saveTextures

            if context.scene.fast64.sm64.export_type == "C":
                export_settings = sm64_props.get_export_settings_class()
                apply_basic_tweaks(export_settings)
                exportGeolayoutObjectC(
                    obj,
                    finalTransform,
                    scene.f3d_type,
                    scene.isHWv1,
                    geo_export_props.texture_dir,
                    saveTextures,
                    saveTextures and geo_export_props.separate_texture_def,
                    DLFormat.Static,
                    export_settings,
                    geo_export_props.name,
                )
                self.report({"INFO"}, "Success!")
            elif context.scene.fast64.sm64.export_type == "Insertable Binary":
                exportGeolayoutObjectInsertableBinary(
                    obj,
                    finalTransform,
                    context.scene.f3d_type,
                    context.scene.isHWv1,
                    bpy.path.abspath(bpy.context.scene.geoInsertableBinaryPath),
                    None,
                )
                self.report({"INFO"}, "Success! Data at " + context.scene.geoInsertableBinaryPath)
            else:
                tempROM = tempName(context.scene.fast64.sm64.output_rom)
                checkExpanded(bpy.path.abspath(context.scene.fast64.sm64.export_rom))
                romfileExport = open(bpy.path.abspath(context.scene.fast64.sm64.export_rom), "rb")
                shutil.copy(bpy.path.abspath(context.scene.fast64.sm64.export_rom), bpy.path.abspath(tempROM))
                romfileExport.close()
                romfileOutput = open(bpy.path.abspath(tempROM), "rb+")

                levelParsed = parseLevelAtPointer(romfileOutput, level_pointers[context.scene.levelGeoExport])
                segmentData = levelParsed.segmentData

                if context.scene.fast64.sm64.extend_bank_4:
                    ExtendBank0x04(romfileOutput, segmentData, defaultExtendSegment4)

                exportRange = [int(context.scene.geoExportStart, 16), int(context.scene.geoExportEnd, 16)]
                textDumpFilePath = (
                    bpy.path.abspath(context.scene.text_dump_path) if context.scene.dump_as_text else None
                )
                if context.scene.overwrite_model_load:
                    modelLoadInfo = (int(context.scene.modelLoadLevelScriptCmd, 16), int(context.scene.modelID, 16))
                else:
                    modelLoadInfo = (None, None)

                if context.scene.geoUseBank0:
                    addrRange, startRAM, geoStart = exportGeolayoutObjectBinaryBank0(
                        romfileOutput,
                        obj,
                        exportRange,
                        finalTransform,
                        *modelLoadInfo,
                        textDumpFilePath,
                        context.scene.f3d_type,
                        context.scene.isHWv1,
                        getAddressFromRAMAddress(int(context.scene.geoRAMAddr, 16)),
                        None,
                    )
                else:
                    addrRange, segPointer = exportGeolayoutObjectBinary(
                        romfileOutput,
                        obj,
                        exportRange,
                        finalTransform,
                        segmentData,
                        *modelLoadInfo,
                        textDumpFilePath,
                        context.scene.f3d_type,
                        context.scene.isHWv1,
                        None,
                    )

                romfileOutput.close()
                bpy.ops.object.select_all(action="DESELECT")
                obj.select_set(True)
                context.view_layer.objects.active = obj

                if os.path.exists(bpy.path.abspath(context.scene.fast64.sm64.output_rom)):
                    os.remove(bpy.path.abspath(context.scene.fast64.sm64.output_rom))
                os.rename(bpy.path.abspath(tempROM), bpy.path.abspath(context.scene.fast64.sm64.output_rom))

                if context.scene.geoUseBank0:
                    self.report(
                        {"INFO"},
                        f"Success! Geolayout at ({hex(addrRange[0])}, {hex(addrRange[1])}), \
                        to write to RAM Address {hex(startRAM)}, \
                        with geolayout starting at {hex(geoStart)}",
                    )
                else:
                    self.report(
                        {"INFO"},
                        "Success! Geolayout at ("
                        + hex(addrRange[0])
                        + ", "
                        + hex(addrRange[1])
                        + ") (Seg. "
                        + segPointer
                        + ").",
                    )

            self.cleanup_temp_object_data()
            applyRotation([obj], math.radians(-90), "X")
            self.show_warnings()
            return {"FINISHED"}  # must return a set

        except Exception as e:
            if context.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")

            self.cleanup_temp_object_data()
            applyRotation([obj], math.radians(-90), "X")

            if context.scene.fast64.sm64.export_type == "Binary":
                if romfileOutput is not None:
                    romfileOutput.close()
                if tempROM is not None and os.path.exists(bpy.path.abspath(tempROM)):
                    os.remove(bpy.path.abspath(tempROM))

            raise e

    def execute(self, context):
        try:
            return self.executeOperator(context)
        except Exception as e:
            raisePluginError(self, e)
            return {"CANCELLED"}


class SM64_ExportGeolayoutArmature(bpy.types.Operator):
    # set bl_ properties
    bl_idname = "object.sm64_export_geolayout_armature"
    bl_label = "Export Armature Geolayout"
    bl_options = {"REGISTER", "UNDO", "PRESET"}

    # Called on demand (i.e. button press, menu item)
    # Can also be called from operator search menu (Spacebar)
    def execute(self, context):
        from .sm64_geolayout_writer import get_all_armatures_objects, prepare_geolayout_export
        from ..properties import SM64_Properties, SM64_GlobalExportProperties, SM64_ExportGeolayoutProps
        from .sm64_geolayout_writer import exportGeolayoutArmatureC

        scene = context.scene
        sm64_props: SM64_Properties = scene.fast64.sm64
        geo_export_props: SM64_ExportGeolayoutProps = sm64_props.geolayout_export

        romfileOutput = None
        tempROM = None
        try:
            armatureObj = None
            if context.mode != "OBJECT":
                raise PluginError("Operator can only be used in object mode.")
            if len(context.selected_objects) == 0:
                raise PluginError("Armature not selected.")
            armatureObj = context.active_object
            if type(armatureObj.data) is not bpy.types.Armature:
                raise PluginError("Armature not selected.")

            if len(armatureObj.children) == 0 or not isinstance(armatureObj.children[0].data, bpy.types.Mesh):
                raise PluginError("Armature does not have any mesh children, or " + "has a non-mesh child.")

            obj = armatureObj.children[0]
            finalTransform = mathutils.Matrix.Identity(4)

            # get all switch option armatures as well
            linkedArmatures = get_all_armatures_objects(armatureObj)

            linkedArmatureDict = {}

            for linkedArmature in linkedArmatures:
                # IMPORTANT: Do this BEFORE rotation
                optionObjs = []
                for childObj in linkedArmature.children:
                    if isinstance(childObj.data, bpy.types.Mesh):
                        optionObjs.append(childObj)
                if len(optionObjs) > 1:
                    raise PluginError("Error: " + linkedArmature.name + " has more than one mesh child.")
                elif len(optionObjs) < 1:
                    raise PluginError("Error: " + linkedArmature.name + " has no mesh children.")
                linkedMesh = optionObjs[0]
                prepare_geolayout_export(linkedArmature, linkedMesh)
                linkedArmatureDict[linkedArmature] = linkedMesh
        except Exception as e:
            raisePluginError(self, e)
            return {"CANCELLED"}

        try:
            # Rotate all armatures 90 degrees
            applyRotation([armatureObj] + linkedArmatures, math.radians(90), "X")

            # You must ALSO apply object rotation after armature rotation.
            bpy.ops.object.select_all(action="DESELECT")
            for linkedArmature, linkedMesh in linkedArmatureDict.items():
                linkedMesh.select_set(True)
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.transform_apply(location=False, rotation=True, scale=True, properties=False)
            if sm64_props.export_type == "C":
                export_settings = sm64_props.get_export_settings_class()
                apply_basic_tweaks(export_settings)

                saveTextures = bpy.context.scene.saveTextures
                header, fileStatus = exportGeolayoutArmatureC(
                    armatureObj,
                    obj,
                    finalTransform,
                    scene.f3d_type,
                    scene.isHWv1,
                    geo_export_props.texture_dir,
                    saveTextures,
                    saveTextures and geo_export_props.separate_texture_def,
                    None,
                    DLFormat.Static,
                    export_settings,
                    geo_export_props.name
                )
                starSelectWarning(self, fileStatus)
                self.report({"INFO"}, "Success!")
            elif context.scene.fast64.sm64.export_type == "glTF":
                exportSm64GlTFGeolayout()
                self.report({"INFO"}, "Success!")
            elif context.scene.fast64.sm64.export_type == "Insertable Binary":
                exportGeolayoutArmatureInsertableBinary(
                    armatureObj,
                    obj,
                    finalTransform,
                    context.scene.f3d_type,
                    context.scene.isHWv1,
                    bpy.path.abspath(bpy.context.scene.geoInsertableBinaryPath),
                    None,
                )
                self.report({"INFO"}, "Success! Data at " + context.scene.geoInsertableBinaryPath)
            else:
                tempROM = tempName(context.scene.output_rom)
                checkExpanded(bpy.path.abspath(context.scene.fast64.sm64.export_rom))
                romfileExport = open(bpy.path.abspath(context.scene.fast64.sm64.export_rom), "rb")
                shutil.copy(bpy.path.abspath(context.scene.fast64.sm64.export_rom), bpy.path.abspath(tempROM))
                romfileExport.close()
                romfileOutput = open(bpy.path.abspath(tempROM), "rb+")

                levelParsed = parseLevelAtPointer(romfileOutput, level_pointers[context.scene.levelGeoExport])
                segmentData = levelParsed.segmentData

                if context.scene.fast64.sm64.extend_bank_4:
                    ExtendBank0x04(romfileOutput, segmentData, defaultExtendSegment4)

                exportRange = [int(context.scene.geoExportStart, 16), int(context.scene.geoExportEnd, 16)]
                textDumpFilePath = (
                    bpy.path.abspath(context.scene.text_dump_path) if context.scene.dump_as_text else None
                )
                if context.scene.overwrite_model_load:
                    modelLoadInfo = (int(context.scene.modelLoadLevelScriptCmd, 16), int(context.scene.modelID, 16))
                else:
                    modelLoadInfo = (None, None)

                if context.scene.geoUseBank0:
                    addrRange, startRAM, geoStart = exportGeolayoutArmatureBinaryBank0(
                        romfileOutput,
                        armatureObj,
                        obj,
                        exportRange,
                        finalTransform,
                        *modelLoadInfo,
                        textDumpFilePath,
                        context.scene.f3d_type,
                        context.scene.isHWv1,
                        getAddressFromRAMAddress(int(context.scene.geoRAMAddr, 16)),
                        None,
                    )
                else:
                    addrRange, segPointer = exportGeolayoutArmatureBinary(
                        romfileOutput,
                        armatureObj,
                        obj,
                        exportRange,
                        finalTransform,
                        segmentData,
                        *modelLoadInfo,
                        textDumpFilePath,
                        context.scene.f3d_type,
                        context.scene.isHWv1,
                        None,
                    )

                romfileOutput.close()
                bpy.ops.object.select_all(action="DESELECT")
                armatureObj.select_set(True)
                context.view_layer.objects.active = armatureObj

                if os.path.exists(bpy.path.abspath(context.scene.fast64.sm64.output_rom)):
                    os.remove(bpy.path.abspath(context.scene.fast64.sm64.output_rom))
                os.rename(bpy.path.abspath(tempROM), bpy.path.abspath(context.scene.fast64.sm64.output_rom))

                if context.scene.geoUseBank0:
                    self.report(
                        {"INFO"},
                        f"Success! Geolayout at ({hex(addrRange[0])}, {hex(addrRange[1])}), to write to RAM Address {hex(startRAM)}, with geolayout starting at {hex(geoStart)}",
                    )
                else:
                    self.report(
                        {"INFO"},
                        f"Success! Geolayout at ({hex(addrRange[0])}, {hex(addrRange[1])}) (Seg. {segPointer}).",
                    )

            applyRotation([armatureObj] + linkedArmatures, math.radians(-90), "X")

            return {"FINISHED"}  # must return a set

        except Exception as e:
            if context.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")

            applyRotation([armatureObj] + linkedArmatures, math.radians(-90), "X")

            if context.scene.fast64.sm64.export_type == "Binary":
                if romfileOutput is not None:
                    romfileOutput.close()
                if tempROM is not None and os.path.exists(bpy.path.abspath(tempROM)):
                    os.remove(bpy.path.abspath(tempROM))
            if armatureObj is not None:
                armatureObj.select_set(True)
                context.view_layer.objects.active = armatureObj
            raisePluginError(self, e)
            return {"CANCELLED"}  # must return a set


sm64_bone_classes = (
    SM64_DefineOptionOperations,
    SM64_SwitchOptionOperations,
    SM64_SwitchMaterialOperations,
    SM64_ExportGeolayoutObject,
    SM64_ExportGeolayoutArmature,
)


def operatorRegister():
    Object.geo_cmd_static = EnumProperty(name="Geolayout Command", items=enumGeoStaticType, default="Optimal")
    Object.draw_layer_static = EnumProperty(name="Draw Layer", items=sm64EnumDrawLayers, default="1")

    Object.scaleFromGeolayout = BoolProperty(
        name="Scale from Geolayout",
        description="If scale is all a single value (e.g. 2, 2, 2), do not apply scale when exporting, and instead use GeoLayout to scale. Can be used to enhance precision by setting scaling values to a value less than 1.",
        default=False,
    )

    # Used during object duplication on export
    Object.original_name = StringProperty()

    for cls in sm64_bone_classes:
        register_class(cls)


def operatorUnregister():
    del Object.geo_cmd_static
    del Object.draw_layer_static
    del Object.scaleFromGeolayout

    # Used during object duplication on export
    del Object.original_name
    for cls in reversed(sm64_bone_classes):
        unregister_class(cls)
