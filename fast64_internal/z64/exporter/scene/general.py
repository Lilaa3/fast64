import re

from dataclasses import dataclass
from bpy.types import Object

from ....utility import PluginError, CData, exportColor, ootGetBaseOrCustomLight, hexOrDecInt, indent
from ...scene.properties import OOTSceneHeaderProperty, OOTLightProperty
from ...utility import getEvalParamsInt
from ..utility import Utility


@dataclass
class EnvLightSettings:
    """This class defines the information of one environment light setting"""

    envLightMode: str
    ambientColor: tuple[int, int, int]
    light1Color: tuple[int, int, int]
    light1Dir: tuple[int, int, int]
    light2Color: tuple[int, int, int]
    light2Dir: tuple[int, int, int]
    fogColor: tuple[int, int, int]
    fogNear: int
    zFar: int
    blendRate: int

    @staticmethod
    def from_data(raw_data: str, not_zapd_assets: bool):
        lights: list[EnvLightSettings] = []
        split_str = ",},{" if not_zapd_assets else "},{"
        entries = raw_data.removeprefix("{").removesuffix("},").split(split_str)

        for entry in entries:
            if not_zapd_assets:
                colors_and_dirs = []
                for match in re.finditer(r"(\{([0-9\-]*,[0-9\-]*,[0-9\-]*)\})", entry, re.DOTALL):
                    colors_and_dirs.append([hexOrDecInt(value) for value in match.group(2).split(",")])

                blend_and_fogs = entry.split("},")[-1].split(",")
                blend_split = blend_and_fogs[0].split("|")
                blend_raw = blend_split[0]
                fog_near = hexOrDecInt(blend_split[1])
                z_far = hexOrDecInt(blend_and_fogs[1])
                blend_rate = getEvalParamsInt(blend_raw)
                assert blend_rate is not None

                if "/" in blend_raw:
                    blend_rate *= 4
            else:
                split = entry.split(",")

                colors_and_dirs = [
                    [hexOrDecInt(value) for value in split[0:3]],
                    [hexOrDecInt(value) for value in split[3:6]],
                    [hexOrDecInt(value) for value in split[6:9]],
                    [hexOrDecInt(value) for value in split[9:12]],
                    [hexOrDecInt(value) for value in split[12:15]],
                    [hexOrDecInt(value) for value in split[15:18]],
                ]

                blend_rate = hexOrDecInt(split[18]) >> 10
                fog_near = hexOrDecInt(split[18]) & 0x3FF
                z_far = hexOrDecInt(split[19])

            lights.append(
                EnvLightSettings(
                    "Custom",
                    tuple(colors_and_dirs[0]),
                    tuple(colors_and_dirs[1]),
                    tuple(colors_and_dirs[2]),
                    tuple(colors_and_dirs[3]),
                    tuple(colors_and_dirs[4]),
                    tuple(colors_and_dirs[5]),
                    fog_near,
                    z_far,
                    blend_rate,
                )
            )

        return lights

    def getBlendFogNear(self):
        """Returns the packed blend rate and fog near values"""

        return f"(({self.blendRate} << 10) | {self.fogNear})"

    def getColorValues(self, vector: tuple[int, int, int]):
        """Returns and formats color values"""

        return ", ".join(f"{v:5}" for v in vector)

    def getDirectionValues(self, vector: tuple[int, int, int]):
        """Returns and formats direction values"""

        return ", ".join(f"{v - 0x100 if v > 0x7F else v:5}" for v in vector)

    def getEntryC(self, index: int):
        """Returns an environment light entry"""

        isLightingCustom = self.envLightMode == "Custom"

        vectors = [
            (self.ambientColor, "Ambient Color", self.getColorValues),
            (self.light1Dir, "Diffuse0 Direction", self.getDirectionValues),
            (self.light1Color, "Diffuse0 Color", self.getColorValues),
            (self.light2Dir, "Diffuse1 Direction", self.getDirectionValues),
            (self.light2Color, "Diffuse1 Color", self.getColorValues),
            (self.fogColor, "Fog Color", self.getColorValues),
        ]

        fogData = [
            (self.getBlendFogNear(), "Blend Rate & Fog Near"),
            (f"{self.zFar}", "Fog Far"),
        ]

        lightDescs = ["Dawn", "Day", "Dusk", "Night"]

        if not isLightingCustom and self.envLightMode == "LIGHT_MODE_TIME":
            # TODO: Improve the lighting system.
            # Currently Fast64 assumes there's only 4 possible settings for "Time of Day" lighting.
            # This is not accurate and more complicated,
            # for now we are doing ``index % 4`` to avoid having an OoB read in the list
            # but this will need to be changed the day the lighting system is updated.
            lightDesc = f"// {lightDescs[index % 4]} Lighting\n"
        else:
            isIndoor = not isLightingCustom and self.envLightMode == "LIGHT_MODE_SETTINGS"
            lightDesc = f"// {'Indoor' if isIndoor else 'Custom'} No. {index + 1} Lighting\n"

        lightData = (
            (indent + lightDesc)
            + (indent + "{\n")
            + "".join(
                indent * 2 + f"{'{ ' + vecToC(vector) + ' },':26} // {desc}\n" for (vector, desc, vecToC) in vectors
            )
            + "".join(indent * 2 + f"{fogValue + ',':26} // {fogDesc}\n" for fogValue, fogDesc in fogData)
            + (indent + "},\n")
        )

        return lightData


