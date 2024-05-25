from math import degrees, radians, pi
import os
import random

import bpy

from ..utility import PluginError, to_s16

ULTRA_SM64_MEMORY_C = "src/boot/memory.c"
SM64_MEMORY_C = "src/game/memory.c"
radians_to_s16 = lambda d: to_s16(d * 0x10000 / (2 * pi))


def starSelectWarning(operator, fileStatus):
    if fileStatus is not None and not fileStatus.starSelectC:
        operator.report({"WARNING"}, "star_select.c not found, skipping star select scrolling.")


def cameraWarning(operator, fileStatus):
    if fileStatus is not None and not fileStatus.cameraC:
        operator.report({"WARNING"}, "camera.c not found, skipping camera volume and zoom mask exporting.")


def getMemoryCFilePath(decompDir):
    isUltra = os.path.exists(os.path.join(decompDir, ULTRA_SM64_MEMORY_C))
    relPath = ULTRA_SM64_MEMORY_C if isUltra else SM64_MEMORY_C
    return os.path.join(decompDir, relPath)


def checkExpanded(filepath):
    size = os.path.getsize(filepath)
    if size < 9000000:  # check if 8MB
        raise PluginError(
            "ROM at "
            + filepath
            + " is too small. You may be using an unexpanded ROM. You can expand a ROM by opening it in SM64 Editor or ROM Manager."
        )


def getPathAndLevel(customExport, exportPath, levelName, levelOption):
    if customExport:
        exportPath = bpy.path.abspath(exportPath)
        levelName = levelName
    else:
        exportPath = bpy.path.abspath(bpy.context.scene.decompPath)
        if levelOption == "custom":
            levelName = levelName
        else:
            levelName = levelOption
    return exportPath, levelName


def findStartBones(armatureObj):
    noParentBones = sorted(
        [
            bone.name
            for bone in armatureObj.data.bones
            if bone.parent is None and (bone.geo_cmd != "SwitchOption" and bone.geo_cmd != "Ignore")
        ]
    )

    if len(noParentBones) == 0:
        raise PluginError(
            "No non switch option start bone could be found "
            + "in "
            + armatureObj.name
            + ". Is this the root armature?"
        )
    else:
        return noParentBones

    if len(noParentBones) == 1:
        return noParentBones[0]
    elif len(noParentBones) == 0:
        raise PluginError(
            "No non switch option start bone could be found "
            + "in "
            + armatureObj.name
            + ". Is this the root armature?"
        )
    else:
        raise PluginError(
            "Too many parentless bones found. Make sure your bone hierarchy starts from a single bone, "
            + 'and that any bones not related to a hierarchy have their geolayout command set to "Ignore".'
        )


def applyBasicTweaks(baseDir):
    enableExtendedRAM(baseDir)
    return


def enableExtendedRAM(baseDir):
    segmentPath = os.path.join(baseDir, "include/segments.h")

    segmentFile = open(segmentPath, "r", newline="\n")
    segmentData = segmentFile.read()
    segmentFile.close()

    matchResult = re.search("#define\s*USE\_EXT\_RAM", segmentData)

    if not matchResult:
        matchResult = re.search("#ifndef\s*USE\_EXT\_RAM", segmentData)
        if matchResult is None:
            raise PluginError(
                "When trying to enable extended RAM, " + "could not find '#ifndef USE_EXT_RAM' in include/segments.h."
            )
        segmentData = (
            segmentData[: matchResult.start(0)] + "#define USE_EXT_RAM\n" + segmentData[matchResult.start(0) :]
        )

        segmentFile = open(segmentPath, "w", newline="\n")
        segmentFile.write(segmentData)
        segmentFile.close()


def decompFolderMessage(layout):
    layout.box().label(text="This will export to your decomp folder.")


def customExportWarning(layout):
    layout.box().label(text="This will not write any headers/dependencies.")


def makeWriteInfoBox(layout):
    writeBox = layout.box()
    writeBox.label(text="Along with header edits, this will write to:")
    return writeBox


def writeBoxExportType(writeBox, headerType, name, levelName, levelOption):
    if headerType == "Actor":
        writeBox.label(text="actors/" + toAlnum(name))
    elif headerType == "Level":
        if levelOption != "custom":
            levelName = levelOption
        writeBox.label(text="levels/" + toAlnum(levelName) + "/" + toAlnum(name))


