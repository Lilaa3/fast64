import dataclasses
from io import BufferedReader, StringIO
import os
import shutil
from typing import BinaryIO

from ..utility import intToHex, tempName, decodeSegmentedAddr
from .sm64_constants import insertableBinaryTypes
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
        type_num = reader.read_value(4)
        if type_num not in insertableBinaryTypes.values():
            raise ValueError(f"Unknown data type: {intToHex(type_num)}")
        self.data_type = next(k for k, v in insertableBinaryTypes.items() if v == type_num)
        if expected_type and self.data_type not in expected_type:
            raise ValueError(f"Unexpected data type: {self.data_type}")

        data_size = reader.read_value(4)
        self.start_address = reader.read_value(4)
        pointer_count = reader.read_value(4)
        self.ptrs = []
        for _ in range(pointer_count):
            self.ptrs.append(reader.read_value(4))

        actual_start = reader.address + self.start_address
        self.data = reader.read_data(data_size, actual_start)
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
    segment_data: dict[int, tuple[int, int]] = dataclasses.field(default_factory=dict)
    insertable: InsertableBinaryData = None
    address: int = dataclasses.field(init=False)

    def __post_init__(self):
        self.address = self.start_address
        if self.insertable_file and not self.insertable:
            self.insertable = InsertableBinaryData().read(self.insertable_file)
        assert self.insertable or self.rom_file

    def branch(self, start_address=-1):
        start_address = self.address if start_address == -1 else start_address
        if self.read_value(1, specific_address=start_address) is None:
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

    def read_data(self, size=-1, specific_address=-1):
        if specific_address == -1:
            address = self.address
            self.address += size
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
        ptr = self.read_value(4)
        if self.insertable and address in self.insertable.ptrs:
            return ptr
        self.rom_file.seek(address)
        if self.segment_data:
            return decodeSegmentedAddr(ptr.to_bytes(4, "big"), self.segment_data)
        return ptr

    def read_value(self, size=-1, signed=False, specific_address=-1):
        in_bytes = self.read_data(size, specific_address)
        return int.from_bytes(in_bytes, "big", signed=signed)


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
                "Data does not fit in the bounds ",
                f"({intToHex(start_address)} - {intToHex(end_address)}).",
            )
        self.write(data, start_address)

    def seek(self, offset: int, whence: int = 0):
        self.rom_file_output.seek(offset, whence)

    def read(self, n=-1, offset=-1):
        if offset != -1:
            self.seek(offset)
        print(f"Reading {n} bytes from {intToHex(self.tell)} to {intToHex(self.tell + n)}.")
        return self.rom_file_output.read(n)

    def write(self, s: bytes, offset=-1):
        if offset != -1:
            self.seek(offset)
        print(f"Writing from {intToHex(self.tell)} to {intToHex(self.tell + len(s))}.")
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


@dataclasses.dataclass
class DMATableElement:
    offset: int = 0
    size: int = 0
    address: int = 0
    end_address: int = 0


@dataclasses.dataclass
class DMATable:
    address_place_holder: int = 0
    entries: list[DMATableElement] = dataclasses.field(default_factory=list)
    data: bytearray = dataclasses.field(default_factory=bytearray)
    address: int = 0
    end_address: int = 0

    def to_binary(self):
        print(
            f"Generating DMA table with {len(self.entries)} entries",
            f"and {len(self.data)} bytes of data",
        )
        data = bytearray()
        data.extend(len(self.entries).to_bytes(4, "big", signed=False))
        data.extend(self.address_place_holder.to_bytes(4, "big", signed=False))

        entries_offset = 8
        entries_length = len(self.entries) * 8
        entrie_data_offset = entries_offset + entries_length

        for entrie in self.entries:
            offset = entrie_data_offset + entrie.offset
            data.extend(offset.to_bytes(4, "big", signed=False))
            data.extend(entrie.size.to_bytes(4, "big", signed=False))
        data.extend(self.data)

        return data

    def read_binary(self, reader: RomReader):
        print("Reading DMA table at", intToHex(reader.start_address))
        self.address = reader.start_address

        num_entries = reader.read_value(4)  # numEntries
        self.address_place_holder = reader.read_value(4)  # addrPlaceholder

        table_size = 0
        for _ in range(num_entries):
            offset = reader.read_value(4)
            size = reader.read_value(4)
            address = self.address + offset
            self.entries.append(DMATableElement(offset, size, address, address + size))
            end_of_entry = offset + size
            if end_of_entry > table_size:
                table_size = end_of_entry
        self.end_address = self.address + table_size
        print(f"Found {len(self.entries)} DMA entries")
        return self


@dataclasses.dataclass
class IntArray:
    name: str = ""
    signed: bool = False
    byte_count: int = 2
    wrap: int = 6
    wrap_start: int = 0  # -6 To replicate decomp animation index table formatting
    data: list[int] = dataclasses.field(default_factory=list)

    def to_binary(self):
        assert self.byte_count in (1, 2, 4, 8)
        print(f"Generating {self.byte_count} byte array with {len(self.data)} elements")
        data = bytearray(0)
        for short in self.data:
            data += short.to_bytes(self.byte_count, "big", signed=self.signed)
        return data

    def to_c(self):
        assert self.name, "Array must have a name"
        assert self.byte_count in (1, 2, 4, 8)
        data_type = f"{'s' if self.signed else 'u'}{self.byte_count * 8}"
        print(f'Generating {data_type} array "{self.name}" with {len(self.data)} elements')

        data = StringIO()
        data.write(f"// {len(self.data)}\n")
        data.write(f"static const {data_type} {self.name}[] = {{\n\t")
        wrap = self.wrap
        i = self.wrap_start
        for short in self.data:
            data.write(f"{intToHex(short, self.byte_count, False)}, ")
            i += 1
            if i >= wrap:
                data.write("\n\t")
                i = 0
        data.write("\n};\n")
        return data.getvalue()
