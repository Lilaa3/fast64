from dataclasses import dataclass
from ..fast64_internal.utility import gammaCorrect


@dataclass
class FlagAttrToGlTFInfo:
    flag: str
    materialAttr: str


def flagAttrsToGlTFArray(materialSettings, enumAttributesInfo: dict[FlagAttrToGlTFInfo]):
    data = []
    for info in enumAttributesInfo:
        if getattr(materialSettings, info.materialAttr) == True:
            data.append(info.flag)
    return data


class TypeToGlTF:
    def __init__(self, typeName: str, function=None):
        self.typeName = typeName
        self.function = function

    def toGltf(self, obj):
        if isinstance(self.function, dict):
            data = {}
            for key in self.function:
                data[key] = getattr(obj, self.function[key])
            return data
        if isinstance(self.function, str):
            return getattr(obj, self.function)
        elif self.function:
            return self.function(obj)


def blenderColorToGlTFColor(color, hasAlpha=False) -> list:
    correctColor = [round(channel, 3) for channel in gammaCorrect(color)]
    if hasAlpha:
        correctColor.append(color[3])

    return correctColor


def appendGlTF2Extension(extension, extensionName, gltf2Object, dataDictionary):
    for (key, value) in dataDictionary.copy().items():
        # For some reason, the glTF exporter is not doing this for the sm64 extension.
        if value is None or (isinstance(value, dict) and not any(value)):
            dataDictionary.pop(key)

    if not any(dataDictionary):
        return

    if gltf2Object.extensions is None:
        gltf2Object.extensions = {}

    gltf2Object.extensions[extensionName] = extension.Extension(
        name=extensionName,
        extension=dataDictionary,
        required=False,
    )
