import dataclasses
import os
import shutil
from typing import BinaryIO

from ..utility import PluginError, intToHex, tempName, decodeSegmentedAddr


@dataclasses.dataclass
class RomReader:
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
        branch = RomReader(
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


class BinaryExporter:
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
    table_size: int = 0
    end_address: int = 0

    def to_binary(self):
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

    def read_binary(self, dma_table_reader: RomReader):
        self.address = dma_table_reader.start_address

        num_entries = dma_table_reader.read_value(4, signed=False)  # numEntries
        self.address_place_holder = dma_table_reader.read_value(4, signed=False)  # addrPlaceholder

        self.table_size = 0
        for _ in range(num_entries):
            offset = dma_table_reader.read_value(4, signed=False)
            size = dma_table_reader.read_value(4, signed=False)
            address = self.address + offset
            self.entries.append(DMATableElement(offset, size, address, address + size))
            end_of_entry = offset + size
            if end_of_entry > self.table_size:
                self.table_size = end_of_entry
        self.end_address = self.address + self.table_size
        return self
