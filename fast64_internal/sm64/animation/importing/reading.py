import dataclasses
import os
from typing import BinaryIO
import bpy

from ..classes import SM64_AnimHeader, SM64_Anim
from ..utility import CArrayReader, ReadArray
from ....utility import PluginError, RomReading, decodeSegmentedAddr


def importBinaryHeader(
    ROMData: BinaryIO,
    headerAddress: int,
    isDMA: bool,
    segmentData: dict[int, tuple[int, int]],
    dataDict: dict[str, SM64_Anim],
):
    header = SM64_AnimHeader()
    header.readBinary(ROMData, headerAddress, segmentData, isDMA)

    dataKey: str = f"{header.indices}-{header.values}"
    if dataKey in dataDict:
        data = dataDict[dataKey]
    else:
        data = SM64_Anim()
        data.readBinary(ROMData, header)
        dataDict[dataKey] = data

    header.headerVariant = len(data.headers)
    header.data = data
    data.headers.append(header)
    return header


@dataclasses.dataclass
class DMATableEntrie:
    offsetFromTable: int
    address: int
    size: int


def readBinaryDMATableEntries(ROMData: BinaryIO, address: int) -> list[DMATableEntrie]:
    entries: list[DMATableEntrie] = []
    DMATableReader = RomReading(ROMData, address)

    numEntries = DMATableReader.readValue(4)
    addrPlaceholder = DMATableReader.readValue(4)

    for i in range(numEntries):
        offset = DMATableReader.readValue(4)
        size = DMATableReader.readValue(4)
        entries.append(DMATableEntrie(offset, address + offset, size))
    return entries


def importBinaryDMAAnimation(
    ROMData: BinaryIO,
    address: int,
    entrieNum: int,
    readEntireTable: bool,
    dataDict: dict[str, SM64_Anim],
    tableList: list[SM64_Anim],
):
    entries: list[DMATableEntrie] = readBinaryDMATableEntries(ROMData, address)
    if readEntireTable:
        for entrie in entries:
            header = importBinaryHeader(ROMData, entrie.address, True, None, dataDict)
            tableList.append(header)
    else:
        if not (0 <= entrieNum < len(entries)):
            raise PluginError("Entrie outside of defined table.")     

        entrie: DMATableEntrie = entries[entrieNum]
        header = importBinaryHeader(ROMData, entrie.address, True, None, dataDict)
        tableList.append(header)
        return header


def importBinaryTable(
    ROMData: BinaryIO,
    address: int,
    readEntireTable: bool,
    tableIndex: int,
    segmentData: dict[int, tuple[int, int]],
    dataDict: dict[str, SM64_Anim],
    tableList: list[SM64_Anim],
):
    for i in range(255):
        ROMData.seek(address + (4 * i))
        ptr = int.from_bytes(ROMData.read(4), "big", signed=False)
        if ptr == 0:
            if not readEntireTable:
                raise PluginError("Table Index not in table.")
            break

        isCorrectIndex = not readEntireTable and i == tableIndex
        if readEntireTable or isCorrectIndex:
            ptrInBytes: bytes = ptr.to_bytes(4, "big")
            if ptrInBytes[0] not in segmentData:
                raise PluginError(
                    f"\
Header at table index {i} located at {ptr} does not belong to the current segment."
                )
            headerAddress = decodeSegmentedAddr(ptrInBytes, segmentData)

            header = importBinaryHeader(ROMData, headerAddress, False, segmentData, dataDict)
            tableList.append(header)

            if isCorrectIndex:
                break
    else:
        raise PluginError(
            "\
Table address is invalid, iterated through 255 indices and no NULL was found."
        )


def importAnimation(dataDict, array: ReadArray, arrays: list[ReadArray]):
    print(f"Reading animation {array.name}")
    header = SM64_AnimHeader()
    header.readC(array)
    print(header)

    dataKey: str = f"{header.indices}-{header.values}"
    if dataKey in dataDict:
        data: SM64_Anim = dataDict[dataKey]
    else:
        data = SM64_Anim()
        data.readC(header, arrays)
        dataDict[dataKey] = data
    
    header.headerVariant = len(data.headers)
    header.data = data
    data.headers.append(header)

    return header


def importCAnimations(
    path: str,
    dataDict: dict[str, SM64_Anim],
    tableList: list[SM64_Anim],
):
    if not os.path.exists(path):
        raise PluginError(f"Path ({path}) does not exist.")

    if os.path.isfile(path):
        filePaths: list[str] = [path]
    elif os.path.isdir(path):
        fileNames = os.listdir(path)
        filePaths: list[str] = [os.path.join(path, fileName) for fileName in fileNames]
    else:
        raise PluginError(f"Path ({path}) is not a file or a directory.")

    filePaths.sort()

    print("Reading arrays in path")

    arrays: dict[ReadArray] = {}
    for filePath in filePaths:
        if not filePath.endswith(".c"):
            continue

        print(f"Reading file {filePath}")
        with open(filePath, "r") as file:
            arrayReader = CArrayReader()
            arrays.update(arrayReader.findAllCArraysInFile(file.read(), filePath))

    header = None
    for array in arrays.values():
        if "*const" in array.keywords or "Animation*" in array.keywords:  # Table
            continue
        elif not "Animation" in array.keywords:
            continue
        header = importAnimation(dataDict, array, arrays)
        tableList.append(header)

    return header
