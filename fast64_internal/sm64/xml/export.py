from pathlib import Path
import xml.etree.ElementTree as ET
from typing import Optional

from .classes import AnimationTable, Behavior, BehaviorField, Collision, Model
from .parser import apply_mul_offset


def _add_sub_element(parent: ET.Element, tag: str, text: Optional[str] = None, **attrs):
    cleaned_attrs = {k: str(v) for k, v in attrs.items() if v is not None}
    elem = ET.SubElement(parent, tag, cleaned_attrs)
    if text is not None:
        elem.text = str(text)
    return elem


def _format_hex(val: Optional[int], padding: int = 0):
    if val is None:
        return None
    if padding:
        return f"0x{val:0{padding}X}"
    return f"0x{val:X}"


def _format_num(val: int | float):
    return str(int(val)) if isinstance(val, float) and val.is_integer() else str(val)


def generate_animation_table(table: AnimationTable):
    attrs = {
        "address": _format_hex(table.address_or_name.address, padding=8),
        "readable_name": table.readable_name,
    }
    if table.dma:
        attrs["dma"] = "true"
    if table.size is not None:
        attrs["size"] = table.size
    if table.ignore_bone_count:
        attrs["ignore_bone_count"] = "true"
    if table.directory:
        attrs["directory"] = table.directory

    root = ET.Element("animation_table", {k: str(v) for k, v in attrs.items() if v is not None})
    names_elem = ET.SubElement(root, "names")
    for name in table.names:
        _add_sub_element(names_elem, "name", text=name)

    return root


def generate_model(model: Model):
    root = ET.Element("model", {"readable_name": model.readable_name})

    if model.description:
        _add_sub_element(root, "description", text=model.description)
    if model.dev_comment:
        _add_sub_element(root, "comment", text=model.dev_comment)

    if model.geolayout:
        _add_sub_element(
            root, "geolayout", address=_format_hex(model.geolayout.address, padding=8), name=model.geolayout.c_name
        )
    elif model.displaylist:
        _add_sub_element(
            root,
            "displaylist",
            address=_format_hex(model.displaylist.address, padding=8),
            name=model.displaylist.c_name,
        )

    if model.group is not None:
        _add_sub_element(root, "group", text=model.group)
    if model.level is not None:
        _add_sub_element(root, "level", text=model.level)

    if model.ids:
        ids_elem = ET.SubElement(root, "ids")
        for mid in model.ids:
            _add_sub_element(
                ids_elem,
                "id",
                value=_format_hex(mid.address_or_name.address, padding=2),
                name=mid.address_or_name.c_name,
                level=mid.level,
                group=mid.group,
            )

    if model.tables:
        tables_elem = ET.SubElement(root, "animation_tables")
        for t in model.tables:
            _add_sub_element(tables_elem, "table", text=t)

    _append_collisions(root, model.collisions, model.readable_name)
    return root


def generate_behavior(behavior: Behavior):
    attrs = {}
    if isinstance(behavior.name_or_address, int):
        attrs["address"] = _format_hex(behavior.name_or_address, padding=8)
    else:
        attrs["name"] = behavior.name_or_address

    attrs["readable_name"] = behavior.readable_name

    root = ET.Element("behavior", {k: str(v) for k, v in attrs.items() if v is not None})

    if behavior.description:
        _add_sub_element(root, "description", text=behavior.description)
    if behavior.dev_comment:
        _add_sub_element(root, "comment", text=behavior.dev_comment)
    if behavior.particle:
        _add_sub_element(root, "particle", text=behavior.particle)

    if behavior.tags:
        tags_elem = ET.SubElement(root, "tags")
        for tag in behavior.tags:
            _add_sub_element(tags_elem, "tag", text=tag)

    if behavior.fields:
        fields_elem = ET.SubElement(root, "fields")
        for f in behavior.fields:
            fields_elem.append(generate_field(f))

    if behavior.models:
        models_elem = ET.SubElement(root, "models")
        for m in behavior.models:
            _add_sub_element(models_elem, "model", text=m)

    _append_collisions(root, behavior.collisions, behavior.readable_name)
    return root


