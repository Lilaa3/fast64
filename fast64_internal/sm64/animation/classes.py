import dataclasses
from io import StringIO
import os
import copy
from typing import Optional

from bpy.types import Action

from ...utility import PluginError, encodeSegmentedAddr, is_bit_active, to_s16, intToHex
from ..sm64_constants import MAX_U16
from ..classes import RomReader, DMATable, DMATableElement, ShortArray

from .constants import HEADER_SIZE, C_FLAGS


@dataclasses.dataclass
class CArrayDeclaration:
    name: str = ""
    path: os.PathLike = ""
    file_name: str = ""
    values: list[str] = dataclasses.field(default_factory=str)


@dataclasses.dataclass
class AnimationPair:
    values: list[int] = dataclasses.field(default_factory=list)

    # Importing
    address: int = 0
    end_address: int = 0
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
        self.values = self.values[:1]

    def get_frame(self, frame: int):
        return self.values[min(frame, len(self.values) - 1)]

    def read_binary(self, indices_reader: RomReader, values_reader: RomReader):
        max_frame = indices_reader.read_value(2)
        self.offset = indices_reader.read_value(2) * 2
        values_reader = values_reader.branch(values_reader.start_address + self.offset)
        self.address = values_reader.address
        for _ in range(max_frame):
            self.values.append(values_reader.read_value(2, signed=True))
        self.end_address = values_reader.address
        return self


@dataclasses.dataclass
class AnimationData:
    pairs: list[AnimationPair] = dataclasses.field(default_factory=list)
    indice_reference: str | int = ""
    values_reference: str | int = ""
    indices_file_name: str | int = ""
    values_file_name: str | int = ""

    # Importing
    value_end_address: int = 0
    indice_end_address: int = 0
    start_address: int = 0
    end_address: int = 0

    def to_c(self, is_dma_structure: bool = False):
        text_data = StringIO()

        value_table, indice_tables = create_tables([self])
        indice_table = indice_tables[0]

        if is_dma_structure:
            text_data.write(indice_table.to_c())
            text_data.write("\n")
            text_data.write(value_table.to_c())
        else:
            text_data.write(value_table.to_c())
            text_data.write("\n")
            text_data.write(indice_table.to_c())

        return text_data.getvalue()

    def to_binary(self) -> bytearray:
        data: bytearray = bytearray()

        value_table, indice_tables = create_tables([self])
        indice_table = indice_tables[0]
        values_offset = len(indice_table.data) * 2
        data.extend(indice_table.to_binary())
        data.extend(value_table.to_binary())
        return data, values_offset

    def read_binary(self, indices_reader: RomReader, values_reader: RomReader, bone_count: int):
        self.indice_reference = indices_reader.start_address
        self.values_reference = values_reader.start_address
        for _ in range((bone_count + 1) * 3):
            pair = AnimationPair()
            pair.read_binary(indices_reader, values_reader)
            self.pairs.append(pair)
        self.indice_end_address = indices_reader.address
        self.value_end_address = max(pair.end_address for pair in self.pairs)

        self.start_address = min(self.indice_reference, self.values_reference)
        self.end_address = max(self.indice_end_address, self.value_end_address)
        return self

    def read_c(self, indice_decl: CArrayDeclaration, value_decl: CArrayDeclaration):
        self.indices_file_name, self.values_file_name = indice_decl.file_name, value_decl.file_name
        self.indice_reference, self.values_reference = indice_decl.name, value_decl.name
        for i in range(0, len(indice_decl.values), 2):
            pair = AnimationPair()
            max_frame = int(indice_decl.values[i], 0)
            offset = int(indice_decl.values[i + 1], 0)
            for j in range(max_frame):
                pair.values.append(to_s16(int(value_decl.values[offset + j], 0)))
            self.pairs.append(pair)
        return self


