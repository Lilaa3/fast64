import enum
import math
import bpy
from ...utility_anim import getFrameInterval
from ...utility import toAlnum, PluginError


def animationOperatorChecks(context, requiresAnimData=True):
    if len(context.selected_objects) > 1:
        raise PluginError("Multiple objects selected, make sure to select only one.")
    if len(context.selected_objects) == 0:
        raise PluginError("No armature selected.")

    armatureObj: bpy.types.Object = context.selected_objects[0]

    if not isinstance(armatureObj.data, bpy.types.Armature):
        raise PluginError("Selected object is not an armature.")

    if requiresAnimData and armatureObj.animation_data is None:
        raise PluginError("Armature has no animation data.")

def updateHeaderVariantNumbers(variants):
    for variantNum in range(len(variants)):
        variant: "SM64_AnimHeader" = variants[variantNum]
        variant.headerVariant = variantNum

def getEnumListName(exportProps):
    return f"{exportProps.actorName.title()}Anims"


def animNameToEnum(animName: str):
    enumName = toAlnum(animName).upper()
    if animName == enumName:
        enumName = f"ANIM_{enumName}"
    return enumName


def getAnimEnum(sm64ExportProps, header):
    return animNameToEnum(getAnimName(sm64ExportProps, header))


def getAction(actionName, throwErrors=True):
    if throwErrors:
        if actionName == "":
            raise PluginError("No selected action.")
        if not actionName in bpy.data.actions:
            raise PluginError(f"Action ({actionName}) is not in this file´s action data.")

    if actionName in bpy.data.actions:
        return bpy.data.actions[actionName]


def getSelectedAction(exportProps, throwErrors=True):
    return getAction(exportProps.selectedAction, throwErrors)


def getAnimName(sm64ExportProps, header, throwErrors=True):
    action = header.action
    actionProps = action.fast64.sm64

    if header.overrideName:
        cName = header.customName
    else:
        cName = f"{sm64ExportProps.name}_anim_{action.name}"
        if header.headerVariant != 0:
            mainHeaderName = getAnimName(sm64ExportProps, actionProps.getHeaders()[0])
            cName = f"\
{mainHeaderName}_{header.headerVariant}"

    return toAlnum(cName)


def getAnimFileName(sm64Props, action: bpy.types.Action):
    actionProps = action.fast64.sm64

    if actionProps.overrideFileName:
        return actionProps.customFileName
    
    if sm64Props.export_type == "Insertable Binary":
        return f"anim_{action.name}.insertableBinary"
    else:
        return f"anim_{action.name}.inc.c"


def getActionsInTable(table):
    if not table:
        return []
    actions = []
    for tableElement in table.elements:
        try:
            if tableElement.action not in actions:
                actions.append(tableElement.action)
        except:
            raise PluginError(f'Action "{tableElement.action.name}" in table is not in this file´s action data')

    return actions


def getHeadersInTable(table):
    headers = []
    if not table:
        return headers

    for tableElement in table.elements:
        try:
            actionProps = tableElement.action.fast64.sm64
            headers.append(actionProps.headerFromIndex(tableElement.headerVariant))
        except:
            raise PluginError(f'Action "{tableElement.action.name}" in table is not in this file´s action data')

    return headers


def getMaxFrame(scene, action):
    actionProps = action.fast64.sm64

    if actionProps.overrideMaxFrame:
        return actionProps.customMaxFrame

    loopEnds = [getFrameInterval(action)[1]]
    for header in actionProps.getHeaders():
        startFrame, loopStart, loopEnd = header.getFrameRange()
        loopEnds.append(loopEnd)

    return max(loopEnds)


class ReadArray:
    def __init__(
        self,
        originString: str,
        originPath: str,
        keywords: list[str],
        name: str,
        values: list,
        valuesAndMacros: list,
    ):
        self.originString, self.originPath = originString, originPath
        self.keywords = keywords
        self.name = name
        self.values = values
        self.valuesAndMacros = valuesAndMacros


def string_to_value(string: str):
    string = string.strip()

    if string.startswith("0x"):
        hexValue = string[2:]
        intValue = int(hexValue, 16)
        return intValue

    try:
        return int(string)
    except:
        try:
            return float(string)
        except:
            return string