def _append_collisions(parent: ET.Element, collisions: list[Collision], base_name: str):
    if not collisions:
        return
    more_than_one = len(collisions) > 1
    col_elem = ET.SubElement(parent, "collisions")

    for c in collisions:
        name = c.address_or_name.c_name
        implicit_name = name

        if more_than_one and name:
            split_name = name.split("_collision_")
            if len(split_name) == 2:
                implicit_name = f"{base_name} {split_name[1].replace('_', ' ').title()}"
            else:
                implicit_name = f"{base_name} {name}"

        attrs = {"c_name": name, "address": _format_hex(c.address_or_name.address, padding=8)}
        if c.readable_name != implicit_name:
            attrs["readable_name"] = c.readable_name

        _add_sub_element(col_elem, "collision", **attrs)


def generate_field(field: BehaviorField):
    attrs = {
        "name": field.name,
        "type": field.type,
        "bparam": "".join(str(b) for b in field.bparam),
    }

    if field.default is not None:
        if field.type == "bool":
            attrs["default"] = "TRUE" if field.default else "FALSE"
        else:
            if isinstance(field.default, float):
                attrs["default"] = _format_num(field.default)
            else:
                attrs["default"] = _format_hex(field.default)

    if field.shift != 0:
        attrs["shift"] = str(field.shift)
    if field.multiplier != 1:
        attrs["multiplier"] = _format_num(field.multiplier)
    if field.offset != 0:
        attrs["offset"] = _format_num(field.offset)

    param_bit_width = len(field.bparam) * 8
    default_mask = ((1 << param_bit_width) - 1) >> field.shift

    if field.enums:
        max_enum = max(enum.value or i for i, enum in enumerate(field.enums))
        bits = max(0, max_enum.bit_length())
        calc_mask = (1 << bits) - 1
        if field.mask != calc_mask:
            attrs["mask"] = _format_hex(field.mask)
    else:
        if field.type != "bool" and field.mask != default_mask:
            attrs["mask"] = _format_hex(field.mask)

    max_raw_val = field.mask
    default_min = apply_mul_offset(0, field.offset, field.multiplier)
    default_max = apply_mul_offset(max_raw_val, field.offset, field.multiplier)

    if field.min != default_min:
        attrs["min"] = _format_num(field.min)
    if field.max != default_max:
        attrs["max"] = _format_num(field.max)

    field_elem = ET.Element("field", attrs)

    if field.description:
        _add_sub_element(field_elem, "description", text=field.description)

    if field.enums:
        enums_elem = ET.SubElement(field_elem, "enums")
        for enum_obj in field.enums:
            enum_attrs = {}
            if field.type != "bool":
                enum_attrs["name"] = enum_obj.name
                enum_attrs["value"] = str(enum_obj.value)
            if enum_obj.c_name is not None:
                enum_attrs["c_name"] = enum_obj.c_name

            en_elem = _add_sub_element(enums_elem, "enum", **enum_attrs)

            if enum_obj.description:
                _add_sub_element(en_elem, "description", text=enum_obj.description)

    return field_elem


def to_xml_file(path: Path, obj: Model | AnimationTable | Behavior):
    if isinstance(obj, AnimationTable):
        root = generate_animation_table(obj)
    elif isinstance(obj, Model):
        root = generate_model(obj)
    elif isinstance(obj, Behavior):
        root = generate_behavior(obj)
    else:
        raise ValueError(f"Unknown object type: {type(obj)}")

    if hasattr(ET, "indent"):
        ET.indent(root, space="    ", level=0)

    tree = ET.ElementTree(root)
    return tree.write(path / f"{obj.file_name}", encoding="utf-8", xml_declaration=True)


def model_to_xml_file(path: Path, model: Model):
    to_xml_file(path / "models", model)


def animation_table_to_xml_file(path: Path, table: AnimationTable):
    to_xml_file(path / "animation_tables", table)


def behavior_to_xml_file(path: Path, behavior: Behavior):
    to_xml_file(path / "behaviors", behavior)
