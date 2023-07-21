import dataclasses
from io import StringIO
import os
from typing import BinaryIO

from ..constants import MAX_U16

from .utility import ReadArray, readArrayToStructDict, updateHeaderVariantNumbers
from ...utility import PluginError, RomReading, decodeSegmentedAddr, isBitActive, toAlnum, arrayToC, structToC


@dataclasses.dataclass
class SM64_AnimHeader:
    name: str = None
    address: int = None
    headerVariant: int = 0
    flags: str | int = None
    yDivisor: int = 0
    startFrame: int = 0
    loopStart: int = 0
    loopEnd: int = 1
    boneCount: int = None
    values: str = ""
    indices: str = ""
    data: "SM64_Anim" = None

    def toC(self, designated: bool, asArray: bool) -> str:
        headerData: list[tuple[str, object]] = [
            ("flags", self.flags),
            ("animYTransDivisor", self.yDivisor),
            ("startFrame", self.startFrame),
            ("loopStart", self.loopStart),
            ("loopEnd", self.loopEnd),
            ("unusedBoneCount", f"ANIMINDEX_NUMPARTS({self.data.indicesReference})"),  # Unused but potentially useful
            ("values", self.data.valuesReference),
            ("index", self.data.indicesReference),
            ("length", 0),  # Unused with no porpuse
        ]
        return structToC(
            self.name,
            "static const struct Animation",
            headerData,
            designated,
            asArray,
        )

    def toBinary(self, indicesReference, valuesReference):
        data = bytearray()
        data.extend(self.flags.to_bytes(2, byteorder="big", signed=False))  # 0x00
        data.extend(self.yDivisor.to_bytes(2, byteorder="big", signed=True))  # 0x02
        data.extend(self.startFrame.to_bytes(2, byteorder="big", signed=True))  # 0x04
        data.extend(self.loopStart.to_bytes(2, byteorder="big", signed=True))  # 0x06
        data.extend(self.loopEnd.to_bytes(2, byteorder="big", signed=True))  # 0x08
        data.extend(self.boneCount.to_bytes(2, byteorder="big", signed=True))  # 0x0A
        data.extend(valuesReference.to_bytes(4, byteorder="big", signed=False))  # 0x0C
        data.extend(indicesReference.to_bytes(4, byteorder="big", signed=False))  # 0x10
        data.extend(bytearray([0x00] * 4))  # 0x14 # Unused with no porpuse
        # 0x18
        return data

    # Importing
    def toHeaderProps(self, action, header):
        intFlagsToProps = {
            "ANIM_FLAG_NOLOOP": "noLoop",
            "ANIM_FLAG_BACKWARD": "backward",
            "ANIM_FLAG_NO_ACCEL": "noAcceleration",
            "ANIM_FLAG_DISABLED": "disabled",
        }
        intFlagsToString = {
            0: "ANIM_FLAG_NOLOOP",
            1: "ANIM_FLAG_BACKWARD",
            2: "ANIM_FLAG_NO_ACCEL",
            3: "ANIM_FLAG_HOR_TRANS",
            4: "ANIM_FLAG_VERT_TRANS",
            5: "ANIM_FLAG_DISABLED",
            6: "ANIM_FLAG_NO_TRANS",
            7: "ANIM_FLAG_UNUSED",
        }

        header.action = action

        if self.name:
            header.overrideName = True
            header.customName = self.name

        correctFrameRange = self.startFrame, self.loopStart, self.loopEnd
        header.startFrame, header.loopStart, header.loopEnd = correctFrameRange
        if correctFrameRange != header.getFrameRange():  # If auto frame range is wrong
            header.manualFrameRange = True

        header.yDivisor = self.yDivisor

        if isinstance(self.flags, int):
            header.customIntFlags = hex(self.flags)
            cFlags = [flag for bit, flag in intFlagsToString.items() if isBitActive(self.flags, bit)]
            header.customFlags = " | ".join(cFlags)
            for cFlag in cFlags:
                if cFlag in intFlagsToProps:
                    setattr(header, intFlagsToProps[cFlag], True)
                else:
                    header.setCustomFlags = True
        else:
            header.setCustomFlags = True
            header.customFlags = self.flags

    def readBinary(self, romfile: BinaryIO, address: int, segmentData, isDMA: bool = False):
        headerReader = RomReading(romfile, address)

        self.address = address
        self.flags = headerReader.readValue(2, signed=False)  # /*0x00*/ s16 flags;
        self.yDivisor = headerReader.readValue(2)  # /*0x02*/ s16 animYTransDivisor;
        self.startFrame = headerReader.readValue(2)  # /*0x04*/ s16 startFrame;
        self.loopStart = headerReader.readValue(2)  # /*0x06*/ s16 loopStart;
        self.loopEnd = headerReader.readValue(2)  # /*0x08*/ s16 loopEnd;
        # Unused in engine but makes it easy to read animation data
        self.boneCount = headerReader.readValue(2)  # /*0x0A*/ s16 unusedBoneCount;

        valuesOffset = headerReader.readValue(4)  # /*0x0C*/ const s16 *values;
        indicesOffset = headerReader.readValue(4)  # /*0x10*/ const u16 *index;

        if isDMA:
            self.values = address + valuesOffset
            self.indices = address + indicesOffset
        else:
            self.values = decodeSegmentedAddr(valuesOffset.to_bytes(4, byteorder="big"), segmentData)
            self.indices = decodeSegmentedAddr(indicesOffset.to_bytes(4, byteorder="big"), segmentData)

    def readC(self, array: ReadArray):
        self.name = toAlnum(array.name)

        structDict = readArrayToStructDict(
            array,
            [
                "flags",
                "animYTransDivisor",
                "startFrame",
                "loopStart",
                "loopEnd",
                "unusedBoneCount",
                "values",
                "index",
                "length",
            ],
        )

        self.flags = structDict["flags"]
        self.yDivisor = structDict["animYTransDivisor"]
        self.startFrame = structDict["startFrame"]
        self.loopStart = structDict["loopStart"]
        self.loopEnd = structDict["loopEnd"]

        self.values = structDict["values"]
        self.indices = structDict["index"]
        return


