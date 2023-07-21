from cmath import exp
from io import StringIO
import bpy, time, mathutils, os, math

from ..utility import (
    CArrayReader,
    animNameToEnum,
    getAnimName,
    getAnimFileName,
    getActionsInTable,
    getEnumListName,
    getHeadersInTable,
    getMaxFrame,
)
from ...utility import BoneInfo, getBonesInfo, apply_basic_tweaks, getExportDir, radian_to_sm64_degree
from ..classes import SM64_AnimHeader, SM64_Anim, SM64_AnimPair

from ....utility import (
    PluginError,
    arrayToC,
    enumToC,
    toAlnum,
    writeIfNotFound,
    writeInsertableFile,
)
from ....utility_anim import stashActionInArmature
from ...constants import NULL


def getAnimationPairs(
    scene: bpy.types.Scene,
    action: bpy.types.Action,
    armatureObj: bpy.types.Object,
    animBonesInfo: list[BoneInfo],
) -> tuple[list[int], list[int]]:
    sm64Props = scene.fast64.sm64
    exportProps = sm64Props.anim_export
    blender_to_sm64_scale = sm64Props.blender_to_sm64_scale

    maxFrame = getMaxFrame(scene, action)

    pairs = [
        SM64_AnimPair(exportProps.bestFrameAmounts),
        SM64_AnimPair(exportProps.bestFrameAmounts),
        SM64_AnimPair(exportProps.bestFrameAmounts),
    ]
    transXPair, transYPair, transZPair = pairs

    rotationPairs: list[tuple[SM64_AnimPair]] = []
    for boneInfo in animBonesInfo:
        xyzPairs = (
            SM64_AnimPair(exportProps.bestFrameAmounts),
            SM64_AnimPair(exportProps.bestFrameAmounts),
            SM64_AnimPair(exportProps.bestFrameAmounts),
        )
        pairs.extend(xyzPairs)
        rotationPairs.append(xyzPairs)

    scale: mathutils.Vector = armatureObj.matrix_world.to_scale() * blender_to_sm64_scale

    print("Reading animation pair values.")

    armatureObj.animation_data.action = action
    for frame in range(maxFrame):
        scene.frame_set(frame)
        for boneIndex, boneInfo in enumerate(animBonesInfo):
            poseBone = boneInfo.poseBone
            if boneIndex == 0:  # Only first bone has translation.
                translation: mathutils.Vector = poseBone.location * scale
                transXPair.appendFrame(int(translation.x))
                transYPair.appendFrame(int(translation.y))
                transZPair.appendFrame(int(translation.z))

            for angle, pair in zip(poseBone.matrix_basis.to_euler(), rotationPairs[boneIndex]):
                pair.appendFrame(radian_to_sm64_degree(angle))

    return pairs


def getIntFlags(header):
    if header.setCustomFlags:
        flags: int = int(header.customIntFlags, 16)
    else:
        flags: int = 0
        if header.noLoop:
            flags |= 1 << 0
        if header.backward:
            flags |= 1 << 1
        if header.noAcceleration:
            flags |= 1 << 2
        if header.disabled:
            flags |= 1 << 5
    return flags


def getCFlags(header):
    if header.setCustomFlags:
        flags = header.customFlags
    else:
        flagList = []
        if header.noLoop:
            flagList.append("ANIM_FLAG_NOLOOP")
        if header.backward:  # TODO: Check for refresh 16 here
            flagList.append("ANIM_FLAG_FORWARD")
        if header.noAcceleration:
            flagList.append("ANIM_FLAG_NO_ACCEL")
        if header.disabled:
            flagList.append("ANIM_FLAG_DISABLED")

        if flagList:
            flags = " | ".join(flagList)
            if len(flagList) > 1:
                flags = f"({flags})"
        else:
            flags = 0
    return flags


