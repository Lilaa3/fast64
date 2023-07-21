from enum import Enum
import os
import bpy

from .decompress import sm64_decompress_mio0
from .get_rom_info import SM64_ROMType, getSM64ROMType, getSM64ROMVersion

from ....utility import isPowerOf2, kbToBytes, mbToBytes, PluginError


def unexpandedROMPathChecks(unExpandedROMPath):
    if not os.path.exists(unExpandedROMPath):
        raise Exception("Unexpanded ROM path does not exist.")
    elif not os.path.isfile(unExpandedROMPath):
        raise Exception("Unexpanded ROM path is not file.")


def getROMFilePath(expansionProps) -> str:
    unExpandedROMPath = expansionProps.unExpandedROMPath
    unexpandedROMPathChecks(unExpandedROMPath)

    if expansionProps.overrideOutputPath:
        path = f"{expansionProps.customOutputDir}/{expansionProps.customOutputName}"
        if not os.path.exists(expansionProps.customOutputDir):
            raise Exception("Custom output directory does not exist.")
        if expansionProps.customOutputName == "":
            raise Exception("Empty name.")
        return path

    path = os.path.dirname(unExpandedROMPath)
    name, extension = os.path.splitext(os.path.basename(unExpandedROMPath))
    return f"{path}\{name}.out{extension}"


def swapBytes(data: bytes):
    for i in range(0, len(data), 2):
        data[i], data[i + 1] = data[i + 1], data[i]  # swap the bytes at index i and i+1


def reverseEndian(data: bytes):
    for i in range(0, len(data), 4):
        data[i], data[i + 3] = data[i + 3], data[i]  # swap the bytes at index i and i+3
        data[i + 1], data[i + 2] = data[i + 2], data[i + 1]  # swap the bytes at index i+1 and i+2


def expandRom(context: bpy.types.Context):
    expansionProps = context.scene.fast64.sm64.rom_expansion

    fileName: str = getROMFilePath(expansionProps)

    if not isPowerOf2(expansionProps.MIO0Alignment):
        raise PluginError("Error: Alignment must be power of 2")

    # Convert sizes to bytes
    extendedSize: int = mbToBytes(expansionProps.extendedSize)
    MIO0Padding: int = kbToBytes(expansionProps.MIO0Padding)

    if expansionProps.dumpMIO0Blocks:
        os.makedirs(os.path.dirname(getROMFilePath(expansionProps)))

    unExpandedROMPath: str = expansionProps.unExpandedROMPath
    unexpandedROMPathChecks(unExpandedROMPath)

    with open(unExpandedROMPath, "rb") as rom:
        inputROMData: bytearray = bytearray(rom.read())

    ROMLength: int = len(inputROMData)

    # Confirm valid SM64
    romType: SM64_ROMType = getSM64ROMType(inputROMData, ROMLength)

    if romType == SM64_ROMType.BYTE_SWAPPED:
        print("Converting ROM from byte-swapped to big-endian.")
        swapBytes(inputROMData)
    elif romType == SM64_ROMType.LITTLE_ENDIAN:
        print("Converting ROM from little to big-endian.")
        reverseEndian(inputROMData)
    elif romType == SM64_ROMType.EXTENDED_BIG_ENDIAN:
        raise PluginError("This ROM is already extended!")

    version = getSM64ROMVersion(inputROMData)
    
    outROMData = bytearray(extendedSize)
    outROMData[:] = b'\x01'
    outROMData[:len(inputROMData)] = inputROMData[:len(inputROMData)]
    sm64_decompress_mio0(expansionProps, inputROMData, outROMData)

#
# // fill new space with 0x01
# memset(&out_buf[in_size], 0x01, config.ext_size - in_size);
#
# // decode SM64 MIO0 files and adjust pointers
# sm64_decompress_mio0(&config, in_buf, in_size, out_buf);
#
# // update N64 header CRC
# sm64_update_checksums(out_buf);
#
# // write to output file
# bytes_written = write_file(config.ext_filename, out_buf, config.ext_size);
# if (bytes_written < (long)config.ext_size) {
#    ERROR("Error writing bytes to output file \"%s\"\n", config.ext_filename);
#    exit(EXIT_FAILURE);
# }
#
# return EXIT_SUCCESS;
