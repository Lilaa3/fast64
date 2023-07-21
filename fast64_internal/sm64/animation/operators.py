import math
import os
import bpy
from bpy.utils import register_class, unregister_class
from bpy.props import (
    EnumProperty,
    FloatProperty,
    StringProperty,
    IntProperty,
)

from .importing.reading import importBinaryDMAAnimation
from .importing import animationDataToBlender, animationTableToBlender, importAnimationToBlender

from .exporting import (
    exportAnimation,
    exportAnimationTable,
)
from .utility import (
    animationOperatorChecks,
    getAction,
    getSelectedAction,
    updateHeaderVariantNumbers,
)

from .constants import marioAnimationNames

from ...utility import (
    PluginError,
    toAlnum,
    raisePluginError,
    get_mode_set_from_context_mode,
    applyRotation,
)


def emulateNoLoop(scene):
    exportProps: "SM64_AnimExportProps" = scene.fast64.sm64.anim_export

    if not exportProps.playedAction:
        return

    try:
        header: "SM64_AnimHeader" = exportProps.playedAction.fast64.sm64.headerFromIndex(exportProps.playedHeader)
    except:
        exportProps.playedAction = None
        return
    if not bpy.context.screen.is_animation_playing:
        exportProps.playedAction = None
        return

    # nextFrame = (scene.frame_float - 1) + exportProps.previewAcceleration # TODO: No.
    nextFrame = scene.frame_current

    startFrame, loopStart, loopEnd = (
        exportProps.playedStartFrame,
        exportProps.playedLoopStart,
        exportProps.playedLoopEnd,
    )
    if header.backward:
        if nextFrame < loopStart:
            if header.noLoop:
                nextFrame = loopStart
            else:
                nextFrame = loopEnd - 1
    elif nextFrame >= loopEnd:
        if header.noLoop:
            nextFrame = loopEnd - 1
        else:
            nextFrame = loopStart

    scene.frame_current = nextFrame


class SM64_PreviewAnimOperator(bpy.types.Operator):
    bl_idname = "scene.sm64_preview_animation"
    bl_label = "Preview Animation"
    bl_options = {"REGISTER", "UNDO", "PRESET"}

    playedHeader: IntProperty(name="Header", min=0, default=0)
    playedAction: StringProperty(name="Action")
    previewAcceleration: FloatProperty(name="Preview acceleration", default=1.0)

    def executeOperation(self, context):
        animationOperatorChecks(context)
        scene = context.scene
        exportProps: "SM64_AnimExportProps" = scene.fast64.sm64.anim_export

        armatureObj: bpy.types.Object = context.selected_objects[0]

        if self.playedAction:
            playedAction = getAction(self.playedAction)
        else:
            playedAction = getSelectedAction(exportProps)
        header = playedAction.fast64.sm64.headerFromIndex(self.playedHeader)
        startFrame, loopStart, loopEnd = header.getFrameRange()

        scene.frame_set(startFrame)
        scene.render.fps = 30

        armatureObj.animation_data.action = playedAction

        if bpy.context.screen.is_animation_playing:
            bpy.ops.screen.animation_play()

        bpy.ops.screen.animation_play()

        exportProps.playedHeader = self.playedHeader
        exportProps.playedAction = playedAction
        exportProps.previewAcceleration = self.previewAcceleration

        exportProps.playedStartFrame, exportProps.playedLoopStart, exportProps.playedLoopEnd = (
            startFrame,
            loopStart,
            loopEnd,
        )

        return {"FINISHED"}

    def execute(self, context):
        try:
            return self.executeOperation(context)
        except Exception as e:
            raisePluginError(self, e)
            return {"CANCELLED"}