@dataclasses.dataclass
class AnimationHeader:
    reference: str | int = ""
    flags: int | str = 0
    trans_divisor: int = 0
    start_frame: int = 0
    loop_start: int = 0
    loop_end: int = 1
    bone_count: int = 0
    indice_reference: Optional[str | int] = None
    values_reference: Optional[str | int] = None
    data: Optional[AnimationData] = None

    enum_name: str = ""
    file_name: str = ""
    # Imports
    end_address: int = 0
    header_variant: int = 0
    table_index: int = 0

    def get_flags_comment(self):
        if isinstance(self.flags, str):
            return self.flags
        flags_list: list[str] = []
        for index, flags in enumerate(C_FLAGS):
            if is_bit_active(self.flags, index):
                flags_list.append("/".join(flags))

        return ", ".join(flags_list)

    def get_c_flags(self):
        if isinstance(self.flags, str):
            return self.flags

        return intToHex(self.flags, 2)

    def get_values_reference(self, override: Optional[str | int] = None, expected_type: type = str):
        if override:
            reference = override
        elif self.data and self.data.values_reference:
            reference = self.data.values_reference
        elif self.values_reference:
            reference = self.values_reference
        assert isinstance(
            reference, expected_type
        ), f"Value reference must be a {expected_type}, but instead is equal to {reference}."
        return reference

    def get_indice_reference(self, override: Optional[str | int] = None, expected_type: type = str):
        if override:
            reference = override
        elif self.data and self.data.indice_reference:
            reference = self.data.indice_reference
        elif self.indice_reference:
            reference = self.indice_reference
        assert isinstance(
            reference, expected_type
        ), f"Indice reference must be a {expected_type}, but instead is equal to {reference}."
        return reference

    def to_c(
        self,
        values_override: Optional[str] = None,
        indice_override: Optional[str] = None,
        is_dma_structure: bool = False,
    ):
        return (
            f"static const struct Animation {self.reference}{'[]' if is_dma_structure else ''} = {{\n"
            + (f"\t{intToHex(self.flags, 2)}, " if is_dma_structure else f"\t{self.get_c_flags()}, ")
            + f"// flags {self.get_flags_comment()}\n"
            f"\t{self.trans_divisor}, // animYTransDivisor\n"
            f"\t{self.start_frame}, // startFrame\n"
            f"\t{self.loop_start}, // loopStart\n"
            f"\t{self.loop_end}, // loopEnd\n"
            f"\tANIMINDEX_NUMPARTS({self.get_indice_reference(indice_override)}), // unusedBoneCount\n"
            f"\t{self.get_values_reference(values_override, str)}, // values\n"
            f"\t{self.get_indice_reference(indice_override, str)}, // index\n"
            "\t0 // length\n"
            "};\n"
        )

    def to_binary(
        self,
        values_override: Optional[int] = None,
        indice_override: Optional[int] = None,
        segment_data: dict[int, tuple[int, int]] = None,
    ):
        data = bytearray()
        data.extend(self.flags.to_bytes(2, byteorder="big"))  # 0x00
        data.extend(self.trans_divisor.to_bytes(2, byteorder="big", signed=True))  # 0x02
        data.extend(self.start_frame.to_bytes(2, byteorder="big", signed=True))  # 0x04
        data.extend(self.loop_start.to_bytes(2, byteorder="big", signed=True))  # 0x06
        data.extend(self.loop_end.to_bytes(2, byteorder="big", signed=True))  # 0x08
        data.extend(self.bone_count.to_bytes(2, byteorder="big", signed=True))  # 0x0A
        values_address = self.get_values_reference(values_override, int)
        indice_address = self.get_indice_reference(indice_override, int)
        if segment_data:
            data.extend(encodeSegmentedAddr(values_address, segment_data))  # 0x0C
            data.extend(encodeSegmentedAddr(indice_address, segment_data))  # 0x10
        else:
            data.extend(values_address.to_bytes(4, byteorder="big"))  # 0x0C
            data.extend(indice_address.to_bytes(4, byteorder="big"))  # 0x10
        data.extend(bytearray([0x00] * 4))  # 0x14 # Unused with no porpuse, however,
        # in the mario dma table it's generated by taking the sum of the offset and size of the values table
        # and subtracting by the offset of the header, the offsets are relative to the table
        # TODO: Implement the described logic for DMA table binary exports
        # 0x18
        return data

    @staticmethod
    def read_binary(
        header_reader: RomReader,
        animation_headers: dict[str, "AnimationHeader"],
        animation_data: dict[tuple[str, str], "Animation"],
        is_dma: bool = False,
        assumed_bone_count: int | None = None,
        table_index: int | None = None,
    ):
        if str(header_reader.start_address) in animation_headers:
            return animation_headers[str(header_reader.start_address)]

        header = AnimationHeader()
        animation_headers[str(header_reader.start_address)] = header
        header.reference = header_reader.start_address
        header.flags = header_reader.read_value(2)  # /*0x00*/ s16 flags;
        header.trans_divisor = header_reader.read_value(2)  # /*0x02*/ s16 animYTransDivisor;
        header.start_frame = header_reader.read_value(2)  # /*0x04*/ s16 startFrame;
        header.loop_start = header_reader.read_value(2)  # /*0x06*/ s16 loopStart;
        header.loop_end = header_reader.read_value(2)  # /*0x08*/ s16 loopEnd;
        bone_count = header_reader.read_value(2)  # /*0x0A*/ s16 unusedBoneCount; (Unused in engine)
        header.bone_count = bone_count if assumed_bone_count is None else assumed_bone_count
        # /*0x0C*/ const s16 *values;
        # /*0x10*/ const u16 *index;
        if is_dma:
            start_address = header_reader.start_address
            header.values_reference = start_address + header_reader.read_value(4)
            header.indice_reference = start_address + header_reader.read_value(4)
        else:
            header.values_reference = header_reader.read_ptr()
            header.indice_reference = header_reader.read_ptr()
        header.length = header_reader.read_value(4)

        header.end_address = header_reader.address
        header.table_index = len(animation_headers) if table_index is None else table_index

        data_key = (str(header.indice_reference), str(header.values_reference))
        if not data_key in animation_data:
            animation = Animation()
            indices_reader = header_reader.branch(header.indice_reference)
            values_reader = header_reader.branch(header.values_reference)
            if indices_reader and values_reader:
                animation.data = AnimationData().read_binary(
                    indices_reader,
                    values_reader,
                    header.bone_count,
                )
            animation_data[data_key] = animation
        animation = animation_data[data_key]
        header.data = animation.data
        header.header_variant = len(animation.headers)
        animation.headers.append(header)

        return header

    @staticmethod
    def read_c(
        header_decl: CArrayDeclaration,
        value_decls,
        indices_decls,
        animation_headers: dict[str, "AnimationHeader"],
        animation_data: dict[tuple[str, str], "Animation"],
    ):
        if header_decl.name in animation_headers:
            return animation_headers[header_decl.name]
        if len(header_decl.values) != 9:
            raise ValueError(f"Header declarion has {len(header_decl.values)} values instead of 9.\n {header_decl}")

        header = AnimationHeader()
        animation_headers[header_decl.name] = header
        header.reference = header_decl.name
        header.file_name = header_decl.file_name

        # Place the values into a dictionary, handles designated initialization
        var_defs = [
            "flags",
            "animYTransDivisor",
            "startFrame",
            "loopStart",
            "loopEnd",
            "unusedBoneCount",
            "values",
            "index",
            "length",
        ]
        designated = {}
        for i, value in enumerate(header_decl.values):
            var_value_split: list[str] = value.split("=")
            value = var_value_split[-1].strip()
            if len(var_value_split) == 2:
                var = var_value_split[0].replace(".", "", 1).strip()
                designated[var] = value
            else:
                designated[var_defs[i]] = value

        # Read from the dict
        header.flags = designated["flags"]
        header.trans_divisor = int(designated["animYTransDivisor"], 0)
        header.start_frame = int(designated["startFrame"], 0)
        header.loop_start = int(designated["loopStart"], 0)
        header.loop_end = int(designated["loopEnd"], 0)
        # bone_count = designated["unusedBoneCount"]
        header.values_reference = designated["values"]
        header.indice_reference = designated["index"]

        data_key = (header.indice_reference, header.values_reference)
        if not data_key in animation_data:
            indices_decl = next(
                (indice for indice in indices_decls if indice.name == header.indice_reference),
                None,
            )
            value_decl = next(
                (value for value in value_decls if value.name == header.values_reference),
                None,
            )
            animation = Animation()
            if indices_decl and value_decl:
                animation.data = AnimationData().read_c(indices_decl, value_decl)
            animation_data[data_key] = animation
        animation = animation_data[data_key]
        header.data = animation.data
        header.header_variant = len(animation.headers)
        animation.headers.append(header)

        return header


