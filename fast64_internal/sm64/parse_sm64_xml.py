import dataclasses
import traceback
import xml.etree.ElementTree as ET
import logging
from pathlib import Path
from typing import Union, Optional

from .sm64_utility import int_from_str
from ..utility import hexOrDecInt, filepath_checks

logger = logging.getLogger(__name__)


class ParseError(Exception):
    pass


@dataclasses.dataclass(frozen=True)
class BehaviorFieldEnum:
    name: str
    description: Optional[str]
    value: int
    c_name: str


@dataclasses.dataclass(frozen=True)
class BehaviorField:
    name: str
    description: Optional[str]
    type: str
    bparam: list[int]
    default: Optional[int|str] = None
    enums: list[BehaviorFieldEnum] = dataclasses.field(default_factory=list)
    mask: int = 0
    shift: int = 0
    multiplier: int = 1
    offset: int = 0
    min: int = 0
    max: int = 0

@dataclasses.dataclass(frozen=True)
class AnimationTable:
    address: int
    name: str
    dma: Optional[str]
    directory: Optional[str]
    names: list[str]
    behaviors: list[str]


@dataclasses.dataclass(frozen=True)
class Collision:
    c_name: str
    address: int
    readable_name: str


@dataclasses.dataclass(frozen=True)
class Behavior:
    name_or_address: int|str
    readable_name: str
    description: str
    dev_comment: str
    tags: list[str]
    models: list[str]
    collisions: list[Collision]
    fields: list[BehaviorField]


@dataclasses.dataclass(frozen=True)
class ModelId:
    value: int
    name: str
    level: Optional[str]


@dataclasses.dataclass(frozen=True)
class Model:
    readable_name: str
    geolayout: Optional[str]
    group: Optional[str]
    ids: list[ModelId]
    tables: list[str]
    collisions: list[str]