class SM64_TableOperations(bpy.types.Operator):
    bl_idname = "scene.sm64_table_operations"
    bl_label = ""
    bl_options = {"UNDO"}
    arrayIndex: IntProperty()
    type: StringProperty()
    actionName: StringProperty(name="Action")
    headerVariant: IntProperty()

    def execute_operator(self, context):
        exportProps = context.scene.fast64.sm64.anim_export
        table = exportProps.table
        tableElements = table.elements

        if self.type == "MOVE_UP":
            tableElements.move(self.arrayIndex, self.arrayIndex - 1)
        elif self.type == "MOVE_DOWN":
            tableElements.move(self.arrayIndex, self.arrayIndex + 1)
        elif self.type == "ADD":
            tableElements.add()
            tableElements.move(len(tableElements) - 1, self.arrayIndex)
            tableElements[-1].action = bpy.data.actions[self.actionName]
            tableElements[-1].headerVariant = self.headerVariant
        elif self.type == "REMOVE":
            tableElements.remove(self.arrayIndex)
        if self.type == "CLEAR":
            for i in range(len(tableElements)):
                tableElements.remove(0)

        return {"FINISHED"}

    def execute(self, context):
        try:
            return self.execute_operator(context)
        except Exception as e:
            raisePluginError(self, e)
            return {"CANCELLED"}


class SM64_AnimVariantOperations(bpy.types.Operator):
    bl_idname = "scene.sm64_header_variant_operations"
    bl_label = ""
    bl_options = {"UNDO"}
    arrayIndex: IntProperty()
    type: StringProperty()
    actionName: StringProperty(name="Action")

    def execute_operator(self, context):
        action = bpy.data.actions[self.actionName]
        actionProps = action.fast64.sm64

        variants = actionProps.headerVariants

        if self.type == "MOVE_UP":
            variants.move(self.arrayIndex, self.arrayIndex - 1)
        elif self.type == "MOVE_DOWN":
            variants.move(self.arrayIndex, self.arrayIndex + 1)
        elif self.type == "ADD":
            variants.add()
            variants.move(len(variants) - 1, self.arrayIndex + 1)
        elif self.type == "REMOVE":
            variants.remove(self.arrayIndex)
        if self.type == "CLEAR":
            for i in range(len(variants)):
                variants.remove(0)

        updateHeaderVariantNumbers(variants)

        if self.type == "ADD":
            variants[-1].action = action
            if len(variants) > 1:
                variants[-1].copyHeader(context.scene.fast64.sm64.anim_export, variants[self.arrayIndex])

        return {"FINISHED"}

    def execute(self, context):
        try:
            return self.execute_operator(context)
        except Exception as e:
            raisePluginError(self, e)
            return {"CANCELLED"}


class SM64_ExportAnimTable(bpy.types.Operator):
    bl_idname = "scene.sm64_export_anim_table"
    bl_label = "Export"
    bl_description = "Select an armature with animation data to use"
    bl_options = {"REGISTER", "UNDO", "PRESET"}

    def execute(self, context):
        try:
            animationOperatorChecks(context)
        except Exception as e:
            raisePluginError(self, e)
            return {"CANCELLED"}

        armatureObj: bpy.types.Object = context.selected_objects[0]
        contextMode = context.mode
        actionPreRead = armatureObj.animation_data.action
        framePreRead = context.scene.frame_current

        bpy.ops.object.mode_set(mode="OBJECT")
        applyRotation([armatureObj], math.radians(90), "X")

        result = {"FINISHED"}
        try:
            self.report({"INFO"}, exportAnimationTable(context, armatureObj))
        except Exception as e:
            result = {"CANCELLED"}
            raisePluginError(self, e)

        bpy.ops.object.mode_set(mode=get_mode_set_from_context_mode(contextMode))
        armatureObj.animation_data.action = actionPreRead
        context.scene.frame_set(framePreRead)
        applyRotation([armatureObj], math.radians(-90), "X")
        return result


class SM64_ExportAnim(bpy.types.Operator):
    bl_idname = "scene.sm64_export_anim"
    bl_label = "Export"
    bl_description = "Exports the selected action, select an armature with animation data to use"
    bl_options = {"REGISTER", "UNDO", "PRESET"}

    def execute(self, context):
        scene = context.scene
        exportProps = scene.fast64.sm64.anim_export
        romfileOutput, tempROM = None, None

        try:
            animationOperatorChecks(context)
        except Exception as e:
            raisePluginError(self, e)
            return {"CANCELLED"}

        armatureObj: bpy.types.Object = context.selected_objects[0]
        contextMode = context.mode
        actionPreRead = armatureObj.animation_data.action
        framePreRead = scene.frame_current

        bpy.ops.object.mode_set(mode="OBJECT")
        applyRotation([armatureObj], math.radians(90), "X")

        result = {"FINISHED"}
        try:
            action = getSelectedAction(exportProps)
            self.report({"INFO"}, exportAnimation(armatureObj, scene, action))
        except Exception as e:
            result = {"CANCELLED"}
            raisePluginError(self, e)

        bpy.ops.object.mode_set(mode=get_mode_set_from_context_mode(contextMode))
        armatureObj.animation_data.action = actionPreRead
        scene.frame_set(framePreRead)
        applyRotation([armatureObj], math.radians(-90), "X")

        if romfileOutput is not None:
            romfileOutput.close()
        if tempROM is not None and os.path.exists(bpy.path.abspath(tempROM)):
            os.remove(bpy.path.abspath(tempROM))

        return result