def getExportDir(customExport, dirPath, headerType, levelName, texDir, dirName):
    # Get correct directory from decomp base, and overwrite texDir
    if not customExport:
        if headerType == "Actor":
            dirPath = os.path.join(dirPath, "actors")
            texDir = "actors/" + dirName
        elif headerType == "Level":
            dirPath = os.path.join(dirPath, "levels/" + levelName)
            texDir = "levels/" + levelName

    return dirPath, texDir


# Position
def readVectorFromShorts(command, offset):
    return [readFloatFromShort(command, valueOffset) for valueOffset in range(offset, offset + 6, 2)]


def readFloatFromShort(command, offset):
    return int.from_bytes(command[offset : offset + 2], "big", signed=True) / bpy.context.scene.blenderToSM64Scale


def writeVectorToShorts(command, offset, values):
    for i in range(3):
        valueOffset = offset + i * 2
        writeFloatToShort(command, valueOffset, values[i])


def writeFloatToShort(command, offset, value):
    command[offset : offset + 2] = int(round(value * bpy.context.scene.blenderToSM64Scale)).to_bytes(
        2, "big", signed=True
    )


def convertFloatToShort(value):
    return int(round((value * bpy.context.scene.blenderToSM64Scale)))


def convertEulerFloatToShort(value):
    return int(round(degrees(value)))


# Rotation


# Rotation is stored as a short.
# Zero rotation starts at Z+ on an XZ plane and goes counterclockwise.
# 2**16 - 1 is the last value before looping around again.
def readEulerVectorFromShorts(command, offset):
    return [readEulerFloatFromShort(command, valueOffset) for valueOffset in range(offset, offset + 6, 2)]


def readEulerFloatFromShort(command, offset):
    return radians(int.from_bytes(command[offset : offset + 2], "big", signed=True))


def writeEulerVectorToShorts(command, offset, values):
    for i in range(3):
        valueOffset = offset + i * 2
        writeEulerFloatToShort(command, valueOffset, values[i])


def writeEulerFloatToShort(command, offset, value):
    command[offset : offset + 2] = int(round(degrees(value))).to_bytes(2, "big", signed=True)


def tempName(name):
    letters = string.digits
    return name + "_temp" + "".join(random.choice(letters) for i in range(10))


def writeInsertableFile(filepath, dataType, address_ptrs, startPtr, data):
    address = 0
    openfile = open(filepath, "wb")

    # 0-4 - Data Type
    openfile.write(dataType.to_bytes(4, "big"))
    address += 4

    # 4-8 - Data Size
    openfile.seek(address)
    openfile.write(len(data).to_bytes(4, "big"))
    address += 4

    # 8-12 Start Address
    openfile.seek(address)
    openfile.write(startPtr.to_bytes(4, "big"))
    address += 4

    # 12-16 - Number of pointer addresses
    openfile.seek(address)
    openfile.write(len(address_ptrs).to_bytes(4, "big"))
    address += 4

    # 16-? - Pointer address list
    for i in range(len(address_ptrs)):
        openfile.seek(address)
        openfile.write(address_ptrs[i].to_bytes(4, "big"))
        address += 4

    openfile.seek(address)
    openfile.write(data)
    openfile.close()


enumSM64PreInlineGeoLayoutObjects = {"Geo ASM", "Geo Branch", "Geo Displaylist", "Custom Geo Command"}


def checkIsSM64PreInlineGeoLayout(sm64_obj_type):
    return sm64_obj_type in enumSM64PreInlineGeoLayoutObjects


enumSM64InlineGeoLayoutObjects = {
    "Geo ASM",
    "Geo Branch",
    "Geo Translate/Rotate",
    "Geo Translate Node",
    "Geo Rotation Node",
    "Geo Billboard",
    "Geo Scale",
    "Geo Displaylist",
    "Custom Geo Command",
}


def checkIsSM64InlineGeoLayout(sm64_obj_type):
    return sm64_obj_type in enumSM64InlineGeoLayoutObjects


enumSM64EmptyWithGeolayout = {"None", "Level Root", "Area Root", "Switch"}


def checkSM64EmptyUsesGeoLayout(sm64_obj_type):
    return sm64_obj_type in enumSM64EmptyWithGeolayout or checkIsSM64InlineGeoLayout(sm64_obj_type)


def highlightWeightErrors(obj, elements, elementType):
    return  # Doesn't work currently
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="DESELECT")
    bpy.ops.mesh.select_mode(type=elementType)
    bpy.ops.object.mode_set(mode="OBJECT")
    print(elements)
    for element in elements:
        element.select = True
