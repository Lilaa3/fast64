import math
import bpy
import mathutils

from ....utility import PluginError, decodeSegmentedAddr
from ....utility_anim import stashActionInArmature
from ...utility import BoneInfo, checkExpanded, getBonesInfo
from ..utility import animationOperatorChecks, sm64ToRadian

from ..classes import SM64_Anim, SM64_AnimPair
from .reading import (
    importBinaryDMAAnimation,
    importBinaryHeader,
    importBinaryTable,
    importCAnimations,
)

from ...sm64_level_parser import SM64_Level, parseLevelAtPointer
from ...constants import (
    level_pointers,
)


def valueDistance(e1, e2):
    result = 0
    for x1, x2 in zip(e1, e2):
        result += abs(x1 - x2)
    return result


def flipEuler(euler):
    ret = euler.copy()

    ret[0] += math.pi
    ret[2] += math.pi
    ret[1] *= -1
    ret[1] += math.pi
    return ret


def naiveFlipDiff(a1, a2):
    while abs(a1 - a2) > math.pi:
        if a1 < a2:
            a2 -= 2 * math.pi
        else:
            a2 += 2 * math.pi

    return a2


class SM64_AnimBone:
    def __init__(self):
        self.translation: list[mathutils.Vector] = []
        self.rotation: list[mathutils.Quaternion] = []

    def readPairs(self, pairs: list[SM64_AnimPair]):
        array: list[int] = []

        maxFrame = max([len(pair.values) for pair in pairs])
        for frame in range(maxFrame):
            array.append([x.getFrame(frame) for x in pairs])
        return array

    def readTranslation(self, pairs: list[SM64_AnimPair], scale):
        translationFrames = self.readPairs(pairs)

        for translationFrame in translationFrames:
            scaledTrans = [(1.0 / scale) * x for x in translationFrame]
            self.translation.append(scaledTrans)

    def readRotation(self, pairs: list[SM64_AnimPair]):
        rotationFrames: list[mathutils.Vector] = self.readPairs(pairs)

        prev = mathutils.Euler([0, 0, 0])

        for rotationFrame in rotationFrames:
            e = mathutils.Euler([sm64ToRadian(x) for x in rotationFrame])
            e[0] = naiveFlipDiff(prev[0], e[0])
            e[1] = naiveFlipDiff(prev[1], e[1])
            e[2] = naiveFlipDiff(prev[2], e[2])

            fe = flipEuler(e)
            fe[0] = naiveFlipDiff(prev[0], fe[0])
            fe[1] = naiveFlipDiff(prev[1], fe[1])
            fe[2] = naiveFlipDiff(prev[2], fe[2])

            de = valueDistance(prev, e)
            dfe = valueDistance(prev, fe)
            if dfe < de:
                e = fe
            prev = e

            self.rotation.append(e.to_quaternion())


def animationTableToBlender(context: bpy.types.Context, tableList: list["SM64_AnimHeader"]):
    tableElements = context.scene.fast64.sm64.anim_export.table.elements
    for header in tableList:
        tableElements.add()
        tableElements[-1].action = bpy.data.actions[header.data.actionName]
        tableElements[-1].headerVariant = header.headerVariant


def animationDataToBlender(armatureObj: bpy.types.Object, blender_to_sm64_scale: float, anim_import: SM64_Anim):
    animBonesInfo, bonesInfo = getBonesInfo(armatureObj)
    for boneInfo in animBonesInfo:
        boneInfo.poseBone.rotation_mode = "QUATERNION"

    action = bpy.data.actions.new("")
    anim_import.toAction(action)

    if armatureObj.animation_data is None:
        armatureObj.animation_data_create()

    stashActionInArmature(armatureObj, action)
    armatureObj.animation_data.action = action

    boneAnimData: list[SM64_AnimBone] = []

    # TODO: Duplicate keyframe filter
    pairs = anim_import.pairs
    for pairNum in range(3, len(pairs), 3):
        bone = SM64_AnimBone()
        if pairNum == 3:
            bone.readTranslation(pairs[0:3], blender_to_sm64_scale)
        bone.readRotation(pairs[pairNum : pairNum + 3])

        boneAnimData.append(bone)

    isRootTranslation = True
    for boneInfo, boneData in zip(animBonesInfo, boneAnimData):
        if isRootTranslation:
            for propertyIndex in range(3):
                fcurve = action.fcurves.new(
                    data_path='pose.bones["' + boneInfo.name + '"].location',
                    index=propertyIndex,
                    action_group=boneInfo.name,
                )
                for frame in range(len(boneData.translation)):
                    fcurve.keyframe_points.insert(frame, boneData.translation[frame][propertyIndex])
            isRootTranslation = False

        for propertyIndex in range(4):
            fcurve = action.fcurves.new(
                data_path='pose.bones["' + boneInfo.name + '"].rotation_quaternion',
                index=propertyIndex,
                action_group=boneInfo.name,
            )
            for frame in range(len(boneData.rotation)):
                fcurve.keyframe_points.insert(frame, boneData.rotation[frame][propertyIndex])
    return action


def importBinaryAnimations(importProps, ROMData, dataDict, tableList):
    address = int(importProps.address, 16)

    levelParsed: SM64_Level = parseLevelAtPointer(ROMData, level_pointers[importProps.level])
    segmentData: dict[int, tuple[int, int]] = levelParsed.segmentData
    if importProps.isSegmentedPointer():
        address = decodeSegmentedAddr(address.to_bytes(4, "big"), segmentData)

    if importProps.binaryImportType == "Table":
        importBinaryTable(
            ROMData, address, importProps.readEntireTable, importProps.tableIndex, segmentData, dataDict, tableList
        )
    elif importProps.binaryImportType == "DMA":
        importBinaryDMAAnimation(
            ROMData,
            int(importProps.DMATableAddress, 16),
            importProps.tableIndex if importProps.marioAnimation == -1 else importProps.marioAnimation,
            importProps.readEntireTable,
            dataDict,
            tableList,
        )
    elif importProps.binaryImportType == "Animation":
        importBinaryHeader(ROMData, address, False, segmentData, dataDict)
    else:
        raise PluginError("Unimplemented binary import type.")


def importAnimationToBlender(context: bpy.types.Context):
    sm64Props = context.scene.fast64.sm64
    importProps = sm64Props.anim_import

    armatureObj: bpy.types.Object = context.selected_objects[0]

    dataDict: dict[str, SM64_Anim] = {}
    tableList: list[str] = []

    animationOperatorChecks(context, False)

    if importProps.importType == "Binary":
        checkExpanded(sm64Props.import_rom)
        with open(bpy.path.abspath(sm64Props.import_rom), "rb") as ROMData:
            importBinaryAnimations(
                importProps,
                ROMData,
                dataDict,
                tableList,
            )
    elif importProps.importType == "C":
        importCAnimations(importProps.path, dataDict, tableList)
    else:
        raise PluginError("Unimplemented Import Type.")

    for dataKey, data in dataDict.items():
        animationDataToBlender(armatureObj, sm64Props.blender_to_sm64_scale, data)
    animationTableToBlender(context, tableList)