@dataclasses.dataclass
class SM64_AnimPair:
    bestFrameAmounts: bool = True
    maxFrame: int = 1
    values: list[int] = dataclasses.field(default_factory=list)

    def appendFrame(self, value: int):
        if self.bestFrameAmounts:
            if len(self.values) >= 1:
                lastValue = self.values[-1]

                if abs(value - lastValue) > 2:  # 2 is a good max difference, basically invisible in game.
                    self.maxFrame = len(self.values) + 1
        else:
            self.maxFrame = len(self.values) + 1

        self.values.append(value)

    def getFrame(self, frame: int):
        if frame < len(self.values):
            return self.values[frame]
        return self.values[len(self.values) - 1]

    # Importing
    def readBinary(self, indicesReader: RomReading, romfile: BinaryIO, valuesAdress: int):
        maxFrame = indicesReader.readValue(2)
        valueOffset = indicesReader.readValue(2) * 2

        valueReader = RomReading(romfile, valuesAdress + valueOffset)
        for frame in range(maxFrame):
            value = valueReader.readValue(2, signed=True)
            self.values.append(value)

    def readC(self, maxFrame, offset, values: list[int]):
        for frame in range(maxFrame):
            value = values[offset + frame]
            if value >= 0:  # Cast any positive to signed.
                value = int.from_bytes(
                    value.to_bytes(length=2, byteorder="big", signed=False), signed=True, byteorder="big"
                )
            self.values.append(value)


headerSize = 0x18


