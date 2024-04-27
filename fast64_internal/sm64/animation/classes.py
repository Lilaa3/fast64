from collections import OrderedDict
import copy
from io import StringIO
from typing import Optional
import dataclasses
import os

from ...utility import PluginError, is_bit_active
from ..sm64_constants import MAX_U16

from .utility import RomReading
from .c_parser import Initialization
from .constants import HEADER_SIZE, C_FLAGS


@dataclasses.dataclass
class SM64_AnimPair:
    values: list[int] = dataclasses.field(default_factory=list)

    # For compressing
    offset: int = 0

    def clean_frames(self):
        if not self.values:
            self.values = [0]

        last_value = self.values[-1]
        for i, value in enumerate(reversed(self.values)):
            if value != last_value:
                if i > 1:
                    self.values = self.values[: -(i - 1)]
                return
        else:
            self.values = self.values[:1]

    def get_frame(self, frame: int):
        return self.values[min(frame, len(self.values) - 1)]

    def read_binary(self, indices_reader: RomReading, values_reader: RomReading):
        max_frame = indices_reader.read_value(2, signed=False)
        offset = indices_reader.read_value(2, signed=False) * 2
        values_reader = values_reader.branch(values_reader.start_address + offset)
        for _ in range(max_frame):
            self.values.append(values_reader.read_value(2, signed=True))

    def read_c(self, max_frame: int, offset: int, values: list[int]):
        for frame in range(max_frame):
            value = values[offset + frame].value
            value = int.from_bytes(
                value.to_bytes(length=2, byteorder="big", signed=False), signed=True, byteorder="big"
            )
            self.values.append(value)


@dataclasses.dataclass
class SM64_AnimData:
    pairs: list[SM64_AnimPair] = dataclasses.field(default_factory=list)
    indice_reference: str | int = ""
    values_reference: str | int = ""
    indices_file_name: str | int = ""
    values_file_name: str | int = ""

    def to_c(self, is_dma_structure: bool):
        text_data = StringIO()

        value_table, indice_tables = create_tables([self])
        indice_table = indice_tables[0]

        if is_dma_structure:
            text_data.write(indice_table.to_c())
            text_data.write("\n\n")
            text_data.write(value_table.to_c())
        else:
            text_data.write(value_table.to_c())
            text_data.write("\n\n")
            text_data.write(indice_table.to_c())

        return text_data.getvalue()

    def to_binary(self, start_address: int = 0) -> bytearray:
        data: bytearray = bytearray()

        value_table, indice_tables = create_tables([self])
        indice_table = indice_tables[0]

        indices_size = len(indice_table.data) * 2
        values_offset = start_address + indices_size
        values_address = start_address, values_offset

        data.extend(indice_table.to_binary())
        data.extend(value_table.to_binary())

        return data, values_address

    def read_binary(self, indices_reader: RomReading, values_reader: RomReading, bone_count: int):
        self.indice_reference = indices_reader.address
        self.values_reference = values_reader.address
        for _ in range((bone_count + 1) * 3):
            pair = SM64_AnimPair()
            pair.read_binary(indices_reader, values_reader)
            self.pairs.append(pair)

    def read_c(self, indices_array: Initialization, values_array: Initialization):
        self.indices_file_name = os.path.basename(indices_array.origin_path)
        self.values_file_name = os.path.basename(values_array.origin_path)

        self.indice_reference = indices_array.name
        self.values_reference = values_array.name

        indices = indices_array.value.value
        values = values_array.value.value
        for i in range(0, len(indices), 2):
            max_frame, offset = indices[i].value, indices[i + 1].value
            pair = SM64_AnimPair()
            pair.read_c(max_frame, offset, values)
            pair.clean_frames()
            self.pairs.append(pair)