def updateIncludes(levelName, dirName, dirPath, exportProps):
    if exportProps.export_type not in ["Custom", "DMA"]:
        if exportProps.export_type == "Actor":
            groupPathC = os.path.join(dirPath, exportProps.groupName + ".c")
            groupPathH = os.path.join(dirPath, exportProps.groupName + ".h")

            writeIfNotFound(groupPathC, '\n#include "' + dirName + '/anims/data.inc.c"', "")
            writeIfNotFound(groupPathC, '\n#include "' + dirName + '/anims/table.inc.c"', "")
            writeIfNotFound(groupPathH, '\n#include "' + dirName + '/anim_header.h"', "#endif")
        elif exportProps.export_type == "Level":
            groupPathC = os.path.join(dirPath, "leveldata.c")
            groupPathH = os.path.join(dirPath, "header.h")

            writeIfNotFound(groupPathC, '\n#include "levels/' + levelName + "/" + dirName + '/anims/data.inc.c"', "")
            writeIfNotFound(groupPathC, '\n#include "levels/' + levelName + "/" + dirName + '/anims/table.inc.c"', "")
            writeIfNotFound(
                groupPathH, '\n#include "levels/' + levelName + "/" + dirName + '/anim_header.h"', "\n#endif"
            )


def writeActorHeader(geoDirPath, animsName):
    headerPath = os.path.join(geoDirPath, "anim_header.h")
    headerFile = open(headerPath, "w", newline="\n")
    headerFile.write("extern const struct Animation *const " + animsName + "[];\n")
    headerFile.close()


def updateTableFile(tablePath: str, tableName: str, headers: list["SM64_AnimHeader"], action, exportProps):
    if not os.path.exists(tablePath):
        createTableFile(exportProps, tablePath, tableName, [])

    # Improved table logic.
    with open(tablePath, "r") as readable_file:
        text = readable_file.read()

    tableProps = exportProps.table
    headerPointers = [f"&{getAnimName(sm64ExportProps, header, action)}" for header in headers]
    tableName, enumListName = exportProps.table.getAnimTableName(exportProps), getEnumListName(exportProps)

    arrayReader = CArrayReader()
    arrays = arrayReader.findAllCArraysInFile(text)

    tableOriginArray, readTable = None, headerPointers
    enumOriginList, enumsList = None, []

    if tableName in arrays:
        tableOriginArray = arrays[tableName]
        readTable = tableOriginArray.values.copy()

    if tableProps.generateEnums:
        if enumListName in arrays:
            enumOriginList = arrays[enumListName]
            enumsList = enumOriginList.values.copy()

        tableArray = {}
        for element in readTable:
            if isinstance(element, tuple):
                enum = element[0]
                pointer = element[1]
            else:
                enum = animNameToEnum(element[1:])
                pointer = element

            tableArray[enum] = pointer

        for headerPointer in headerPointers:
            headerEnum = animNameToEnum(headerPointer[1:])
            tableArray[headerEnum] = headerPointer

        for tableEnumName in tableArray.keys():
            for enumName in enumsList:
                if isinstance(enumName, tuple):
                    enumName = enumListName[0]
                if enumName == tableEnumName:
                    break
            else:
                enumsList.append(tableEnumName)

        enumInC = enumToC(enumListName, enumsList)
    else:
        tableArray = []
        for pointer in readTable:
            if isinstance(pointer, tuple):
                pointer = pointer[1]

            tableArray.append(pointer)

        for headerPointer in headerPointers:
            if headerPointer not in tableArray:
                tableArray.append(headerPointer)

    if tableProps.generateEnums:
        if enumOriginList:
            text = text.replace(enumOriginList.originString, enumInC)
        else:
            text = f"{enumInC}\n" + text

    tableInC = arrayToC(
        tableName,
        "const struct Animation *const",
        tableArray,
        explicitSize=True,
        sizeComment=False,
        newLineEveryElement=True,
    )
    if tableOriginArray:
        text = text.replace(tableOriginArray.originString, tableInC)
    else:
        text += f"\n{tableInC}"

    with open(tablePath, "w") as f:
        f.write(text)


