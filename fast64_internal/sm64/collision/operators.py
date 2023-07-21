import math
import os
import bpy, mathutils
from bpy.utils import register_class, unregister_class
from bpy.props import (
    EnumProperty,
    FloatProperty,
    StringProperty,
    IntProperty,
)
from ...utility import applyRotation, raisePluginError, PluginError
from .constants import enumCollisionType

class SM64_SearchCollisionEnum(bpy.types.Operator):
    bl_idname = "scene.search_collision_enums_operator"
    bl_label = "Search Collision Enum"
    bl_description = "Search All Collision Enum"
    bl_property = "collisionEnum"
    bl_options = {"UNDO"}

    collisionEnum: EnumProperty(items=enumCollisionType)

    def execute(self, context):
        context.region.tag_redraw()
        context.material.fast64.sm64.collision.vanilla.type = self.collisionEnum
        self.report({"INFO"}, "Selected: " + self.collisionEnum)
        return {"FINISHED"}

    def invoke(self, context, event):
        context.window_manager.invoke_search_popup(self)
        return {"RUNNING_MODAL"}

class SM64_ExportCollision(bpy.types.Operator):
    # set bl_ properties
    bl_idname = "object.sm64_export_collision"
    bl_label = "Export Collision"
    bl_description = "Export Collision"
    bl_options = {"REGISTER", "UNDO", "PRESET"}

    def execute(self, context):
        romfileOutput = None
        tempROM = None
        try:
            obj = None
            if context.mode != "OBJECT":
                raise PluginError("Operator can only be used in object mode.")
            if len(context.selected_objects) == 0:
                raise PluginError("Object not selected.")
            obj = context.active_object

            scaleValue = bpy.context.scene.fast64.sm64.blender_to_sm64_scale
            finalTransform = mathutils.Matrix.Diagonal(mathutils.Vector((scaleValue, scaleValue, scaleValue))).to_4x4()
        except Exception as e:
            raisePluginError(self, e)
            return {"CANCELLED"}

        try:
            applyRotation([obj], math.radians(90), "X")
            if context.scene.fast64.sm64.export_type == "C":
                exportPath, levelName = getPathAndLevel(
                    context.scene.colCustomExport,
                    context.scene.colExportPath,
                    context.scene.colLevelName,
                    context.scene.colLevelOption,
                )
                if not context.scene.colCustomExport:
                    apply_basic_tweaks(exportPath)
                exportCollisionC(
                    obj,
                    finalTransform,
                    exportPath,
                    False,
                    context.scene.colIncludeChildren,
                    bpy.context.scene.colName,
                    context.scene.colCustomExport,
                    context.scene.colExportRooms,
                    context.scene.colExportHeaderType,
                    context.scene.colGroupName,
                    levelName,
                )
                self.report({"INFO"}, "Success!")
            elif context.scene.fast64.sm64.export_type == "Insertable Binary":
                exportCollisionInsertableBinary(
                    obj,
                    finalTransform,
                    bpy.path.abspath(context.scene.colInsertableBinaryPath),
                    False,
                    context.scene.colIncludeChildren,
                )
                self.report({"INFO"}, "Success! Collision at " + context.scene.colInsertableBinaryPath)
            else:
                tempROM = tempName(context.scene.fast64.sm64.output_rom)
                checkExpanded(bpy.path.abspath(context.scene.fast64.sm64.export_rom))
                romfileExport = open(bpy.path.abspath(context.scene.fast64.sm64.export_rom), "rb")
                shutil.copy(bpy.path.abspath(context.scene.fast64.sm64.export_rom), bpy.path.abspath(tempROM))
                romfileExport.close()
                romfileOutput = open(bpy.path.abspath(tempROM), "rb+")

                levelParsed = parseLevelAtPointer(romfileOutput, level_pointers[context.scene.colExportLevel])
                segmentData = levelParsed.segmentData

                if context.scene.fast64.sm64.extend_bank_4:
                    ExtendBank0x04(romfileOutput, segmentData, defaultExtendSegment4)

                addrRange = exportCollisionBinary(
                    obj,
                    finalTransform,
                    romfileOutput,
                    int(context.scene.colStartAddr, 16),
                    int(context.scene.colEndAddr, 16),
                    False,
                    context.scene.colIncludeChildren,
                )

                segAddress = encodeSegmentedAddr(addrRange[0], segmentData)
                if context.scene.set_addr_0x2A:
                    romfileOutput.seek(int(context.scene.addr_0x2A, 16) + 4)
                    romfileOutput.write(segAddress)
                segPointer = bytesToHex(segAddress)

                romfileOutput.close()

                if os.path.exists(bpy.path.abspath(context.scene.fast64.sm64.output_rom)):
                    os.remove(bpy.path.abspath(context.scene.fast64.sm64.output_rom))
                os.rename(bpy.path.abspath(tempROM), bpy.path.abspath(context.scene.fast64.sm64.output_rom))

                self.report(
                    {"INFO"},
                    "Success! Collision at ("
                    + hex(addrRange[0])
                    + ", "
                    + hex(addrRange[1])
                    + ") (Seg. "
                    + segPointer
                    + ").",
                )

            applyRotation([obj], math.radians(-90), "X")
            return {"FINISHED"}  # must return a set

        except Exception as e:
            if context.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")

            applyRotation([obj], math.radians(-90), "X")

            if context.scene.fast64.sm64.export_type == "Binary":
                if romfileOutput is not None:
                    romfileOutput.close()
                if tempROM is not None and os.path.exists(bpy.path.abspath(tempROM)):
                    os.remove(bpy.path.abspath(tempROM))
            obj.select_set(True)
            context.view_layer.objects.active = obj
            raisePluginError(self, e)
            return {"CANCELLED"}  # must return a set


operators = [SM64_SearchCollisionEnum, SM64_ExportCollision]

def operatorRegister():
    for cls in operators:
        register_class(cls)

def operatorUnregister():
    for cls in reversed(operators):
        unregister_class(cls)