class CArrayReader:
    def checkForCommentEnd(self, char: str, previousChar: str, charIndex: str):
        # Check if the comment has ended
        if char == "\n" and not self.inMultiLineComment:
            self.inComment = False

        # Check if a comment has ended in a multi-line comment
        if self.inMultiLineComment and previousChar == "*" and char == "/":
            if self.comentStart > self.keywordStart < charIndex:
                self.keywordStart = charIndex + 1

            if self.comentStart > self.valueStart < charIndex:
                self.valueStart = charIndex + 1

            self.inComment = False
            self.inMultiLineComment = False

        if not self.inComment and self.readingKeywords:
            if self.comentStart > self.keywordsStart < charIndex:
                self.keywordsStart = charIndex + 1
            if self.comentStart > self.keywordStart < charIndex:
                self.keywordStart = charIndex + 1

    def checkForComments(self, char: str, previousChar: str, charIndex: str):
        # Single line comment
        if previousChar == "/" and char == "/":
            # Single line comment detected
            self.comentStart = charIndex
            self.inComment = True

        # Multi-line comment
        if previousChar == "/" and char == "*":
            self.comentStart = charIndex
            self.inComment = True
            self.inMultiLineComment = True

    def readMacros(self, char, charIndex: str):
        if self.readingMacroDef:
            macroString = self.text[self.macroStart : charIndex]
            if macroString in ["ifdef", "ifndef", "elif", "else", "endif"]:
                self.macroString, self.macroDefStart = macroString, charIndex + 1
                self.readingMacroDef = False
        if char != "\n":
            return

        macroDefinesString = self.text[self.macroDefStart : charIndex]
        macroDefinesStriped = macroDefinesString.replace(" ", "").replace("\t", "")
        macroDefines = macroDefinesStriped.split("|")

        for macro in macroDefines:
            if self.macroString == "ifdef":
                self.macroDefines.add(macro)
            elif self.macroString == "ifndef":
                self.excludedMacroDefines.add(macro)

        if self.macroStart > self.valueStart < charIndex:
            self.valueStart = charIndex + 1
        if self.readingKeywords:
            if self.macroStart > self.keywordsStart < charIndex:
                self.keywordsStart = charIndex + 1
            if self.macroStart > self.keywordStart < charIndex:
                self.keywordStart = charIndex + 1

        self.readingMacro = False

    def checkForMacroStart(self, char, charIndex: str):
        if char == "#":  # Start of macro
            self.macroStart = charIndex + 1
            self.readingMacro, self.readingMacroDef = True, True

    def readKeywords(self, char: str, charIndex: str):
        if char in ["\n", ";"]:
            self.keywordsStart = charIndex + 1
            self.keywordStart = self.keywordsStart

        elif char in ["[", " ", "{", "="]:
            keyword = self.text[self.keywordStart : charIndex]
            if keyword not in [" ", ""]:
                self.keywords.append(self.text[self.keywordStart : charIndex].strip())

            self.keywordStart = charIndex + 1

            if char in ["[", "=", "{"]:
                self.readingKeywords = False

    def readValues(self, char: str, previousChar: str, charIndex: str):
        if self.stack == 0 and char == "}":
            textStart, textEnd = self.keywordsStart, self.text.find(";", charIndex) + 1
            structData = ReadArray(
                self.text[textStart:textEnd],
                self.originPath,
                self.keywords[:-1],
                self.keywords[-1],
                self.values,
                self.valuesAndMacros,
            )
            self.arrays[structData.name] = structData
            self.readingKeywords = True
            self.keywords = []
            self.values, self.valuesAndMacros = [], []
            self.enumIndex = 0
            self.readingValues = False

        elif char in ["(", "{"]:
            self.stack += 1
        elif char in [")", "}"]:
            self.stack -= 1
        elif self.stack == 0 and char == ",":
            value = self.text[self.valueStart : charIndex]

            value = string_to_value(self.text[self.valueStart : charIndex])
            if isinstance(value, str):
                if value.startswith("["):
                    # Enum indexed
                    enumValue = value.split("=")
                    enumName = enumValue[0].strip().replace("[", "").replace("]", "")
                    value = (enumName, string_to_value(enumValue[1]))

                elif "struct" in self.keywords and value.startswith("."):
                    # Designated initializer
                    nameValue = value.split("=")
                    value = (nameValue[0].replace(".", ""), string_to_value(nameValue[1]))

                elif "enum" in self.keywords:
                    if "=" in value:
                        enumValue = value.split("=")
                        value = (enumValue[0].replace(" ", ""), string_to_value(enumValue[1]))

            self.values.append(value)
            self.valuesAndMacros.append((value, self.macroDefines.copy(), self.excludedMacroDefines.copy()))
            self.valueStart = charIndex + 1

    def readChar(self, char: str, previousChar: str, charIndex: str):
        if not self.inComment:
            self.checkForComments(char, previousChar, charIndex)
        if self.inComment:
            self.checkForCommentEnd(char, previousChar, charIndex)
            return  # If not in comment continue parsing

        if not self.readingMacro:
            self.checkForMacroStart(char, charIndex)
        if self.readingMacro:
            self.readMacros(char, charIndex)
            return  # If not reading macros

        if self.readingKeywords:
            self.readKeywords(char, charIndex)
        elif self.readingValues:  # data after "={"
            self.readValues(char, previousChar, charIndex)
        # In between stage, = or [] has been reached so we are no longer reading keywords
        # but we are still not reading values until the first "{""
        if not self.readingKeywords and not self.readingValues:
            if char == "{":
                self.readingValues = True
                self.valueStart = charIndex + 1

    def findAllCArraysInFile(self, text: str, originPath: str = ""):
        """
        Parses the provided string for arrays.
        """
        self.text = text
        self.originPath = originPath

        self.macroDefStart, self.macroString = 0, ""
        self.macroDefines, self.excludedMacroDefines = set(), set()

        self.inComment, self.inMultiLineComment = False, False
        self.readingMacro, self.readingKeywords, self.readingValues = False, True, False

        self.keywordsStart, self.keywordStart, self.valueStart = 0, 0, 0

        self.stack = 0

        self.keywords = []
        self.values, self.valuesAndMacros = [], []

        self.arrays: dict[str, ReadArray] = {}

        previousChar = ""
        for charIndex, char in enumerate(self.text):
            self.readChar(char, previousChar, charIndex)
            previousChar = char

        return self.arrays


def readArrayToStructDict(array: ReadArray, structDefinition: list[str]):
    structDict = {}
    for i, element in enumerate(array.values):
        if isinstance(element, tuple):
            structDict[element[0]] = element[1]
        else:
            structDict[structDefinition[i]] = element
    return structDict


def sm64ToRadian(signedSM64Angle: int) -> float:
    SM64Angle = int.from_bytes(signedSM64Angle.to_bytes(4, "big", signed=True), "big", signed=False)
    degree = SM64Angle * (360.0 / (2.0**16.0))
    return math.radians(degree % 360.0)