def createTableFile(exportProps, tableFilePath, tableName, headerNames):
    tableProps = exportProps.table
    tableName, enumListName = tableProps.getAnimTableName(exportProps), getEnumListName(exportProps)

    if tableProps.generateEnums:
        tableArray = {}
        for headerName in headerNames:
            tableArray[animNameToEnum(headerName)] = f"&{headerName}"

        enumsList = set()
        for tableEnumName in tableArray.keys():
            enumsList.add(tableEnumName)
    else:
        tableArray = []
        for headerName in headerNames:
            tableArray.append(f"&{headerName}")

    with open(tableFilePath, "w", newline="\n") as tableFile:
        if tableProps.generateEnums:
            tableFile.write(enumToC(enumListName, enumsList))
            tableFile.write("\n\n")

        tableInC = arrayToC(
            tableName,
            "const struct Animation *const",
            tableArray,
            explicitSize=True,
            sizeComment=False,
            newLineEveryElement=True,
        )
        tableFile.write(tableInC)


def createDataFile(sm64Props, dataFilePath, table=None):
    print(f"Creating new animation data file at {dataFilePath}")
    open(dataFilePath, "w", newline="\n")
    for action in getActionsInTable(table):
        writeIfNotFound(dataFilePath, '#include "' + getAnimFileName(sm64Props, action) + '"\n', "")


def updateDataFile(sm64Props, dataFilePath, animFileName):
    print(f"Updating animation data file at {dataFilePath}")
    if not os.path.exists(dataFilePath):
        createDataFile(sm64Props, dataFilePath)

    writeIfNotFound(dataFilePath, '#include "' + animFileName + '"\n', "")


def updateFiles(
    sm64Props,
    exportProps: "SM64_AnimExportProps",
    geoDirPath: str,
    animDirPath: str,
    dirPath: str,
    levelName: str,
    dirName: str,
    animFileName: str,
    headers: list["SM64_AnimHeader"],
    skipTableAndData: bool,
):
    exportProps = sm64Props.anim_export

    tableProps = exportProps.table
    tableName = tableProps.getAnimTableName(exportProps)
    tablePath = os.path.join(animDirPath, tableProps.getAnimTableFileName(sm64Props))
    dataFilePath = os.path.join(animDirPath, "data.inc.c")

    if not skipTableAndData:
        updateTableFile(tablePath, tableName, headers, exportProps)
        if exportProps.handleIncludes:
            updateDataFile(sm64Props, dataFilePath, animFileName)

    if exportProps.handleIncludes:
        writeActorHeader(geoDirPath, tableProps.getAnimTableName(exportProps))
        updateIncludes(levelName, dirName, dirPath, exportProps)


def getAnimationPaths(exportProps):
    customExport = exportProps.export_type == "Custom"

    exportPath, levelName = getPathAndLevel(
        customExport,
        exportProps.customPath,
        exportProps.level,
        exportProps.customLevel,
    )

    if not customExport:
        apply_basic_tweaks(exportPath)

    dirName = toAlnum(exportProps.actorName)

    if exportProps.export_type == "DMA":
        animDirPath = os.path.join(exportPath, exportProps.DMAFolder)
        dirPath = ""
        geoDirPath = ""
    else:
        dirPath, texDir = getExportDir(customExport, exportPath, exportProps.export_type, levelName, "", dirName)
        geoDirPath = os.path.join(dirPath, dirName)
        animDirPath = os.path.join(geoDirPath, "anims")

        if not os.path.exists(dirPath):
            os.mkdir(dirPath)
        if not os.path.exists(geoDirPath):
            os.mkdir(geoDirPath)
        if not os.path.exists(animDirPath):
            os.mkdir(animDirPath)

    return animDirPath, dirPath, geoDirPath, levelName


