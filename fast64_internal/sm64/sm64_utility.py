import os
import shutil
from typing import BinaryIO

from ..utility import PluginError, filepath_checks, intToHex, tempName


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


def import_rom_checks(filepath: str, extended_check: bool = True):
    filepath_checks(
        filepath,
        empty_error=f"Import ROM path is empty.",
        doesnt_exist_error=f"Import ROM path does not exist.",
        not_a_file_error=f"Import ROM path is not a file.",
    )
    if extended_check:
        check_expanded(filepath)


def export_rom_checks(filepath: str, extended_check: bool = True):
    filepath_checks(
        filepath,
        empty_error=f"Export ROM path is empty.",
        doesnt_exist_error=f"Export ROM path does not exist.",
        not_a_file_error=f"Export ROM path is not a file.",
    )
    if extended_check:
        check_expanded(filepath)


def check_expanded(filepath: str):
    filepath_checks(
        filepath,
        empty_error=f"ROM path is empty.",
        doesnt_exist_error=f"ROM path does not exist.",
        not_a_file_error=f"ROM path is not a file.",
    )

    size = os.path.getsize(filepath)
    if size < 9000000:  # check if 8MB
        raise PluginError(
            f"ROM at {filepath} is too small.\nYou may be using an unexpanded ROM.\nYou can expand a ROM by opening it in SM64 Editor or ROM Manager."
        )


def upgrade_hex_prop(prop_location, old_prop_location, prop_name: str, hex_prop_name: str):
    value = old_prop_location.get(hex_prop_name, None)
    if value is not None:
        prop_location.set(prop_name, intToHex(int(value, 16)))


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
        export_rom_checks(self.export_rom, self.extended_check)
        shutil.copy(self.export_rom, self.temp_rom)
        self.rom_file_output = open(self.temp_rom, "rb+")
        return self

    def write_to_range(self, start_address: int, end_address: int, data: bytes):
        assert (
            start_address + len(data) <= end_address
        ), f"Data does not fit in the bounds ({intToHex(start_address)}, {intToHex(end_address)})"
        self.rom_file_output.seek(start_address)
        self.rom_file_output.write(data)

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