@dataclasses.dataclass
class SM64_Anim:
    indicesReference: str = ""
    valuesReference: str = ""
    reference: bool = False
    isDmaStructure: bool = False
    headers: list[SM64_AnimHeader] = dataclasses.field(default_factory=list)
    pairs: list[SM64_AnimPair] = dataclasses.field(default_factory=list)
    actionName: str = None
    fileName: str = None

    def createTables(self, merge: bool) -> tuple[list[int], list[int]]:
        def findOffset(addedIndexes, pairValues) -> int | None:
            offset: int | None = None
            for addedIndex in addedIndexes:
                # TODO: If the added index values are less than the values of the current pair
                # but the values that it does have are all equal to the pair´s, add the rest of
                # the values to the added index values.
                if len(addedIndex.values) < len(pairValues):
                    continue
                for i, j in zip(pairValues, addedIndex.values[0 : len(pairValues)]):
                    offset = addedIndex.offset
                    if abs(i - j) > 2:  # 2 is a good max difference, basically invisible in game.
                        offset = None
                        break
            return offset

        print("Merging values and creating tables.")

        valueTable, indicesTable, addedIndexes = [], [], []

        for pair in self.pairs:
            maxFrame: int = pair.maxFrame
            pairValues: list[int] = pair.values[0:maxFrame]

            existingOffset: int | None = None
            if merge:
                existingOffset = findOffset(addedIndexes, pairValues)

            if existingOffset is None:
                offset: int = len(valueTable)
                pair.offset = offset
                valueTable.extend(pairValues)

                addedIndexes.append(pair)
            else:
                offset: int = existingOffset

            if offset > MAX_U16:
                raise PluginError("Index pair´s value offset is too high. Value table might be too long.")

            indicesTable.extend([maxFrame, offset])

        return valueTable, indicesTable

    def headersToC(self, designated: bool, asArray: bool) -> str:
        cData = StringIO()
        for header in self.headers:
            cData.write(header.toC(designated, asArray))
        return cData.getvalue()

    def toBinary(self, mergeValues: bool, isDMA: bool, startAddress: int) -> bytearray:
        data: bytearray = bytearray()
        ptrs: list[int] = []

        if self.reference:
            for header in self.headers:
                headerData = header.toBinary(self.indicesReference, self.valuesReference)
                data.extend(headerData)
            return data, []

        valueTable, indicesTable = self.createTables(mergeValues)

        indicesOffset = headerSize * len(self.headers)
        valuesOffset = indicesOffset + (len(indicesTable) * 2)
        indicesReference, valuesReference = startAddress + indicesOffset, startAddress + valuesOffset

        for header in self.headers:
            ptrs.extend([startAddress + len(data) + 12, startAddress + len(data) + 16])
            headerData = header.toBinary(indicesReference, valuesReference)
            data.extend(headerData)

        for value in indicesTable:
            data.extend(value.to_bytes(2, byteorder="big", signed=False))
        for value in valueTable:
            data.extend(value.to_bytes(2, byteorder="big", signed=True))
        
        if isDMA:
            return data, []
        return data, ptrs

    def toC(self, mergeValues: bool, useHexValues: bool, explicitArraySize: bool) -> str:
        if self.reference:
            return

        valueTable, indicesTable = self.createTables(mergeValues)

        cData = StringIO()
        cData.write(
            arrayToC(
                self.indicesReference,
                "static const u16",
                indicesTable,
                explicitSize=explicitArraySize,
                sizeComment=True,
                storeAsHex=useHexValues,
            )
        )
        cData.write("\n\n")

        cData.write(
            arrayToC(
                self.valuesReference,
                "static const s16",
                valueTable,
                explicitSize=explicitArraySize,
                sizeComment=True,
                storeAsHex=useHexValues,
            )
        )

        return cData.getvalue()

    # Importing
    def toAction(self, action):
        actionProps = action.fast64.sm64

        if self.actionName:
            action.name = self.actionName
        else:
            if self.headers[0].name:
                action.name = toAlnum(self.headers[0].name)
            else:
                action.name = hex(self.headers[0].address)
        self.actionName = action.name

        if self.fileName:
            actionProps.customFileName = self.fileName
            actionProps.overrideFileName = True

        actionProps.indicesTable, actionProps.indicesAddress = self.indicesReference, self.indicesReference
        actionProps.valuesTable, actionProps.valueAddress = self.valuesReference, self.valuesReference

        self.referenceTables = self.reference

        actionProps.customMaxFrame = max([1] + [len(x.values) for x in self.pairs])

        for header in self.headers:
            actionProps.headerVariants.add()
            headerProps = actionProps.headerVariants[-1]
            header.toHeaderProps(action, headerProps)

        updateHeaderVariantNumbers(actionProps.headerVariants)

    def readBinary(self, romfile: BinaryIO, header: SM64_AnimHeader):
        self.indicesReference = hex(header.indices)
        self.valuesReference = hex(header.values)

        indicesReader = RomReading(romfile, header.indices)
        for i in range((header.boneCount + 1) * 3):
            pair = SM64_AnimPair(True)
            pair.readBinary(indicesReader, romfile, header.values)
            self.pairs.append(pair)

    def readC(self, header: SM64_AnimHeader, arrays: dict[ReadArray]):
        self.indicesReference = header.indices
        self.valuesReference = header.values

        if self.indicesReference in arrays and self.valuesReference in arrays:
            indicesArray: ReadArray = arrays[self.indicesReference]
            valuesArray: ReadArray = arrays[self.valuesReference]
            self.fileName = os.path.basename(indicesArray.originPath)
        else:
            # self.fileName = os.path.basename(header.originPath)
            self.reference = True
            return

        indices = indicesArray.values
        values = valuesArray.values
        for i in range(0, len(indices), 2):
            maxFrame, offset = indices[i], indices[i + 1]
            pair = SM64_AnimPair(True)
            pair.readC(maxFrame, offset, values)
            self.pairs.append(pair)