@dataclasses.dataclass
class SM64_AnimHeader:
    reference: str | int = ""

    flags: int | str = 0
    trans_divisor: int = 0
    start_frame: int = 0
    loop_start: int = 0
    loop_end: int = 1
    bone_count: int = 0

    indice_reference: Optional[str | int] = None
    values_reference: Optional[str | int] = None

    enum_reference: str = ""
    file_name: str = ""

    data: Optional[SM64_AnimData] = None

    # Imports
    header_variant: int = 0

    def get_flags_comment(self):
        if isinstance(self.flags, str):
            return self.flags
        flags_list: list[str] = []
        for index, flags in enumerate(C_FLAGS):
            if is_bit_active(self.flags, index):
                flags_list.append("/".join(flags))

        return ", ".join(flags_list)

    def get_int_flags(self):
        assert isinstance(self.flags, int), "Flags must be in an int."
        return self.flags

    def get_c_flags(self):
        if isinstance(self.flags, str):
            return self.flags

        return hex(self.flags)

    def get_values_reference(self, override: Optional[str | int] = None):
        if override:
            return override
        elif self.values_reference:
            return self.values_reference
        elif self.data and self.data.values_reference:
            return self.data.values_reference

    def get_indice_reference(self, override: Optional[str | int] = None):
        if override:
            return override
        elif self.indice_reference:
            return self.indice_reference
        elif self.data and self.data.indice_reference:
            return self.data.indice_reference

    def to_c(
        self,
        values_override: Optional[str | int] = None,
        indice_override: Optional[str | int] = None,
        is_dma_structure: bool = False,
    ):
        return (
            f"static const struct Animation {self.reference}{'[]' if is_dma_structure else ''} = {{\n"
            + (f"\t{hex(self.get_int_flags())}, " if is_dma_structure else f"\t{self.get_c_flags()}, ")
            + f"// flags {self.get_flags_comment()}\n"
            f"\t{self.trans_divisor}, // animYTransDivisor\n"
            f"\t{self.start_frame}, // startFrame\n"
            f"\t{self.loop_start}, // loopStart\n"
            f"\t{self.loop_end}, // loopEnd\n"
            f"\tANIMINDEX_NUMPARTS({self.get_indice_reference(indice_override)}), // unusedBoneCount\n"
            f"\t{self.get_values_reference(values_override)}, // values\n"
            f"\t{self.get_indice_reference(indice_override)}, // index\n"
            "\t0\n // length\n"
            "};\n"
        )

    def to_binary(
        self,
        values_override: Optional[str | int] = None,
        indice_override: Optional[str | int] = None,
    ):
        data = bytearray()
        data.extend(self.get_int_flags().to_bytes(2, byteorder="big", signed=False))  # 0x00
        data.extend(self.trans_divisor.to_bytes(2, byteorder="big", signed=True))  # 0x02
        data.extend(self.start_frame.to_bytes(2, byteorder="big", signed=True))  # 0x04
        data.extend(self.loop_start.to_bytes(2, byteorder="big", signed=True))  # 0x06
        data.extend(self.loop_end.to_bytes(2, byteorder="big", signed=True))  # 0x08
        data.extend(self.bone_count.to_bytes(2, byteorder="big", signed=True))  # 0x0A
        data.extend(self.get_values_reference(values_override).to_bytes(4, byteorder="big", signed=False))  # 0x0C
        data.extend(self.get_indice_reference(indice_override).to_bytes(4, byteorder="big", signed=False))  # 0x10
        data.extend(bytearray([0x00] * 4))  # 0x14 # Unused with no porpuse, however,
        # in the mario dma table it's generated by taking the sum of the offset and size of the values table
        # and subtracting by the offset of the header, the offsets are relative to the table
        # TODO: Implement the described logic for DMA table binary exports
        # 0x18
        return data

    def read_binary(
        self,
        header_reader: RomReading,
        is_dma: bool = False,
        assumed_bone_count: int | None = None,
    ):
        self.reference = header_reader.address
        self.flags = header_reader.read_value(2, signed=False)  # /*0x00*/ s16 flags;
        self.trans_divisor = header_reader.read_value(2)  # /*0x02*/ s16 animYTransDivisor;
        self.start_frame = header_reader.read_value(2)  # /*0x04*/ s16 startFrame;
        self.loop_start = header_reader.read_value(2)  # /*0x06*/ s16 loopStart;
        self.loop_end = header_reader.read_value(2)  # /*0x08*/ s16 loopEnd;
        bone_count = header_reader.read_value(2)  # /*0x0A*/ s16 unusedBoneCount; (Unused in engine)
        self.bone_count = bone_count if assumed_bone_count is None else assumed_bone_count

        # /*0x0C*/ const s16 *values;
        # /*0x10*/ const u16 *index;
        if is_dma:
            start_address = header_reader.start_address
            self.values_reference = start_address + header_reader.read_value(4, signed=False)
            self.indice_reference = start_address + header_reader.read_value(4, signed=False)
        else:
            self.values_reference = header_reader.read_ptr()
            self.indice_reference = header_reader.read_ptr()

    def read_c(self, value: Initialization):
        self.file_name = os.path.basename(value.origin_path)
        self.reference = value.name

        value.set_attributes_from_struct(
            self,
            OrderedDict(
                {
                    "flags": "flags",
                    "animYTransDivisor": "trans_divisor",
                    "startFrame": "start_frame",
                    "loopStart": "loop_start",
                    "loopEnd": "loop_end",
                    "unusedBoneCount": "bone_count",
                    "values": "values_reference",
                    "index": "indice_reference",
                    "length": "length",
                },
            ),
        )


