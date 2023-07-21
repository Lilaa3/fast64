from enum import Enum
from ....utility import kbToBytes, mbToBytes, PluginError


class SM64_ROMType(Enum):
    INVALID = (0,)
    BYTE_SWAPPED = (1,)  # SM64 byte-swapped (BADC)
    BIG_ENDIAN = (2,)  # SM64 big-endian (ABCD)
    LITTLE_ENDIAN = (3,)  # SM64 little-endian
    EXTENDED_BIG_ENDIAN = 4  # SM64 big-endian, extended


def memcmp(a, b, n):
    # Compare the first n bytes of a and b
    # Return True if they are equal, False otherwise
    return a[:n] == b[:n]


def getSM64ROMType(inputROMData: bytes, ROMLength: int) -> SM64_ROMType:
    bs = bytes([0x37, 0x80, 0x40, 0x12])
    be = bytes([0x80, 0x37, 0x12, 0x40])
    le = bytes([0x40, 0x12, 0x37, 0x80])

    # Check the conditions and return the corresponding rom type
    if memcmp(inputROMData, bs, len(bs)) and ROMLength == mbToBytes(8):
        return SM64_ROMType.BYTE_SWAPPED
    if memcmp(inputROMData, le, len(le)) and ROMLength == mbToBytes(8):
        return SM64_ROMType.LITTLE_ENDIAN
    if memcmp(inputROMData, be, len(be)):
        if ROMLength > mbToBytes(8):
            return SM64_ROMType.EXTENDED_BIG_ENDIAN
        if ROMLength > mbToBytes(7):
            return SM64_ROMType.BIG_ENDIAN

    raise PluginError("This does not appear to be a valid SM64 ROM.")

class SM64_ROMVersion(Enum):
    UNKNOWN = 0
    USA = 1
    EUROPEAN = 2
    JAPAN = 3
    SHINDOU = 4
    IQUE = 5


versionTable = {
    SM64_ROMVersion.USA: bytes([0x63, 0x5A, 0x2B, 0xFF]),
    SM64_ROMVersion.EUROPEAN: bytes([0xA0, 0x3C, 0xF0, 0x36]),
    SM64_ROMVersion.JAPAN: bytes([0x4E, 0xAA, 0x3D, 0x0E]),
    SM64_ROMVersion.SHINDOU: bytes([0xD6, 0xFB, 0xA4, 0xA8]),
    SM64_ROMVersion.IQUE: bytes([0x00, 0x00, 0x00, 0x00]),
}


def getSM64ROMVersion(inputROMData: bytes):
    for version, cksum1 in versionTable.items():
        # compare checksums
        if cksum1 == inputROMData[0x10:0x14]:
            return version

    raise PluginError("Unknown SM64 ROM version")