@dataclasses.dataclass
class Animation:
    data: AnimationData = None
    headers: list[AnimationHeader] = dataclasses.field(default_factory=list)
    file_name: str | None = ""

    # Imports
    action: Action | None = None  # Used in the table class to prop function

    @property
    def enum_and_header_names(self) -> list[str, str]:
        names = []
        for header in self.headers:
            assert isinstance(header.reference, str), "Reference is not a string."
            names.append((header.enum_name, header.reference))
        return names

    def to_binary_dma(self):
        assert self.data
        headers: list[bytearray] = []

        indice_offset = HEADER_SIZE * len(self.headers)
        anim_data, values_offset = self.data.to_binary()
        for header in self.headers:
            header_data = header.to_binary(indice_offset + values_offset, indice_offset)
            headers.append(header_data)
            indice_offset -= HEADER_SIZE
        return headers, anim_data

    def to_binary(self, start_address: int = 0, segment_data: dict[int, tuple[int, int]] = None):
        data: bytearray = bytearray()
        ptrs: list[int] = []
        if self.data:
            indice_offset = start_address + (HEADER_SIZE * len(self.headers))
            anim_data, values_offset = self.data.to_binary()
        for header in self.headers:
            ptrs.extend([start_address + len(data) + 12, start_address + len(data) + 16])
            header_data = header.to_binary(
                indice_offset + values_offset if self.data else None,
                indice_offset if self.data else None,
                segment_data,
            )
            data.extend(header_data)
        if self.data:
            data.extend(anim_data)
            return data, ptrs
        return data, []

    def headers_to_c(self, is_dma_structure: bool) -> str:
        text_data = StringIO()
        for header in self.headers:
            text_data.write(header.to_c(is_dma_structure=is_dma_structure))
            text_data.write("\n")
        return text_data.getvalue()

    def to_c(self, is_dma_structure: bool):
        text_data = StringIO()

        c_headers = self.headers_to_c(is_dma_structure)
        if is_dma_structure:
            text_data.write(c_headers)
            text_data.write("\n")
        if self.data:
            text_data.write(self.data.to_c(is_dma_structure))
            text_data.write("\n")
        if not is_dma_structure:
            text_data.write(c_headers)

        return text_data.getvalue()


