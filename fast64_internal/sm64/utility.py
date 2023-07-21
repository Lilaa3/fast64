import math, operator, os, re, bpy

from ..utility import PluginError, to_s16, toAlnum

def starSelectWarning(operator, fileStatus):
    if fileStatus is not None and not fileStatus.starSelectC:
        operator.report({"WARNING"}, "star_select.c not found, skipping star select scrolling.")


def cameraWarning(operator, fileStatus):
    if fileStatus is not None and not fileStatus.cameraC:
        operator.report({"WARNING"}, "camera.c not found, skipping camera volume and zoom mask exporting.")


ULTRA_SM64_MEMORY_C = "src/boot/memory.c"
SM64_MEMORY_C = "src/game/memory.c"


def getMemoryCFilePath(decompDir):
    isUltra = os.path.exists(os.path.join(decompDir, ULTRA_SM64_MEMORY_C))
    relPath = ULTRA_SM64_MEMORY_C if isUltra else SM64_MEMORY_C
    return os.path.join(decompDir, relPath)


def apply_basic_tweaks(export_settings: "SM64_ExportSettings"):
    from .properties import SM64_ExportSettings
    export_settings: SM64_ExportSettings = export_settings

    if export_settings.header_type == "Custom":
        return

    if export_settings.decomp_path == "":
        raise PluginError("Empty decomp folder.")
    if not os.path.exists(export_settings.decomp_path):
        raise PluginError(
            f"Decomp folder ({export_settings.decomp_path}) does not exist. If you are using WSL mounted as a network drive, make sure it is on."
        )
    if not os.path.isdir(export_settings.decomp_path):
        raise PluginError(f"Decomp folder ({export_settings.decomp_path}) is not a directory.")

    enableExtendedRAM(export_settings.decomp_path)


def enableExtendedRAM(decompFolder: str):
    if not bpy.context.scene.fast64.sm64.set_extended_ram:
        return

    segmentPath = os.path.join(decompFolder, "include/segments.h")

    if not os.path.isfile(decompFolder):
        raise PluginError(f"segment.h file does not exist at {segmentPath}")

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


class BoneInfo:
    def __init__(self, bone, poseBone, name):
        self.children = []
        self.parent = None

        self.bone = bone
        self.poseBone = poseBone
        self.name = name

        self.cmd = bone.fast64.sm64.geo_cmd

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return self.name

    def find_parents_and_childs(self, bone_info):
        for bone in bone_info:
            if self.bone.parent == bone.bone:
                self.parent = bone
                break

        for child in self.bone.children:
            for bone in bone_info:
                if bone.bone == child:
                    child = bone
                    break

            self.children.append(child)

            child.find_parents_and_childs(bone_info)

        self.children.sort(key=operator.attrgetter("name"))


def getBonesInfo(armatureObj: bpy.types.Object) -> tuple[list[BoneInfo], list[BoneInfo]]:
    from .geolayout.utility import find_start_bones

    bonesInfo = []
    animBonesInfo = []

    rootBones = find_start_bones(armatureObj)

    bonesToProcess = rootBones

    # Get bones in order
    while len(bonesToProcess) > 0:
        boneName = bonesToProcess[0]
        bonesToProcess = bonesToProcess[1:]

        bone = armatureObj.data.bones[boneName]
        poseBone = armatureObj.pose.bones[boneName]

        boneInfo = BoneInfo(bone, poseBone, boneName)
        bonesInfo.append(boneInfo)

        if bone.fast64.sm64.is_animatable():
            animBonesInfo.append(boneInfo)

        # Traverse children in alphabetical order.
        childNames = sorted([child.name for child in bone.children])
        bonesToProcess = childNames + bonesToProcess

    bonesInfo[0].find_parents_and_childs(bonesInfo)
    return animBonesInfo, bonesInfo


def normalize_degree(degree_angle: float):
    return round(degree_angle, 5) % 360.0

def degree_to_sm64_degree(degree: float, as_s16=True) -> int:
    normalized_degree = normalize_degree(degree)
    sm64_degree = int((normalized_degree / 360.0) * (2**16))

    if as_s16:
        sm64_degree = to_s16(sm64_degree)

    return sm64_degree

def radian_to_sm64_degree(radian: float, as_s16=True) -> int:
    return degree_to_sm64_degree(math.degrees(radian), as_s16)

def checkExpanded(filepath: str):
    if os.path.exists(filepath):
        PluginError(f"ROM path ({filepath}) does not exist.")
        return

    if not os.path.isfile(filepath):
        PluginError(f"ROM path ({filepath}) is not a file.")
        return

    size = os.path.getsize(filepath)
    if size < 9000000:  # check if 8MB
        raise PluginError(
            "ROM at "
            + filepath
            + " is too small. You may be using an unexpanded ROM. You can expand a ROM by opening it in SM64 Editor or ROM Manager."
        )


def decompFolderMessage(layout):
    layout.label(text="This will export to your decomp folder.")


def checkIfPathExists(filePath):
    if not os.path.exists(filePath):
        raise PluginError(filePath + " does not exist.")


def makeWriteInfoBox(layout):
    writeBox = layout.box().column()
    writeBox.label(text="Along with header edits, this will write to:")
    return writeBox


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


def box_sm64_panel(layout: bpy.types.UILayout):
    return layout.box().column()

def draw_error(layout: bpy.types.UILayout, text: str):
    layout.box().label(text=text, icon="ERROR")

def directory_path_checks(directory_path: str):
    if directory_path == "":
        raise PluginError("Empty directory.")
    elif not os.path.exists(directory_path):
        raise PluginError("Directory does not exist.")
    elif not os.path.isdir(directory_path):
        raise PluginError("Path is not a directory.")

def directory_ui_warnings(layout: bpy.types.UILayout, directory_path: str):
    try:
        directory_path_checks(directory_path)
    except Exception as e:
        draw_error(layout, str(e))

def file_path_checks(file_path: str):
    if file_path == "":
        raise PluginError("Empty path.")
    elif not os.path.exists(file_path):
        raise PluginError("File does not exist.")
    elif not os.path.isfile(file_path):
        raise PluginError("Path is not a file.")

def file_ui_warnings(layout: bpy.types.UILayout, file_path: str):
    try:
        file_path_checks(file_path)
    except Exception as e:
        draw_error(layout, str(e))

def path_checks(path: str):
    if path == "":
        raise PluginError("Empty path.")
    elif not os.path.exists(path):
        raise PluginError("Path does not exist.")

def path_ui_warnings(layout: bpy.types.UILayout, path: str):
    try:
        path_checks(path)
    except Exception as e:
        draw_error(layout, str(e))

