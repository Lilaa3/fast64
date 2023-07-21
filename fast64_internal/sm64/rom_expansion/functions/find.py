from dataclasses import dataclass
from ....utility import PluginError

inStartAddress  = 0x000D0000
maxPointers = 128

# MIPS instruction decoding
def OPCODE(x: int):
    return x & 0xFC


def RS(x: bytearray):
    return ((x[0] & 0x3) << 3) | ((x[1] & 0xE0) >> 5)


def RT(x):
    return x & 0x1F


def readU16BigEndian(u16: bytearray):
    return int.from_bytes(u16, byteorder="big", signed=False)


def readU32BigEndian(u32: bytearray):
    return int.from_bytes(u32, byteorder="big", signed=False)


@dataclass
class Mio0Ptr:
    old: int = 0  # MIO0 address in original ROM
    oldEnd: int = 0  # ending MIO0 address in original ROM
    new: int = 0  # starting MIO0 address in extended ROM
    newEnd: int = 0  # ending MIO0 address in extended ROM
    addr: int = 0  # ASM address for referenced pointer
    a1Addiu: int = 0  # ASM offset for ADDIU for A1
    command: int = 0  # command type: 0x1A or 0x18 (or 0xFF for ASM)


def findMIO0PtrInTable(ptr: int, table: list[Mio0Ptr]) -> Mio0Ptr:
    for mio0Ptr in table:
        if ptr == mio0Ptr.old:
            return mio0Ptr


def findPointers(inputROMData: bytearray, table: list[Mio0Ptr]):
    for addr in range(inStartAddress, len(inputROMData), 4):
        if (
            (inputROMData[addr] == 0x18 or inputROMData[addr] == 0x1A)
            and inputROMData[addr + 1] == 0x0C
            and inputROMData[addr + 2] == 0x00
        ):
            ptr: int = readU32BigEndian(inputROMData[addr + 4 : addr + 8])
            mio0Ptr: Mio0Ptr = findMIO0PtrInTable(ptr, table)
            if mio0Ptr is not None:
                mio0Ptr.command = inputROMData[addr]
                mio0Ptr.oldEnd = readU32BigEndian(inputROMData[addr + 8 : addr + 12])


def la2int(inputROMData: bytearray, lui: int, addiu: int):
    addressHigh = readU16BigEndian(inputROMData[lui + 0x2 : lui + 0x4])
    adressLow = readU16BigEndian(inputROMData[addiu + 0x2 : addiu + 0x4])
    if adressLow & 0x8000:
        addressHigh -= 1
    return (addressHigh << 16) | adressLow


def find_asm_pointers(inputROMData: bytearray, mio0Table: list[Mio0Ptr]):
    # looking for some code that follows one of the below patterns:
    # lui a1, start_upper lui a1, start_upper
    # lui a2, end_upper lui a2, end_upper
    # addiu a2, a2, end_lower addiu a2, a2, end_lower
    # addiu a1, a1, start_lower jal function
    # jal function addiu a1, a1, start_lower

    for addr in range(0, inStartAddress, 4):
        opCode0, opCode1, opCode2 = (
            OPCODE(inputROMData[addr]),
            OPCODE(inputROMData[addr + 4]),
            OPCODE(inputROMData[addr + 8]),
        )
        if not(opCode0 == 0x3C and opCode1 == 0x3C and opCode2 == 0x24):
            continue

        opCode3, opCode0x4 = (OPCODE(inputROMData[addr + 0xC]), OPCODE(inputROMData[addr + 0x10]))
        if opCode3 == 0x24:
            a1Addiu = 0xC
        elif opCode0x4 == 0x24:
            a1Addiu = 0x10
        else:
            continue

        rt0, rt1, rt2, rt3 = (
            RT(inputROMData[addr + 1]),
            RT(inputROMData[addr + a1Addiu + 1]),
            RT(inputROMData[addr + 5]),
            RT(inputROMData[addr + 9]),
        )
        if not (rt0 == rt1 and rt2 == rt3):
            continue

        ptr = la2int(inputROMData, addr, addr + a1Addiu)
        end = la2int(inputROMData, addr + 4, addr + 0x8)

        mio0Ptr: Mio0Ptr = findMIO0PtrInTable(ptr, mio0Table)
        if mio0Ptr is not None:
            print(f"Found ASM reference to {ptr} at {addr}")
            mio0Ptr.command = 0xFF
            mio0Ptr.addr = addr
            mio0Ptr.newEnd = end
            mio0Ptr.a1Addiu = a1Addiu


def findMIO0(inputROMData: bytearray) -> list[Mio0Ptr]:
    table = []
    # MIO0 data is on 16-byte boundaries
    for address in range(inStartAddress, len(inputROMData), 16):
        if inputROMData[address : address + 4] != b"MIO0":
            continue
        if len(table) >= maxPointers:
            raise PluginError(f"MIO0 pointer table exceeded the limit of {maxPointers}. This ROM could be invalid.")

        mio0Ptr: Mio0Ptr = Mio0Ptr(old=address)
        table.append(mio0Ptr)
    return table