@dataclasses.dataclass
class AnimationTableElement:
    reference: str | int = ""
    enum_name: str | None = None
    header: AnimationHeader | None = None

    @property
    def data(self):
        return self.header.data if self.header else None


@dataclasses.dataclass
class AnimationTable:
    reference: str | int = None
    enum_list_reference: str = ""
    file_name: str = ""
    values_reference: str = ""
    elements: list[AnimationTableElement] = dataclasses.field(default_factory=list)

    # Importing
    end_address: int = 0

    @property
    def enum_and_header_names(self) -> list[str, str]:
        names = []
        for element in self.elements:
            assert isinstance(element.reference, str), "Reference is not a string."
            names.append((element.enum_name, element.reference))
        return names

    def get_sets(self) -> tuple[list[AnimationHeader], list[AnimationData]]:
        # Remove duplicates of data and headers, keep order by using a list
        data_set = []
        headers_set = []
        for element in self.elements:
            if element.data and not element.data in data_set:
                data_set.append(element.data)
            if element.header and not element.header in headers_set:
                headers_set.append(element.header)
        return headers_set, data_set

    def get_seperate_anims(self):
        anims = []
        headers_set, headers_added = self.get_sets()[0], []
        for header in headers_set:
            if header in headers_added:
                continue
            ordered_headers: list[AnimationHeader] = []
            for other_header in headers_set:
                if other_header.data == header.data:
                    ordered_headers.append(other_header)
                    headers_added.append(other_header)

            anims.append(Animation(header.data, ordered_headers, header.file_name))
        return anims

    def get_seperate_anims_dma(self) -> list[Animation]:
        def num_to_padded_hex(num: int):
            hex_str = hex(num)[2:].upper()  # remove the '0x' prefix
            return hex_str.zfill(2)

        anims = []
        header_nums = []
        included_headers = []
        data = None
        # For creating duplicates
        data_already_added = []
        headers_already_added = []

        for i, element in enumerate(self.elements):
            assert element.header, f"Header in table element {i} is not set."
            assert element.data, f"Data in table element {i} is not set."
            header_nums.append(i)

            header, data = element.header, element.data
            if header in headers_already_added:
                header = copy.copy(header)
            header.reference = f"anim_{num_to_padded_hex(i)}"
            headers_already_added.append(header)

            included_headers.append(header)

            # If not at the end of the list and the next element doesn´t have different data
            if (i < len(self.elements) - 1) and self.elements[i + 1].data is data:
                continue

            name = f'anim_{"_".join([f"{num_to_padded_hex(num)}" for num in header_nums])}'
            file_name = f"{name}.inc.c"
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
                included_header.indice_reference = data.indice_reference
                included_header.values_reference = data.values_reference
                included_header.data = data
            anims.append(Animation(data, included_headers, file_name))

            header_nums.clear()
            included_headers = []

        return anims

    def to_binary_dma(self):
        dma_table = DMATable()
        for animation in self.get_seperate_anims_dma():
            headers, data = animation.to_binary_dma()
            end_offset = len(dma_table.data) + (HEADER_SIZE * len(headers)) + len(data)
            for header in headers:
                offset = len(dma_table.data)
                size = end_offset - offset
                dma_table.entries.append(DMATableElement(offset, size))
                dma_table.data.extend(header)
            dma_table.data.extend(data)
        return dma_table.to_binary()

    def to_combined_binary(
        self,
        table_start_address: int = 0,
        data_start_address: int = -1,
        segment_data: dict[int, tuple[int, int]] = None,
    ):
        table_data: bytearray = bytearray()
        data: bytearray = bytearray()
        ptrs: list[int] = []
        headers_set, data_set = self.get_sets()

        # Pre calculate offsets
        table_length = len(self.elements) * 4 + 4
        if data_start_address == -1:
            headers_offset = table_start_address + table_length
        else:
            headers_offset = data_start_address
        if data_set:
            headers_length = len(headers_set) * HEADER_SIZE
            value_table, indice_tables = create_tables(data_set, self.values_reference)
            indice_tables_offset = headers_offset + headers_length
            values_table_offset = indice_tables_offset + sum(
                [len(indice_table.data) * 2 for indice_table in indice_tables]
            )

        # Add the animation table
        for i, element in enumerate(self.elements):
            if element.header:
                ptrs.append(table_start_address + len(table_data))
                header_offset = headers_offset + (headers_set.index(element.header) * HEADER_SIZE)
                if segment_data:
                    table_data.extend(encodeSegmentedAddr(header_offset, segment_data))
                else:
                    table_data.extend(header_offset.to_bytes(4, byteorder="big"))
            else:
                assert isinstance(element.reference, int), f"Reference at element {i} is not an int."
                table_data.extend(element.reference.to_bytes(4, byteorder="big"))
        table_data.extend(bytearray([0x00] * 4))  # NULL delimiter

        for anim_header in headers_set:  # Add the headers
            if not anim_header.data:
                data.extend(anim_header.to_binary())
                continue
            ptrs.extend([data_start_address + len(data) + 12, data_start_address + len(data) + 16])
            indice_offset = indice_tables_offset + sum(
                len(indice_table.data) * 2 for indice_table in indice_tables[: data_set.index(anim_header.data)]
            )
            data.extend(anim_header.to_binary(values_table_offset, indice_offset, segment_data))
        if data_set:  # Add the data
            for indice_table in indice_tables:
                data.extend(indice_table.to_binary())
            data.extend(value_table.to_binary())

        return table_data, data, ptrs

    def data_and_headers_to_c(self, is_dma: bool) -> list[os.PathLike, str]:
        files_data: dict[str, str] = {}
        for anim in self.get_seperate_anims_dma() if is_dma else self.get_seperate_anims():
            files_data[anim.file_name] = anim.to_c(is_dma_structure=is_dma)
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
        text_data.write(f"\t{self.enum_list_reference.upper()}_END,\n")
        text_data.write("};\n")

        return text_data.getvalue()

    def table_to_c(self):
        text_data = StringIO()

        text_data.write(f"const struct Animation *const {self.reference}[] = {{\n")
        for element in self.elements:
            text_data.write(f"\t&{element.reference},\n")
        text_data.write("\tNULL,\n")
        text_data.write("};\n")

        return text_data.getvalue()

    def read_binary(
        self,
        reader: RomReader,
        animation_headers: dict[str, AnimationHeader],
        animation_data: dict[tuple[str, str], Animation],
        table_index: int | None = None,
        assumed_bone_count: int | None = 0,
        size: int | None = None,
    ) -> AnimationHeader | None:
        self.elements.clear()
        self.reference = reader.start_address
        range_size = size if size else 300
        if table_index is not None:
            range_size = min(range_size, table_index + 1)
        for i in range(range_size):
            ptr = reader.read_ptr()
            if size is None and ptr == 0:
                break
            if table_index is not None and i != table_index:
                continue

            header_reader = reader.branch(ptr)
            header = None
            if header_reader:
                header = AnimationHeader.read_binary(
                    header_reader, animation_headers, animation_data, False, assumed_bone_count, i
                )
            else:
                header = None
            self.elements.append(AnimationTableElement(ptr, None, header))
        else:
            if table_index is not None:
                raise PluginError(f"Table index {table_index} not found in table.")
            if size is None:
                raise PluginError(f"Iterated through {range_size} elements and no NULL was found.")
        self.end_address = reader.address
        return self

    def read_dma_binary(
        self,
        reader: RomReader,
        animation_headers: dict[str, AnimationHeader],
        animation_data: dict[tuple[str, str], Animation],
        table_index: int | None = None,
        assumed_bone_count: int | None = None,
    ):
        dma_table = DMATable()
        dma_table.read_binary(reader)
        self.reference = reader.start_address
        if table_index is not None:
            assert table_index >= 0 and table_index < len(
                dma_table.entries
            ), f"Index {table_index} outside of defined table ({len(dma_table.entries)} entries)."
            entrie = dma_table.entries[table_index]
            return AnimationHeader.read_binary(
                reader.branch(entrie.address),
                animation_headers,
                animation_data,
                True,
                assumed_bone_count,
                table_index,
            )

        for i, entrie in enumerate(dma_table.entries):
            header = AnimationHeader.read_binary(
                reader.branch(entrie.address),
                animation_headers,
                animation_data,
                True,
                assumed_bone_count,
                i,
            )
            self.elements.append(AnimationTableElement(reader.start_address, None, header))
        self.end_address = dma_table.end_address
        return self

    def read_c(
        self,
        table_decl: CArrayDeclaration,
        animation_headers: dict[str, AnimationHeader],
        animation_data: dict[tuple[str, str], Animation],
        header_decls: list[CArrayDeclaration],
        values_decls: list[CArrayDeclaration],
        indices_decls: list[CArrayDeclaration],
    ):
        self.elements.clear()
        for value in table_decl.values:
            enum_name_split: list[str] = value.split("=")
            header_name = enum_name_split[-1].replace("&", "").strip()
            enum_name = (
                enum_name_split[0].replace("[", "", 1).replace("]", "", 1).strip()
                if len(enum_name_split) == 2
                else None
            )

            if header_name not in animation_headers:
                header_decl = next(
                    (header for header in header_decls if header.name == header_name),
                    None,
                )
                if header_decl:
                    animation_headers[header_name] = AnimationHeader.read_c(
                        header_decl, values_decls, indices_decls, animation_headers, animation_data
                    )
            self.elements.append(
                AnimationTableElement(enum_name_split[-1], enum_name, animation_headers.get(header_name, None))
            )
        if self.elements and header_name == "NULL":
            self.elements.pop()  # Remove table end identifier from import
        return self