@dataclass
class SceneLighting:
    """This class hosts lighting data"""

    name: str
    envLightMode: str
    settings: list[EnvLightSettings]

    @staticmethod
    def new(name: str, props: OOTSceneHeaderProperty):
        envLightMode = Utility.getPropValue(props, "skyboxLighting")
        lightList: dict[str, OOTLightProperty] = {}
        settings: list[EnvLightSettings] = []

        if envLightMode == "LIGHT_MODE_TIME":
            todLights = props.timeOfDayLights
            lightList = {"Dawn": todLights.dawn, "Day": todLights.day, "Dusk": todLights.dusk, "Night": todLights.night}
        else:
            lightList = {str(i): light for i, light in enumerate(props.lightList)}

        for setting_name, lightProp in lightList.items():
            try:
                light1 = ootGetBaseOrCustomLight(lightProp, 0, True, True)
                light2 = ootGetBaseOrCustomLight(lightProp, 1, True, True)
                settings.append(
                    EnvLightSettings(
                        envLightMode,
                        exportColor(lightProp.ambient),
                        light1[0],
                        light1[1],
                        light2[0],
                        light2[1],
                        exportColor(lightProp.fogColor),
                        lightProp.fogNear,
                        lightProp.z_far,
                        lightProp.transitionSpeed,
                    )
                )
            except Exception as exc:
                raise PluginError(f"In light settings {setting_name}: {exc}") from exc
        return SceneLighting(name, envLightMode, settings)

    def getCmd(self):
        """Returns the env light settings scene command"""

        return (
            indent + "SCENE_CMD_ENV_LIGHT_SETTINGS("
        ) + f"{len(self.settings)}, {self.name if len(self.settings) > 0 else 'NULL'}),\n"

    def getC(self):
        """Returns a ``CData`` containing the C data of env. light settings"""

        lightSettingsC = CData()
        lightName = f"EnvLightSettings {self.name}[{len(self.settings)}]"

        # .h
        lightSettingsC.header = f"extern {lightName};\n"

        # .c
        lightSettingsC.source = (
            (lightName + " = {\n") + "".join(light.getEntryC(i) for i, light in enumerate(self.settings)) + "};\n\n"
        )

        return lightSettingsC


@dataclass
class SceneInfos:
    """This class stores various scene header informations"""

    ### General ###

    keepObjectID: str
    naviHintType: str
    drawConfig: str
    appendNullEntrance: bool
    useDummyRoomList: bool
    title_card_name: str

    ### Skybox And Sound ###

    # Skybox
    skyboxID: str
    skyboxConfig: str

    # Sound
    sequenceID: str
    ambienceID: str
    specID: str

    ### Camera And World Map ###

    # World Map
    worldMapLocation: str

    # Camera
    sceneCamType: str

    @staticmethod
    def new(props: OOTSceneHeaderProperty, sceneObj: Object):
        return SceneInfos(
            Utility.getPropValue(props, "globalObject"),
            Utility.getPropValue(props, "naviCup"),
            Utility.getPropValue(props.sceneTableEntry, "drawConfig"),
            props.appendNullEntrance,
            sceneObj.fast64.oot.scene.write_dummy_room_list,
            Utility.getPropValue(props, "title_card_name"),
            Utility.getPropValue(props, "skyboxID"),
            Utility.getPropValue(props, "skyboxCloudiness"),
            Utility.getPropValue(props, "musicSeq"),
            Utility.getPropValue(props, "nightSeq"),
            Utility.getPropValue(props, "audioSessionPreset"),
            Utility.getPropValue(props, "mapLocation"),
            Utility.getPropValue(props, "cameraMode"),
        )

    def getCmds(self, lights: SceneLighting):
        """Returns the sound settings, misc settings, special files and skybox settings scene commands"""

        return (
            indent
            + f",\n{indent}".join(
                [
                    f"SCENE_CMD_SOUND_SETTINGS({self.specID}, {self.ambienceID}, {self.sequenceID})",
                    f"SCENE_CMD_MISC_SETTINGS({self.sceneCamType}, {self.worldMapLocation})",
                    f"SCENE_CMD_SPECIAL_FILES({self.naviHintType}, {self.keepObjectID})",
                    f"SCENE_CMD_SKYBOX_SETTINGS({self.skyboxID}, {self.skyboxConfig}, {lights.envLightMode})",
                ]
            )
            + ",\n"
        )


@dataclass
class SceneExits(Utility):
    """This class hosts exit data"""

    name: str
    exitList: list[tuple[int, str]]

    @staticmethod
    def new(name: str, props: OOTSceneHeaderProperty):
        # TODO: proper implementation of exits

        exitList: list[tuple[int, str]] = []
        for i, exitProp in enumerate(props.exitList):
            if exitProp.exitIndex != "Custom":
                raise PluginError("ERROR: Exits are unfinished, please use 'Custom'.")
            exitList.append((i, exitProp.exitIndexCustom))
        return SceneExits(name, exitList)

    def getCmd(self):
        """Returns the exit list scene command"""

        return indent + f"SCENE_CMD_EXIT_LIST({self.name}),\n"

    def getC(self):
        """Returns a ``CData`` containing the C data of the exit array"""

        exitListC = CData()
        listName = f"s16 {self.name}[{len(self.exitList)}]"

        # .h
        exitListC.header = f"extern {listName};\n"

        # .c
        exitListC.source = (
            (listName + " = {\n")
            # @TODO: use the enum name instead of the raw index
            + "\n".join(indent + f"{value}," for (_, value) in self.exitList)
            + "\n};\n\n"
        )

        return exitListC
