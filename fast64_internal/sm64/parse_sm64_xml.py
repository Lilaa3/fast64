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
    default: Optional[int]
    enums: list[BehaviorFieldEnum]
    mask: int
    shift: int
    multiplier: int
    offset: int
    min: Optional[int]
    max: Optional[int]


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
    address: int
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
        convert_bool: bool = False,
    ):
        """Retrieves an attribute, optionally converting it to an integer."""
        val = element.get(attr)
        if val is None:
            if required:
                raise ParseError(f"Missing required attribute '{attr}' in <{element.tag}>")
            return None
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

    def _parse_animation_table(self, root: ET.Element) -> AnimationTable:
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
        shift = self._get_attr(root, "shift", convert_int=True, required=False)
        mask = self._get_attr(root, "mask", convert_int=True, required=False)
        multiplier = self._get_attr(root, "multiplier", convert_int=True, required=False) or 1
        offset = self._get_attr(root, "offset", convert_int=True, required=False) or 0
        min_value = self._get_attr(root, "min", convert_int=True, required=False) or 0

        if field_type not in {"int", "float", "bool", "dialogue_id", "units", "frames"}:
            raise ParseError(f"Unsupported field type '{field_type}' in field '{name}'.")

        default = self._get_attr(
            root,
            "default",
            convert_int=(field_type in {"int", "dialogue_id", "units", "frames"}),
            convert_bool=(field_type == "bool"),
            required=False,
        )

        bparams = self._get_attr(root, "bparam")
        bparams = [int(bparam) for bparam in bparams]
        if any(bparam < 1 or bparam > 4 for bparam in bparams):
            raise ParseError(f"Invalid bparam '{bparams}' in field '{name}'. Must be between 1 and 4.")

        max_value = self._get_attr(root, "max", convert_int=True, required=False) or len(bparams) * 255
        enums = []
        enums_elem = root.find("enums")
        if enums_elem is not None:
            self._check_unknown_elements(enums_elem, ["enum"])
            for enum_node in enums_elem.findall("enum"):
                enums.append(self._parse_field_enum(enum_node, field_type == "bool"))

        return BehaviorField(
            name,
            description,
            field_type,
            bparams,
            default,
            enums,
            shift,
            mask,
            multiplier,
            offset,
            min_value,
            max_value,
        )

    def _parse_behavior(self, root: ET.Element) -> Behavior:
        self._check_unknown_elements(
            root, ["tags", "models", "collisions", "description", "comment", "fields", "particle"]
        )

        address = self._get_attr(root, "name", convert_int=True)
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

        return Behavior(address, readable_name, description, comment, tags, models, collisions, fields)

    def _parse_model(self, root: ET.Element) -> Model:
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
        if not displaylist and not geolayout:
            raise ParseError("Must specify either <geolayout> or <displaylist>")

        group = self._get_text(root, "group")
        level = self._get_text(root, "level")

        if group and level:
            raise ParseError("Cannot specify both <group> and <level>")
        if not group and not level:
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
                try:
                    return parsers[root.tag](root)
                except Exception as exc:
                    raise ParseError(f"Error while parsing <{root.tag}>:\n{exc}") from exc

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