class SM64XMLParser:
    def _get_attr(
        self,
        element: ET.Element,
        attr: str,
        required: bool = True,
        convert_int: bool = False,
        convert_float: bool = False,
        convert_bool: bool = False,
    ):
        """Retrieves an attribute, optionally converting it to an integer."""
        val = element.get(attr)
        if val is None:
            if required:
                raise ParseError(f"Missing required attribute '{attr}' in <{element.tag}>")
            return None
        if convert_float:
            if convert_int:
                try:
                    return int(val, 0)
                except ValueError:
                    pass
            return float(val)
        if convert_bool:
            if val.lower() == "true":
                return True
            if val.lower() == "false":
                return False
            return int_from_str(val)
        return int_from_str(val) if convert_int else val

    def _get_text(self, root: ET.Element, tag: str, required: bool = False, convert_int: bool = False):
        """Finds a child element and returns its text, optionally converting to int."""
        elem = root.find(tag)
        if elem is None:
            if required:
                raise ParseError(f"Missing required element <{tag}> inside <{root.tag}>")
            return None

        val = elem.text
        if val is None:
            return None
        return int_from_str(val) if convert_int else val

    def _get_list(self, root: ET.Element, parent_tag: str, child_tag: str) -> list[str]:
        """Helper to extract a list of strings from a parent/child tag structure."""
        parent = root.find(parent_tag)
        if parent is None:
            return []
        self._check_unknown_elements(parent, [child_tag])
        return [c.text for c in parent.findall(child_tag) if c.text]

    def _check_unknown_elements(self, element: ET.Element, expected_tags: list[str]):
        for child in element:
            if child.tag not in expected_tags:
                raise ParseError(
                    f"Unknown element <{child.tag}> found inside <{element.tag}>. Expected: {', '.join(expected_tags)}"
                )

    def _check_unknown_attributes(self, element: ET.Element, expected_attrs: list[str]):
        """Ensures no unexpected attributes are present on an element."""
        for attr in element.attrib:
            if attr not in expected_attrs:
                raise ParseError(
                    f"Unknown attribute '{attr}' in <{element.tag}>. Expected: {', '.join(expected_attrs)}"
                )

    def _parse_collision(self, element: ET.Element, base_name: str, more_than_one: bool) -> Collision:
        self._check_unknown_elements(element, [])

        name = self._get_attr(element, "c_name")
        address = self._get_attr(element, "address", convert_int=True)
        readable_name = self._get_attr(element, "readable_name", required=False)

        if readable_name is None:
            readable_name = name
            if more_than_one:
                split_name = name.split("_collision_")
                if len(split_name) == 2:
                    readable_name = f"{base_name} {split_name[1].replace('_', ' ').title()}"
                else:
                    readable_name = f"{base_name} {name}"
        elif base_name and not more_than_one:
            logger.warning("Not recommended to include per collision name when there is only one collision model.")

        return Collision(name, address, readable_name)

    def _parse_animation_table(self, root: ET.Element, name: str) -> AnimationTable:
        self._check_unknown_elements(root, ["names", "behaviors"])

        address = self._get_attr(root, "address", convert_int=True)
        name = self._get_attr(root, "name")
        dma = self._get_attr(root, "dma", required=False)
        directory = self._get_attr(root, "directory", required=False)
        behaviors = self._get_list(root, "behaviors", "behavior")

        names = self._get_list(root, "names", "name")
        if not names:
            raise ParseError("Missing or empty <names> section in <animation_table>")

        return AnimationTable(address, name, dma, directory, names, behaviors)

    def apply_mul_offset(self, value: int|float, offset: int|float, multiplier: int|float):
        return value * multiplier - offset

    def undo_mul_offset(self, value: int|float, offset: int|float, multiplier: int|float):
        return (value + offset) / multiplier

    def get_mask_info(self, bparam: list[int], mask: Optional[int] = None, shift: int = 0):
        """Calculates the raw bit-width and maximum value allowed by the mask."""
        param_bit_width = len(bparam) * 8
        if mask is None:
            mask = ((1 << param_bit_width) - 1) >> shift
        max_raw_value = mask
        
        return mask, max_raw_value, param_bit_width

    def validate_field_constraints(self, field: BehaviorField):
        """Checks if default, min, and max are valid for the field's bitmask and type."""
        if field.type == "bool":
            if field.default not in [None, True, False, 0, 1]:
                raise ParseError(f"Field '{field.name}' is bool but has non-boolean default: {field.default}")
            return

        if field.min is not None and field.max is not None:
            if field.min > field.max:
                raise ParseError(f"Field '{field.name}' has min ({field.min}) > max ({field.max})")

        if field.default is not None:
            # Check against explicit min/max
            if field.min is not None and field.default < field.min:
                raise ParseError(f"Default {field.default} for '{field.name}' is below min {field.min}")
            if field.max is not None and field.default > field.max:
                raise ParseError(f"Default {field.default} for '{field.name}' is above max {field.max}")

    def validate_fields(self, fields: list[BehaviorField]):
        used_bparams = {}

        for field in fields:
            # Continuity Check
            if any(field.bparam[i] != field.bparam[i-1] + 1 for i in range(1, len(field.bparam))):
                raise ParseError(f"Field '{field.name}' has non-continuous bparams: {field.bparam}")

            self.validate_field_constraints(field)

            full_field_mask = field.mask << field.shift
            
            # Check if the mask/shift actually fits in the allocated bparams
            if (full_field_mask).bit_length() > self.get_mask_info(field.bparam)[2]:
                raise ParseError(f"Field '{field.name}' mask/shift exceeds its {len(field.bparam)} bparams.")

            # Map to individual bytes to find overlaps
            temp_mask = full_field_mask
            for bp_index in reversed(field.bparam):
                byte_bits = temp_mask & 0xFF
                if byte_bits:
                    if used_bparams.get(bp_index, 0) & byte_bits:
                        raise ParseError(f"Field '{field.name}' overlaps bits in bparam {bp_index}.")
                    used_bparams[bp_index] = used_bparams.get(bp_index, 0) | byte_bits
                temp_mask >>= 8

    def _parse_field_enum(self, element: ET.Element, is_bool: bool) -> BehaviorFieldEnum:
        """Parses an <enum> tag within a field."""
        self._check_unknown_elements(element, ["description"])
        self._check_unknown_attributes(element, ["name", "value", "c_name"])

        if is_bool:
            name = description = ""
            value = None
        else:
            name = self._get_attr(element, "name")
            description = self._get_text(element, "description", required=False)
            value = self._get_attr(element, "value", convert_int=True)
        c_name = self._get_attr(element, "c_name", required=False)
        return BehaviorFieldEnum(name=name, description=description, value=value, c_name=c_name)

    def _parse_field(self, root: ET.Element) -> BehaviorField:
        self._check_unknown_elements(root, ["enums", "description"])
        self._check_unknown_attributes(
            root, ["name", "type", "bparam", "default", "shift", "mask", "multiplier", "offset", "min", "max"]
        )

        name = self._get_attr(root, "name")
        field_type = self._get_attr(root, "type")
        description = self._get_text(root, "description", required=False)
        shift = self._get_attr(root, "shift", convert_int=True, required=False) or 0
        multiplier = self._get_attr(root, "multiplier", convert_int=True, required=False) or 1
        offset = self._get_attr(root, "offset", convert_int=True, required=False) or 0

        if field_type not in {"int", "float", "bool", "dialogue_id", "units", "frames", "bitflag"}:
            raise ParseError(f"Unsupported field type '{field_type}' in field '{name}'.")

        default = self._get_attr(
            root,
            "default",
            convert_int=(field_type in {"int", "dialogue_id", "units", "frames", "bitflag"}),
            convert_bool=(field_type == "bool"),
            convert_float=(field_type == "units"),
            required=False,
        )

        bparams = self._get_attr(root, "bparam")
        bparams = [int(bparam) for bparam in bparams]
        if any(bparam < 1 or bparam > 4 for bparam in bparams):
            raise ParseError(f"Invalid bparam '{bparams}' in field '{name}'. Must be between 1 and 4.")

        enums = []
        enums_elem = root.find("enums")
        if enums_elem is not None:
            self._check_unknown_elements(enums_elem, ["enum"])
            for enum_node in enums_elem.findall("enum"):
                enums.append(self._parse_field_enum(enum_node, field_type == "bool"))
        
        mask = self._get_attr(root, "mask", convert_int=True, required=False)
        if enums:
            max_enum = max(enum.value or i for i, enum in enumerate(enums))
            bits = max(0, max_enum.bit_length())
            mask = (1 << bits) - 1
        if field_type == "bool":
            if mask is not None and mask != 1:
                logger.warning(f"Invalid mask '{mask}' for bool field '{name}'. Must be 1.")
            mask = 1
        mask, max_raw_val, _bit_width = self.get_mask_info(bparams, mask, shift)
        min_value = self._get_attr(root, "min", convert_int=True, required=False) or self.apply_mul_offset(0, offset, multiplier)
        max_value = self._get_attr(root, "max", convert_int=True, required=False) or self.apply_mul_offset(max_raw_val, offset, multiplier)

        field = BehaviorField(
            name,
            description,
            field_type,
            bparams,
            default,
            enums,
            mask,
            shift,
            multiplier,
            offset,
            min_value,
            max_value
        )

        return field

    def _parse_behavior_wrapped(self, root: ET.Element, name_or_address: str|int) -> Behavior:
        self._check_unknown_elements(
            root, ["name", "readable_name", "tags", "models", "collisions", "description", "comment", "fields", "particle"]
        )

        description = self._get_text(root, "description") or ""
        readable_name = self._get_attr(root, "readable_name")
        comment = self._get_text(root, "comment")
        particle = self._get_text(root, "particle")

        tags = self._get_list(root, "tags", "tag")
        if particle is not None and "PARTICLE" not in tags:
            logger.warning(f"Behavior {readable_name} has a particle, but no PARTICLE tag.")

        models = self._get_list(root, "models", "model")

        # Restrictive field parsing
        fields = []
        fields_container = root.find("fields")
        if fields_container is not None:
            self._check_unknown_elements(fields_container, ["field"])
            for field_node in fields_container.findall("field"):
                fields.append(self._parse_field(field_node))

        self.validate_fields(fields)

        collisions = []
        collisions_elem = root.find("collisions")
        if collisions_elem is not None:
            self._check_unknown_elements(collisions_elem, ["collision"])
            collision_elements = collisions_elem.findall("collision")
            for c in collision_elements:
                try:
                    collisions.append(self._parse_collision(c, readable_name, len(collision_elements) > 1))
                except Exception as exc:
                    raise ParseError(f"Error while parsing <collision>:\n{exc}") from exc

        return Behavior(name_or_address, readable_name, description, comment, tags, models, collisions, fields)

    def _parse_behavior(self, root: ET.Element, file_name: str) -> Behavior:
        address = None
        readable_name = None
        try:
            readable_name = self._get_attr(root, "readable_name")
            address = self._get_attr(root, "address", convert_int=True, required=False)
            name = self._get_attr(root, "name", required=False)
            if name is None and address is None:
                raise ParseError("Must specify either \"name\" or \"address\"")
            name_or_address = name or address
            return self._parse_behavior_wrapped(root, name_or_address)
        except Exception as exc:
            given_name = readable_name or name_or_address
            if given_name is None:
                raise ParseError(f"Error while parsing behavior in file {file_name}:\n{exc}")
            raise ParseError(f"Error while parsing behavior \"{given_name}\" in file {file_name}:\n{exc}") from exc

    def _parse_model_wrapped(self, root: ET.Element):
        self._check_unknown_elements(
            root, ["geolayout", "displaylist", "ids", "animation_tables", "collisions", "level", "group"]
        )

        readable_name = self._get_attr(root, "readable_name")
        geolayout = self._get_text(root, "geolayout", convert_int=True)

        displaylist_elem = root.find("displaylist")
        if displaylist_elem is not None:
            self._check_unknown_elements(displaylist_elem, ["address"])
            displaylist = (displaylist_elem.text, self._get_text(displaylist_elem, "address", convert_int=True))
        else:
            displaylist = None

        if displaylist and geolayout:
            raise ParseError("Cannot specify both <geolayout> and <displaylist>")
        #if not displaylist and not geolayout:
            #raise ParseError("Must specify either <geolayout> or <displaylist>")
        # we can't evoke this if we want unused model ids to still exist, so I think
        # it makes sense to check if a bhv is using it, and only then warn

        group = self._get_text(root, "group")
        level = self._get_text(root, "level")

        if group and level:
            raise ParseError("Cannot specify both <group> and <level>")
        if (displaylist or geolayout) and not group and not level:
            raise ParseError("Must specify either <group> or <level>")

        ids = []
        ids_elem = root.find("ids")
        if ids_elem is not None:
            self._check_unknown_elements(ids_elem, ["id"])
            for id_elem in ids_elem.findall("id"):
                id_level = self._get_attr(id_elem, "level", required=False)
                id_group = self._get_attr(id_elem, "group", required=False)

                # Warnings for redundant level/group assignments
                if id_level and id_level == level:
                    logger.warning(f"<id level='{id_level}'> is the same as <level> '{level}'.")
                if id_group and id_group == group:
                    logger.warning(f"<id group='{id_group}'> is the same as <group> '{group}'.")

                ids.append(
                    ModelId(
                        self._get_attr(id_elem, "value", convert_int=True),
                        self._get_attr(id_elem, "name"),
                        id_level or id_group,
                    )
                )

        tables = self._get_list(root, "animation_tables", "table")

        collisions = []
        collisions_elem = root.find("collisions")
        if collisions_elem is not None:
            self._check_unknown_elements(collisions_elem, ["collision"])
            collision_elements = collisions_elem.findall("collision")
            for c in collision_elements:
                try:
                    collisions.append(self._parse_collision(c, readable_name, len(collision_elements) > 1))
                except Exception as exc:
                    raise ParseError(f"Error while parsing <collision>:\n{exc}") from exc

        return Model(readable_name, geolayout, group, ids, tables, collisions)

    def _parse_model(self, root: ET.Element, file_name: str):
        try:
            return self._parse_model_wrapped(root)
        except Exception as exc:
            try:
                readable_name = self._get_attr(root, "readable_name")
            except Exception:
                readable_name = None
            if readable_name is None:
                raise ParseError(f"Error while parsing model in file {file_name}:\n{exc}")
            raise ParseError(f"Error while parsing model \"{readable_name}\" in file {file_name}:\n{exc}") from exc

    def parse_file(self, file_path: Path) -> Union[AnimationTable, Behavior, Model]:
        filepath_checks(file_path)
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()

            parsers = {
                "animation_table": self._parse_animation_table,
                "behavior": self._parse_behavior,
                "model": self._parse_model,
            }

            if root.tag in parsers:
                return parsers[root.tag](root, file_path.parts[-1])
            raise ParseError(f"Unknown root tag: {root.tag}")
        except ET.ParseError as exc:
            raise ParseError(f"XML Syntax Error: {exc}") from exc


def parse_all() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = SM64XMLParser()
    base_path = Path("fast64_internal/data/sm64")

    files = list(base_path.rglob("*.xml"))
    logger.info(f"Found {len(files)} XML files to parse.")

    success_count = 0
    error_count = 0

    for xml_file in files:
        try:
            parser.parse_file(xml_file)
            # print(parser.parse_file(xml_file), "\n")
            success_count += 1
        except Exception as exc:
            logger.error(f"Parse Error in {xml_file}:\n{exc}\n")
            # traceback.print_exc()
            error_count += 1

    logger.info(f"Parsing complete. Success: {success_count}, Errors: {error_count}")