def getAnimationData(armatureObj: bpy.types.Object, scene: bpy.types.Scene, action: bpy.types.Action, headers):
    sm64Props = scene.fast64.sm64
    exportProps = sm64Props.anim_export
    actionProps = action.fast64.sm64

    stashActionInArmature(armatureObj, action)
    animBonesInfo = getBonesInfo(armatureObj)[0]

    sm64Anim = SM64_Anim()

    if actionProps.referenceTables:
        sm64Anim.reference = True
        if sm64Props.is_binary_export():
            sm64Anim.valuesReference, sm64Anim.indicesReference = int(actionProps.valuesAddress, 16), int(
                actionProps.indicesAddress, 16
            )
    else:
        sm64Anim.pairs = getAnimationPairs(scene, action, armatureObj, animBonesInfo)

    sm64Anim.isDmaStructure = exportProps.isDmaStructure(sm64Props)

    for header in headers:
        sm64AnimHeader = SM64_AnimHeader()
        sm64AnimHeader.data = sm64Anim
        sm64Anim.headers.append(sm64AnimHeader)

        sm64AnimHeader.name = getAnimName(exportProps, header)
        if sm64Anim.isDmaStructure or sm64Props.is_binary_export():
            sm64AnimHeader.flags = getIntFlags(header)
        else:
            sm64AnimHeader.flags = getCFlags(header)

        startFrame, loopStart, loopEnd = header.getFrameRange()

        sm64AnimHeader.yDivisor = header.yDivisor
        sm64AnimHeader.startFrame = startFrame
        sm64AnimHeader.loopStart = loopStart
        sm64AnimHeader.loopEnd = loopEnd
        sm64AnimHeader.boneCount = len(animBonesInfo)
    return sm64Anim


def exportAnimTableInsertableBinary(
    armatureObj: bpy.types.Object,
    scene: bpy.types.Scene,
    tableHeaders: list["SM64_AnimHeaderProps"],
    sm64Anim: SM64_Anim,
) -> str:
    sm64Props = scene.fast64.sm64
    exportProps = sm64Props.anim_export
    tableProps = exportProps.table

    data: bytearray = bytearray()
    ptrs: list[int] = []
    tableDict: dict = {}

    # Allocate table data.
    for header in tableHeaders:
        tableOffset = len(data)
        ptrs.append(tableOffset)
        data.extend(bytearray([0x00] * 4))

        offsets = tableDict.get(header, [])
        offsets.append(tableOffset)
        tableDict[header] = offsets

    data.extend(NULL.to_bytes(4, byteorder="big", signed=False))  # NULL represents the end of a table

    for action in getActionsInTable(tableProps):  # Iterates through all actions in table
        offset = len(data)

        actionHeaders = []  # Get all headers needed for table export in order
        for tableHeader, offsets in tableDict.items():
            if action != tableHeader.action:
                continue
            for tableOffset in offsets:
                headerOffset = offset + (len(actionHeaders) * 4)
                data[tableOffset : tableOffset + 4] = headerOffset.to_bytes(4, byteorder="big", signed=False)
            actionHeaders.append(header)

        sm64Anim = getAnimationData(armatureObj, scene, action, actionHeaders)
        animResult = sm64Anim.toBinary(exportProps.mergeValues, False, offset)

        data.extend(animResult[0])
        ptrs.extend(animResult[1])

    directory = os.path.abspath(exportProps.binary.insertableDirectory)
    animTableFileName = tableProps.getAnimTableFileName(sm64Props)
    writeInsertableFile(os.path.join(directory, animTableFileName), 2, ptrs, 0, data)

    return "Success!"


def exportAnimInsertableBinary(action: bpy.types.Action, sm64Props, sm64Anim: SM64_Anim) -> str:
    exportProps = sm64Props.anim_export

    data, ptrs = sm64Anim.toBinary(exportProps.mergeValues, exportProps.isDmaStructure(sm64Props), 0)

    directory = os.path.abspath(exportProps.binary.insertableDirectory)
    animFileName = getAnimFileName(sm64Props, action)
    writeInsertableFile(os.path.join(directory, animFileName), 2, ptrs, 0, data)

    return "Success!"