@dataclasses.dataclass
class SM64_Anim:
    data: SM64_AnimData = None
    headers: list[SM64_AnimHeader] = dataclasses.field(default_factory=list)

    # Imports
    action_name: str = ""  # Used in the table class to prop function

    def to_binary(self, is_dma: bool = False, start_address: int = 0) -> bytearray:
        data: bytearray = bytearray()
        ptrs: list[int] = []

        if self.data:
            indice_offset = HEADER_SIZE * len(self.headers)
            indice_reference = start_address + indice_offset
            anim_data, values_reference = self.data.to_binary(indice_reference)

        for header in self.headers:
            ptrs.extend([start_address + len(data) + 12, start_address + len(data) + 16])
            header_data = header.to_binary(
                indice_reference if self.data else None,
                values_reference if self.data else None,
            )
            data.extend(header_data)

        if self.data:
            data.extend(anim_data)

        if is_dma or not self.data:
            return data, []
        else:
            return data, ptrs

    def headers_to_c(self, is_dma_structure: bool) -> str:
        text_data = StringIO()
        for header in self.headers:
            text_data.write(header.to_c(is_dma_structure=is_dma_structure))
            text_data.write("\n")
        return text_data.getvalue()

    def to_c(self, is_dma_structure: bool):
        text_data = StringIO()

        table_data = None
        if self.data:
            table_data = self.data.to_c(is_dma_structure)

        c_headers = self.headers_to_c(is_dma_structure)
        if is_dma_structure:
            text_data.write(c_headers)
        text_data.write(table_data)
        text_data.write("\n")
        if not is_dma_structure:
            text_data.write(c_headers)

        return text_data.getvalue()


@dataclasses.dataclass
class DMATableEntrie:
    offset: int
    size: int
    address: int


@dataclasses.dataclass
class SM64_DMATable:
    address_place_holder: int = 0
    entries: list[DMATableEntrie] = dataclasses.field(default_factory=list)

    def read_binary(self, dma_table_reader: RomReading):
        num_entries = dma_table_reader.read_value(4)  # numEntries
        self.address_place_holder = dma_table_reader.read_value(4)  # addrPlaceholder

        end_of_table = 0
        for _ in range(num_entries):
            offset = dma_table_reader.read_value(4)
            size = dma_table_reader.read_value(4)
            self.entries.append(DMATableEntrie(offset, size, dma_table_reader.start_address + offset))
            end_of_entry = offset + size
            if end_of_entry > end_of_table:
                end_of_table = end_of_entry


def num_to_padded_hex(num: int):
    hex_str = hex(num)[2:].upper()  # remove the '0x' prefix
    return hex_str.zfill(2)


@dataclasses.dataclass
class SM64_AnimTableElement:
    reference: str | int = ""
    enum_name: str | None = None
    header: SM64_AnimHeader | None = None

    @property
    def data(self):
        return self.header.data if self.header else None


