from ...utility import PluginError
from ..utility import getHeaderSettings
from .constants import headerNames


class SharedSceneData:
    def __init__(
        self,
        scenePath: str,
        scene_name: str,
        includeMesh: bool,
        includeCollision: bool,
        includeActors: bool,
        includeCullGroups: bool,
        includeLights: bool,
        includeCameras: bool,
        includePaths: bool,
        includeWaterBoxes: bool,
        includeCutscenes: bool,
        is_single_file: bool,
        is_fast64_data: bool,
        not_zapd_assets: bool,
    ):
        self.actorDict = {}  # actor hash : blender object
        self.entranceDict = {}  # actor hash : blender object
        self.transDict = {}  # actor hash : blender object
        self.pathDict = {}  # path hash : blender object

        self.scenePath = scenePath
        self.scene_name = scene_name
        self.includeMesh = includeMesh
        self.includeCollision = includeCollision
        self.includeActors = includeActors
        self.includeCullGroups = includeCullGroups
        self.includeLights = includeLights
        self.includeCameras = includeCameras
        self.includePaths = includePaths
        self.includeWaterBoxes = includeWaterBoxes
        self.includeCutscenes = includeCutscenes
        self.is_single_file = is_single_file
        self.is_fast64_data = is_fast64_data
        self.not_zapd_assets = not_zapd_assets

    def addHeaderIfItemExists(self, hash, itemType: str, headerIndex: int):
        if itemType == "Actor":
            dictToAdd = self.actorDict
        elif itemType == "Entrance":
            dictToAdd = self.entranceDict
        elif itemType == "Transition Actor":
            dictToAdd = self.transDict
        elif itemType == "Curve":
            dictToAdd = self.pathDict
        else:
            raise PluginError(f"Invalid empty type for shared actor handling: {itemType}")

        if hash not in dictToAdd:
            return False

        actorObj = dictToAdd[hash]
        headerSettings = getHeaderSettings(actorObj)

        if headerIndex < 4:
            setattr(headerSettings, headerNames[headerIndex], True)
        else:
            cutsceneHeaders = headerSettings.cutsceneHeaders
            if len([header for header in cutsceneHeaders if header.headerIndex == headerIndex]) == 0:
                cutsceneHeaders.add().headerIndex = headerIndex

        return True