def exportAnimC(
    action: bpy.types.Action,
    scene: bpy.types.Scene,
    sm64Anim: SM64_Anim,
    skipTableAndData: bool,
) -> str:
    sm64Props = scene.fast64.sm64
    exportProps = sm64Props.anim_export
    actionProps = action.fast64.sm64

    if actionProps.referenceTables:
        sm64Anim.valuesReference, sm64Anim.indicesReference = actionProps.valuesTable, actionProps.indicesTable
    else:
        dataName: str = toAlnum(f"anim_{action.name}")
        sm64Anim.valuesReference, sm64Anim.indicesReference = f"{dataName}_values", f"{dataName}_indices"

    animDirPath, dirPath, geoDirPath, levelName = getAnimationPaths(exportProps)

    animFileName = getAnimFileName(sm64Props, action)

    isDmaStructure = False
    if exportProps.export_type == "DMA":
        isDmaStructure = exportProps.useDMAStructure
    else:
        if exportProps.export_type == "Custom":
            isDmaStructure = exportProps.useDMAStructure
        elif exportProps.handleTables:
            updateFiles(
                sm64Props,
                geoDirPath,
                animDirPath,
                dirPath,
                levelName,
                toAlnum(exportProps.actorName),
                animFileName,
                sm64Anim.headers,
                skipTableAndData,
            )

    animPath = os.path.join(animDirPath, animFileName)

    headersC = sm64Anim.headersToC(exportProps.designated and not isDmaStructure, isDmaStructure)
    dataC = sm64Anim.toC(exportProps.mergeValues, exportProps.useHexValues, not isDmaStructure)

    with open(animPath, "w", newline="\n") as animFile:
        if isDmaStructure:
            animFile.write(headersC)
            if dataC:
                animFile.write("\n\n")
                animFile.write(dataC)
        else:
            if dataC:
                animFile.write(dataC)
                animFile.write("\n\n")
            animFile.write(headersC)

    return "Success!"


def exportAnimation(
    armatureObj: bpy.types.Context, scene: bpy.types.Scene, action: bpy.types.Action, skipTableAndData: bool = False
):
    sm64Props = scene.fast64.sm64

    sm64Anim = getAnimationData(armatureObj, scene, action, action.fast64.sm64.getHeaders())
    if sm64Props.export_type == "C":
        exportAnimC(action, scene, sm64Anim, skipTableAndData)
    else:
        exportAnimInsertableBinary(action, sm64Props, sm64Anim)

    return "Sucess!"


def exportAnimationTable(context: bpy.types.Context, armatureObj: bpy.types.Object):
    scene = context.scene
    sm64Props = scene.fast64.sm64
    exportProps = sm64Props.anim_export
    tableProps = exportProps.table

    tableHeaders = getHeadersInTable(tableProps)
    headerNames = [getAnimName(exportProps, header) for header in tableHeaders]

    if sm64Props.export_type == "C":
        for action in getActionsInTable(tableProps):
            exportAnimation(context, scene, action, tableProps.overrideFiles)
    elif sm64Props.export_type == "Insertable Binary":
        return exportAnimTableInsertableBinary(armatureObj, scene, tableHeaders, sm64Props)
    else:
        return

    if tableProps.overrideFiles:
        animDirPath, dirPath, geoDirPath, levelName = getAnimationPaths(sm64Props)

        tableName = tableProps.getAnimTableName(exportProps)
        tablePath = os.path.join(animDirPath, "table.inc.c")
        dataFilePath = os.path.join(animDirPath, "data.inc.c")

        createTableFile(exportProps, tablePath, tableName, headerNames)
        if exportProps.handleIncludes:
            createDataFile(sm64Props, dataFilePath, tableProps)

    return "Sucess!"