@dataclasses.dataclass
class SM64_AnimTable:
    reference: str | int = None
    enum_list_reference: str = ""
    file_name: str = ""
    values_reference: str = ""
    elements: list[SM64_AnimTableElement] = dataclasses.field(default_factory=list)

    @property
    def enum_and_header_names(self) -> list[str, str]:
        names = []
        for element in self.elements:
            assert isinstance(element.reference, str), "Reference is not a string."
            names.append((element.enum_name, element.reference))
        return names

    # TODO: Bring over binary and c import logic for tables here
    def get_sets(self) -> tuple[list[SM64_AnimHeader], list[SM64_AnimData]]:
        # Remove duplicates of data and headers, keep order by using a list
        data_set = []
        headers_set = []
        for element in self.elements:
            if element.data and not element.data in data_set:
                data_set.append(element.data)
            if element.header and not element.header in headers_set:
                headers_set.append(element.header)
        return headers_set, data_set

    def prepare_for_dma(self):
        elements = []
        # For creating duplicates
        data_already_added = []
        headers_already_added = []
        header_nums = []
        included_headers = []
        data = None

        for i, element in enumerate(self.elements):
            assert element.header, f"Header in table element {i} is not set."
            assert element.data, f"Data in table element {i} is not set."
            header_nums.append(i)

            header = element.header
            if header in headers_already_added:
                header = copy.copy(header)
            header.reference = f"anim_{num_to_padded_hex(i)}"
            headers_already_added.append(header)

            included_headers.append(header)
            if header.data:
                data = header.data

            # If not at the end of the list and the next element doesn´t have different data
            if (i < len(self.elements) - 1) and self.elements[i + 1].data is data:
                continue

            name = f'anim_{"_".join([f"{num_to_padded_hex(num)}" for num in header_nums])}'
            file_name = f"{name}.inc.c"
            if data:
                if data in data_already_added:
                    data = copy.copy(data)
                data_already_added.append(data)

                data.indice_reference, data.values_reference, data.file_name = (
                    f"{name}_indices",
                    f"{name}_values",
                    file_name,
                )
            # Normal names are possible (order goes by line and file) but would break convention
            for included_header in included_headers:
                included_header.file_name = file_name
                included_header.indice_reference = f"{name}_indices"
                included_header.values_reference = f"{name}_values"
                included_header.data = data
                elements.append(SM64_AnimTableElement(header=included_header))

            data = None
            header_nums.clear()
            included_headers.clear()

        self.elements = elements

    def to_binary(self, is_dma: bool = False, start_address: int = 0):
        # TODO: Handle dma exports
        data: bytearray = bytearray()
        ptrs: list[int] = []
        headers_set, data_set = self.get_sets()

        headers_offset = start_address + len(self.elements) * 4 + 4  # Table length
        headers_length = len(headers_set) * HEADER_SIZE
        if data_set:
            value_table, indice_tables = create_tables(data_set, "values")
            indice_tables_offset = headers_offset + headers_length
            values_table_offset = indice_tables_offset + sum(
                [len(indice_table.data) * 2 for indice_table in indice_tables]
            )

        for anim_header in self.elements:  # Add the animation table
            ptrs.append(len(data))
            header_offset = headers_offset + (headers_set.index(anim_header) * HEADER_SIZE)
            data.extend(header_offset.to_bytes(4, byteorder="big", signed=False))
        data.extend(bytearray([0x00] * 4))  # NULL delimiter

        for anim_header in self.elements:  # Add the headers
            if not anim_header.data:
                data.extend(anim_header.to_binary())
                continue
            ptrs.extend([start_address + len(data) + 12, start_address + len(data) + 16])
            indice_offset = indice_tables_offset + sum(
                len(indice_table.data) * 2 for indice_table in indice_tables[: data_set.index(anim_header.data)]
            )
            data.extend(
                anim_header.to_binary(
                    values_table_offset,
                    indice_offset,
                )
            )

        if data_set:  # Add the data
            for indice_table in indice_tables:
                data.extend(indice_table.to_binary())
            data.extend(value_table.to_binary())

        return data, ptrs

    def data_and_headers_to_c(self, is_dma: bool) -> list[os.PathLike, str]:
        files_data: dict[str, str] = {}

        headers_set = self.get_sets()[0]
        headers_added = []

        text_data = StringIO()
        for anim_header in headers_set:
            if anim_header in headers_added:
                continue

            same_reference_headers = [anim_header]
            for other_header in headers_set:
                if (
                    not anim_header is other_header
                    and anim_header.indice_reference == other_header.indice_reference
                    and anim_header.values_reference == other_header.values_reference
                ):
                    same_reference_headers.append(other_header)
                    headers_added.append(other_header)

            if is_dma:
                for same_reference_header in same_reference_headers:
                    text_data.write(same_reference_header.to_c(is_dma_structure=is_dma))
                text_data.write("\n")
            for same_reference_header in same_reference_headers:
                if same_reference_header.data:
                    value_table, indice_tables = create_tables([same_reference_header.data])
                    if is_dma:
                        text_data.write(indice_tables[0].to_c())
                        text_data.write("\n")
                    text_data.write(value_table.to_c())
                    text_data.write("\n")
                    if not is_dma:
                        text_data.write(indice_tables[0].to_c())
                        text_data.write("\n")
                    break
            if not is_dma:
                for same_reference_header in same_reference_headers:
                    text_data.write(same_reference_header.to_c(is_dma_structure=is_dma))
                text_data.write("\n")

            files_data[anim_header.file_name] = text_data.getvalue()
            text_data = StringIO()

        return files_data

    def data_and_headers_to_c_combined(self):
        text_data = StringIO()

        headers_set, data_set = self.get_sets()
        if data_set:
            value_table, indice_tables = create_tables(data_set, self.values_reference)
            text_data.write(value_table.to_c())
            text_data.write("\n")
            for indice_table in indice_tables:
                text_data.write(indice_table.to_c())
                text_data.write("\n")

        for anim_header in headers_set:
            text_data.write(anim_header.to_c(values_override=self.values_reference))
            text_data.write("\n")

        return text_data.getvalue()

    def enum_list_to_c(self):
        text_data = StringIO()

        text_data.write(f"enum {self.enum_list_reference} {{\n")
        for anim_header in self.elements:
            text_data.write(f"\t{anim_header.enum_name},\n")
        text_data.write("};\n")

        return text_data.getvalue()

    def table_to_c(self, generate_enums: bool):
        text_data = StringIO()

        if generate_enums:
            text_data.write(f'#include "table_enum.h"\n')

        text_data.write(f"const struct Animation *const {self.reference}[] = {{\n")
        for element in self.elements:
            if generate_enums:
                text_data.write(f"\t[{element.enum_name}] = &{element.reference},\n")
            else:
                text_data.write(f"\t&{element.reference},\n")
        text_data.write("\tNULL,\n};\n")

        return text_data.getvalue()