# Importing
class SM64_ImportAllMarioAnims(bpy.types.Operator):
    bl_idname = "scene.sm64_import_mario_anims"
    bl_label = "Import All Mario Animations"
    bl_options = {"REGISTER", "UNDO", "PRESET"}

    def execute_operator(self, context):
        animationOperatorChecks(context, False)

        sm64Props = context.scene.fast64.sm64
        importProps = sm64Props.anim_import

        armatureObj: bpy.types.Object = context.selected_objects[0]

        dataDict: dict[str, "SM64_Anim"] = {}
        tableList: list["SM64_AnimHeader"] = []

        if importProps.importType == "Binary":
            with open(bpy.path.abspath(sm64Props.import_rom), "rb") as ROMData:
                for entrieStr, name, description in marioAnimationNames[1:]:
                    header = importBinaryDMAAnimation(
                        ROMData,
                        0x4EC000,
                        int(entrieStr),
                        False,
                        dataDict,
                        tableList,
                    )
                    header.name = toAlnum(name)
                    header.data.actionName = name
        else:
            raise PluginError("Unimplemented import type.")

        for dataKey, data in dataDict.items():
            animationDataToBlender(armatureObj, sm64Props.blender_to_sm64_scale, data)
        animationTableToBlender(context, tableList)

        return {"FINISHED"}

    def execute(self, context):
        try:
            return self.execute_operator(context)
        except Exception as e:
            raisePluginError(self, e)
            return {"CANCELLED"}


class SM64_ImportAnim(bpy.types.Operator):
    bl_idname = "scene.sm64_import_anim"
    bl_label = "Import Animation"
    bl_options = {"REGISTER", "UNDO", "PRESET"}

    def execute(self, context):
        try:
            animationOperatorChecks(context, False)
            importAnimationToBlender(context)

            self.report({"INFO"}, "Success!")
            return {"FINISHED"}
        except Exception as e:
            raisePluginError(self, e)
            return {"CANCELLED"}


class SM64_SearchMarioAnimEnum(bpy.types.Operator):
    bl_idname = "scene.search_mario_anim_enum_operator"
    bl_label = "Search Mario Animations"
    bl_description = "Search Mario Animations"
    bl_property = "marioAnimations"
    bl_options = {"UNDO"}

    marioAnimations: EnumProperty(items=marioAnimationNames)

    def execute(self, context):
        anim_import = context.scene.fast64.sm64.anim_import

        context.region.tag_redraw()
        anim_import.marioAnimation = int(self.marioAnimations)
        self.report({"INFO"}, "Selected: " + self.marioAnimations)
        return {"FINISHED"}

    def invoke(self, context, event):
        context.window_manager.invoke_search_popup(self)
        return {"RUNNING_MODAL"}


sm64_anim_operators = (
    # Exporting
    SM64_ExportAnimTable,
    SM64_ExportAnim,
    SM64_PreviewAnimOperator,
    SM64_TableOperations,
    SM64_AnimVariantOperations,
    # Importing
    SM64_SearchMarioAnimEnum,
    SM64_ImportAnim,
    SM64_ImportAllMarioAnims,
)


def sm64_anim_operator_register():
    for cls in sm64_anim_operators:
        register_class(cls)

    bpy.app.handlers.frame_change_pre.append(emulateNoLoop)


def sm64_anim_operator_unregister():
    for cls in reversed(sm64_anim_operators):
        unregister_class(cls)

    if emulateNoLoop in bpy.app.handlers.frame_change_pre:
        bpy.app.handlers.frame_change_pre.remove(emulateNoLoop)
