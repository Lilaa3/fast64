import dataclasses
import os
import shutil
from typing import BinaryIO

from bpy.types import UILayout
from bpy.path import abspath

from ..utility import PluginError, filepath_checks, multilineLabel, intToHex, tempName, decodeSegmentedAddr


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


def import_rom_checks(rom: os.PathLike):
    filepath_checks(
        rom,
        empty_error="Import ROM path is empty.",
        doesnt_exist_error="Import ROM path does not exist.",
        not_a_file_error="Import ROM path is not a file.",
    )
    check_expanded(rom)


def export_rom_checks(rom: os.PathLike):
    filepath_checks(
        rom,
        empty_error="Export ROM path is empty.",
        doesnt_exist_error="Export ROM path does not exist.",
        not_a_file_error="Export ROM path is not a file.",
    )
    check_expanded(rom)


def import_rom_ui_warnings(layout: UILayout, rom: os.PathLike) -> bool:
    try:
        import_rom_checks(abspath(rom))
        return True
    except Exception as exc:
        multilineLabel(layout.box(), str(exc), "ERROR")
        return False


def export_rom_ui_warnings(layout: UILayout, rom: os.PathLike) -> bool:
    try:
        export_rom_checks(abspath(rom))
        return True
    except Exception as exc:
        multilineLabel(layout.box(), str(exc), "ERROR")
        return False


def check_expanded(rom: os.PathLike):
    size = os.path.getsize(rom)
    if size < 9000000:  # check if 8MB
        raise PluginError(
            f"ROM at {rom} is too small.\nYou may be using an unexpanded ROM.\nYou can expand a ROM by opening it in SM64 Editor or ROM Manager."
        )


def upgrade_hex_prop(prop_location, old_prop_location, prop_name: str, hex_prop_name: str):
    value = old_prop_location.get(hex_prop_name, None)
    if value is not None:
        prop_location.set(prop_name, intToHex(int(value, 16)))


@dataclasses.dataclass
class RomReading:
    """
    Simple class that simplifies reading data continously from a starting address.
    Accounts for insertable binary data.
    """

    def __init__(
        self,
        data: bytes,
        start_address: int = 0,
        insertable_ptrs: list[int] | None = None,
        rom_data: bytes | None = None,
        segment_data: dict[int, tuple[int, int]] | None = None,
    ):
        self.start_address = start_address
        self.address = start_address
        self.data = data
        self.rom_data = rom_data
        if not insertable_ptrs:
            insertable_ptrs = []
        self.insertable_ptrs = insertable_ptrs
        self.segment_data = segment_data

    def branch(self, start_address: int | None = None, data: bytes | None = None):
        if start_address and start_address > len(self.data):
            if self.rom_data and self.insertable_ptrs:
                data = self.rom_data
            else:
                return None
        branch = RomReading(
            data if data else self.data,
            start_address if start_address is not None else self.address,
            self.insertable_ptrs,
            self.rom_data,
            self.segment_data,
        )
        return branch

    def read_ptr(self):
        ptr_address = self.address
        self.address += 4
        in_bytes = self.data[ptr_address : ptr_address + 4]
        ptr = int.from_bytes(in_bytes, "big", signed=False)
        if ptr == 0:
            return None
        if ptr_address not in self.insertable_ptrs and self.segment_data:
            ptr_in_bytes: bytes = ptr.to_bytes(4, "big")
            if ptr_in_bytes[0] not in self.segment_data:
                raise PluginError(f"Address {intToHex(ptr)} does not belong to the current segment.")
            return decodeSegmentedAddr(ptr_in_bytes, self.segment_data)
        return ptr

    def read_value(self, size, offset: int = None, signed=True):
        if offset:
            self.address = self.start_address + offset
        in_bytes = self.data[self.address : self.address + size]
        self.address += size
        return int.from_bytes(in_bytes, "big", signed=signed)


class SM64_BinaryExporter:
    def __init__(
        self,
        export_rom: os.PathLike,
        output_rom: os.PathLike,
        extended_check: bool = False,
    ):
        self.export_rom = export_rom
        self.output_rom = output_rom
        self.temp_rom: os.PathLike = tempName(self.output_rom)
        self.rom_file_output: BinaryIO = None
        self.extended_check = extended_check

    def __enter__(self):
        export_rom_checks(self.export_rom)
        shutil.copy(self.export_rom, self.temp_rom)
        self.rom_file_output = open(self.temp_rom, "rb+")
        return self

    def write_to_range(self, start_address: int, end_address: int, data: bytes):
        assert (
            start_address + len(data) <= end_address
        ), f"Data does not fit in the bounds ({intToHex(start_address)}, {intToHex(end_address)})"
        self.write(data, start_address)

    def seek(self, offset: int, whence: int = 0):
        self.rom_file_output.seek(offset, whence)

    def read(self, n=-1, offset=-1):
        if offset != -1:
            self.seek(offset)
        return self.rom_file_output.read(n)

    def write(self, s: bytes, offset=-1):
        if offset != -1:
            self.seek(offset)
        return self.rom_file_output.write(s)

    def __exit__(self, exc_type, exc_value, traceback):
        self.rom_file_output.close()
        if exc_value:
            if os.path.exists(self.temp_rom):
                os.remove(self.temp_rom)
            print("\nExecution type:", exc_type)
            print("\nExecution value:", exc_value)
            print("\nTraceback:", traceback)
        else:
            if os.path.exists(self.output_rom):
                os.remove(self.output_rom)
            os.rename(self.temp_rom, self.output_rom)