class SM64_ShortArray:
    def __init__(self, name, signed):
        self.name = name
        self.data = []
        self.signed = signed

    def to_binary(self):
        data = bytearray(0)
        for short in self.data:
            data += short.to_bytes(2, "big", signed=True)
        return data

    def to_c(self):
        data = StringIO()
        data.write(f"static const {'s' if self.signed else 'u'}16 {self.name}[] = {{\n\t")

        wrap_counter = 0
        for short in self.data:
            u_short = int.from_bytes(short.to_bytes(2, "big", signed=True), "big", signed=False)
            data.write(f"0x{format(u_short, '04X')}, ")
            wrap_counter += 1
            if wrap_counter > 8:
                data.write("\n\t")
                wrap_counter = 0
        data.write("\n};\n")
        return data.getvalue()


def create_tables(anims_data: list[SM64_AnimData], values_name: str = None):
    """Can generate multiple indices table with only one value table, which improves compression"""
    """This feature is used in table exports"""

    def index_sub_seq_in_seq(sub_seq: list[int], seq: list[int]):
        i, sub_length = -1, len(sub_seq)
        while True:
            trunc_seq = seq[i + 1 :]
            if sub_seq[0] not in trunc_seq:
                return -1
            i = seq.index(sub_seq[0], i + 1)
            if sub_seq == seq[i:sub_length]:
                return i

    value_table = SM64_ShortArray(values_name if values_name else anims_data[0].values_reference, True)

    all_pairs = [pair for anim_data in anims_data for pair in anim_data.pairs]
    # Generate compressed value table and offsets
    value_table_parts: list[(list[SM64_AnimPair], list[int])] = []
    for pair in all_pairs:
        values = pair.values
        assert len(values) <= MAX_U16, "Pair frame count is higher than the 16 bit max."

        for value_table_part_pairs, value_table_part in value_table_parts:
            index = index_sub_seq_in_seq(values, value_table_part)
            if index != -1:
                pair.offset = index
                value_table_part_pairs.append(pair)
                break
            # TODO: Add more extensive compression in the future
        else:
            value_table_parts.append(([pair], values))
            pair.offset = 0

    for value_table_part_pairs, value_table_part in value_table_parts:
        for pair in value_table_part_pairs:
            pair.offset += len(value_table.data)
            assert pair.offset <= MAX_U16, "Pair offset is higher than the 16 bit max."
        value_table.data.extend(value_table_part)

    indice_tables: list[SM64_ShortArray] = []
    # Use calculated offsets to generate the indices table
    for anim_data in anims_data:
        indice_table = SM64_ShortArray(anim_data.indice_reference, False)
        for pair in anim_data.pairs:
            indice_table.data.extend([len(pair.values), pair.offset])
        indice_tables.append(indice_table)
    return value_table, indice_tables
