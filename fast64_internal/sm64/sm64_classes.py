import dataclasses
from io import BufferedReader, StringIO
import os
import shutil
import struct
from typing import BinaryIO

from ..utility import intToHex, tempName, decodeSegmentedAddr
from .sm64_constants import insertableBinaryTypes, SegmentData
from .sm64_utility import export_rom_checks


@dataclasses.dataclass
class InsertableBinaryData:
    data_type: str = ""
    data: bytearray = dataclasses.field(default_factory=bytearray)
    start_address: int = 0
    ptrs: list[int] = dataclasses.field(default_factory=list)

    def write(self, path: os.PathLike):
        with open(path, "wb") as file:
            file.write(self.to_binary())

    def to_binary(self):
        data = bytearray()
        # 0-4
        data.extend(insertableBinaryTypes[self.data_type].to_bytes(4, "big"))
        # 4-8
        data.extend(len(self.data).to_bytes(4, "big"))
        # 8-12
        data.extend(self.start_address.to_bytes(4, "big"))
        # 12-16
        data.extend(len(self.ptrs).to_bytes(4, "big"))
        # 16-?
        for ptr in self.ptrs:
            data.extend(ptr.to_bytes(4, "big"))
        data.extend(self.data)
        return data

    def read(self, file: BufferedReader, expected_type: list = None):
        print(f"Reading insertable binary data from {file.name}")
        reader = RomReader(file)
        type_num = reader.read_int(4)
        if type_num not in insertableBinaryTypes.values():
            raise ValueError(f"Unknown data type: {intToHex(type_num)}")
        self.data_type = next(k for k, v in insertableBinaryTypes.items() if v == type_num)
        if expected_type and self.data_type not in expected_type:
            raise ValueError(f"Unexpected data type: {self.data_type}")

        data_size = reader.read_int(4)
        self.start_address = reader.read_int(4)
        pointer_count = reader.read_int(4)
        self.ptrs = []
        for _ in range(pointer_count):
            self.ptrs.append(reader.read_int(4))

        actual_start = reader.address + self.start_address
        self.data = reader.read_int(data_size, actual_start)
        return self


@dataclasses.dataclass
class RomReader:
    """
    Helper class that simplifies reading data continously from a starting address.
    Can read insertable binary files, in which it can also read data from ROM if provided.
    """

    rom_file: BufferedReader = None
    insertable_file: BufferedReader = None
    start_address: int = 0
    segment_data: SegmentData = dataclasses.field(default_factory=dict)
    insertable: InsertableBinaryData = None
    address: int = dataclasses.field(init=False)

    def __post_init__(self):
        self.address = self.start_address
        if self.insertable_file and not self.insertable:
            self.insertable = InsertableBinaryData().read(self.insertable_file)
        assert self.insertable or self.rom_file

    def branch(self, start_address=-1):
        start_address = self.address if start_address == -1 else start_address
        if self.read_int(1, specific_address=start_address) is None:
            if self.insertable and self.rom_file:
                return RomReader(self.rom_file, start_address=start_address, segment_data=self.segment_data)
            return None
        return RomReader(
            self.rom_file,
            self.insertable_file,
            start_address,
            self.segment_data,
            self.insertable,
        )

    def skip(self, size: int):
        self.address += size

    def read_data(self, size=-1, specific_address=-1):
        if specific_address == -1:
            address = self.address
            self.skip(size)
        else:
            address = specific_address

        if self.insertable:
            data = self.insertable.data[address : address + size]
        else:
            self.rom_file.seek(address)
            data = self.rom_file.read(size)
        if not data:
            raise IndexError(f"Value at {intToHex(address)} not present in data.")
        return data

    def read_ptr(self):
        address = self.address
        ptr = self.read_int(4)
        if self.insertable and address in self.insertable.ptrs:
            return ptr
        if ptr and self.segment_data:
            return decodeSegmentedAddr(ptr.to_bytes(4, "big"), self.segment_data)
        return ptr

    def read_int(self, size=4, signed=False, specific_address=-1):
        in_bytes = self.read_data(size, specific_address)
        return int.from_bytes(in_bytes, "big", signed=signed)

    def read_float(self, size=4, specific_address=-1):
        in_bytes = self.read_data(size, specific_address)
        return struct.unpack(">f", in_bytes)[0]

    def read_str(self, specific_address=-1):
        ptr = self.read_ptr() if specific_address == -1 else specific_address
        if not ptr:
            return None
        branch = self.branch(ptr)
        text_data = bytearray()
        while True:
            byte = branch.read_data(1)
            if byte == b"\x00" or not byte:
                break
            text_data.append(ord(byte))
        text = text_data.decode("utf-8")
        return text


@dataclasses.dataclass
class BinaryExporter:
    export_rom: os.PathLike
    output_rom: os.PathLike
    rom_file_output: BinaryIO = dataclasses.field(init=False)
    temp_rom: os.PathLike = dataclasses.field(init=False)

    @property
    def tell(self):
        return self.rom_file_output.tell()

    def __enter__(self):
        print("Binary export started, exporting to", self.output_rom)
        export_rom_checks(self.export_rom)
        self.temp_rom: os.PathLike = tempName(self.output_rom)
        print(f'Copying "{self.export_rom}" to temporary file "{self.temp_rom}".')
        shutil.copy(self.export_rom, self.temp_rom)
        self.rom_file_output = open(self.temp_rom, "rb+")
        return self

    def write_to_range(self, start_address: int, end_address: int, data: bytes):
        if start_address + len(data) > end_address:
            raise IndexError(
                f"Data does not fit in the bounds ({intToHex(start_address)} - {intToHex(end_address)}).",
            )
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
        print("Closing temporary file.")
        if exc_value:
            print("Deleting temporary file because of exception.")
            if os.path.exists(self.temp_rom):
                os.remove(self.temp_rom)
            print("Type:", exc_type, "\nValue:", exc_value, "\nTraceback:", traceback)
        else:
            if not os.path.exists(self.temp_rom):
                raise FileNotFoundError(f"Temporary file {self.temp_rom} does not exist?")
            print(f"Moving temporary file to {self.output_rom}.")
            if os.path.exists(self.output_rom):
                os.remove(self.output_rom)
            os.rename(self.temp_rom, self.output_rom)
