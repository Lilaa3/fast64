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


class AnimationTable:
    def __init__(self, address: int, name: str, dma: Optional[str], directory: Optional[str], names: list[str]):
        self.address = address
        self.name = name
        self.dma = dma
        self.directory = directory
        self.names = names


class Behavior:
    def __init__(
        self,
        address: int,
        readable_name: str,
        description: str,
        tags: list[str],
        models: list[str],
        collisions: list["Collision"],
    ):
        self.address = address
        self.readable_name = readable_name
        self.tags = tags
        self.models = models
        self.collisions = collisions


class ModelId:
    def __init__(self, value: int, name: str, level: Optional[str]):
        self.value = value
        self.name = name
        self.level = level


class Collision:
    def __init__(self, name: str, address: int, readable_name: str):
        self.c_name = name
        self.address = address
        self.readable_name = readable_name


class Model:
    def __init__(
        self,
        readable_name: str,
        geolayout: Optional[str],
        group: Optional[str],
        ids: list[ModelId],
        tables: list[str],
        collisions: list[str],
    ):
        self.readable_name = readable_name
        self.geolayout = geolayout
        self.group = group
        self.ids = ids
        self.tables = tables
        self.collisions = collisions


class SM64XMLParser:
    def _get_attr(self, element: ET.Element, attr: str, required: bool = True, convert_int: bool = False):
        """Retrieves an attribute, optionally converting it to an integer."""
        val = element.get(attr)
        if val is None:
            if required:
                raise ParseError(f"Missing required attribute '{attr}' in <{element.tag}>")
            return None
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
        self._check_unknown_elements(root, ["names"])

        address = self._get_attr(root, "address", convert_int=True)
        name = self._get_attr(root, "name")
        dma = self._get_attr(root, "dma", required=False)
        directory = self._get_attr(root, "directory", required=False)

        names = self._get_list(root, "names", "name")
        if not names:
            raise ParseError("Missing or empty <names> section in <animation_table>")

        return AnimationTable(address, name, dma, directory, names)

    def _parse_behavior(self, root: ET.Element) -> Behavior:
        self._check_unknown_elements(root, ["tags", "models", "collisions", "description"])

        name = self._get_attr(root, "name", convert_int=True)
        description = self._get_attr(root, "description", required=False) or ""
        readable_name = self._get_attr(root, "readable_name")

        tags = self._get_list(root, "tags", "tag")
        models = self._get_list(root, "models", "model")

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

        return Behavior(name, readable_name, description, tags, models, collisions)

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
            success_count += 1
        except Exception as exc:
            logger.error(f"Parse Error in {xml_file}:\n{exc}")
            # traceback.print_exc()
            error_count += 1

    logger.info(f"Parsing complete. Success: {success_count}, Errors: {error_count}")
