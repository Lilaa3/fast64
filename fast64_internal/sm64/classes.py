import dataclasses
from io import BufferedReader, StringIO
import os
import shutil
from typing import BinaryIO

from ..utility import intToHex, tempName, decodeSegmentedAddr
from .sm64_utility import export_rom_checks


@dataclasses.dataclass
class RomReader:
    """
    Simple class that simplifies reading data continously from a starting address.
    Accounts for insertable binary data.
    When reading insertable binary data, can also read data from ROM if available.
    """

    data: bytes | BufferedReader = None
    start_address: int = 0
    insertable: bool = False
    insertable_ptrs: list[int] = dataclasses.field(default_factory=list)
    rom_data: bytes | BufferedReader = None
    segment_data: dict[int, tuple[int, int]] = dataclasses.field(default_factory=dict)
    address: int = dataclasses.field(init=False)

    def __post_init__(self):
        self.address = self.start_address

    def branch(self, start_address=0, data: bytes | BufferedReader | None = None):
        if self.read_value(1, specific_address=start_address) is None:
            if self.insertable and self.rom_data:
                return RomReader(self.rom_data, start_address, segment_data=self.segment_data)
            return None
        branch = RomReader(
            data if data else self.data,
            start_address,
            self.insertable,
            self.insertable_ptrs,
            self.rom_data,
            self.segment_data,
        )
        return branch

    def read_ptr(self):
        address = self.address
        ptr = self.read_value(4)
        if address not in self.insertable_ptrs and self.segment_data:
            return decodeSegmentedAddr(ptr.to_bytes(4, "big"), self.segment_data)
        return ptr

    def read_value(self, size, signed=False, specific_address: int | None = None):
        if specific_address is None:
            address = self.address
            self.address += size
        else:
            address = specific_address

        if isinstance(self.data, BufferedReader):
            self.data.seek(address)
            in_bytes = self.data.read(size)
        else:
            if address + size > len(self.data):
                in_bytes = None
            else:
                in_bytes = self.data[address : address + size]
        return None if in_bytes is None else int.from_bytes(in_bytes, "big", signed=signed)


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
        print(f"Found {len(self.entries)} entries")
        return self


@dataclasses.dataclass
class ShortArray:
    name: str = ""
    signed: bool = False
    data: list[int] = dataclasses.field(default_factory=list)

    def to_binary(self):
        data = bytearray(0)
        for short in self.data:
            data += short.to_bytes(2, "big", signed=True)
        return data

    def to_c(self):
        data = StringIO()
        data.write(f"// {len(self.data)}\n")
        data.write(f"static const {'s' if self.signed else 'u'}16 {self.name}[] = {{\n\t")

        wrap = 9 if self.signed else 6
        i = 0 if self.signed else -12 + 6
        for short in self.data:
            data.write(f"{format(short if short >= 0 else 65536 + short, '#06x')}, ")
            i += 1
            if i == wrap:
                data.write("\n\t")
                i = 0
        data.write("\n};\n")
        return data.getvalue()