def create_tables(anims_data: list[AnimationData], values_name: str = None):
    """Can generate multiple indices table with only one value table, which improves compression"""
    """This feature is used in table exports"""

    value_table = ShortArray(values_name if values_name else anims_data[0].values_reference, True)
    data = value_table.data

    # Generate compressed value table and offsets
    for pair in [pair for anim_data in anims_data for pair in anim_data.pairs]:
        values = pair.values
        assert len(values) <= MAX_U16, "Pair frame count is higher than the 16 bit max."

        # It's never worth to find an offset for values bigger than 1 frame from my testing
        # the one use case resulted in a 286 bytes improvement, which for a slow down of all exports
        # is not worth it
        pair.offset = data.index(values[0]) if len(values) == 1 and values[0] in data else None
        if pair.offset is None:
            pair.offset = len(data)
            data.extend(values)
        assert pair.offset <= MAX_U16, "Pair offset is higher than the 16 bit max."

    indice_tables: list[ShortArray] = []
    # Use calculated offsets to generate the indices table
    for anim_data in anims_data:
        indice_table = ShortArray(anim_data.indice_reference, False)
        for pair in anim_data.pairs:
            indice_table.data.extend([len(pair.values), pair.offset])
        indice_tables.append(indice_table)
    return value_table, indice_tables
