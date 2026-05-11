import dataclasses
from typing import Optional


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
    default: Optional[int | str] = None
    enums: list[BehaviorFieldEnum] = dataclasses.field(default_factory=list)
    mask: int = 0
    shift: int = 0
    multiplier: int = 1
    offset: int = 0
    min: int = 0
    max: int = 0


@dataclasses.dataclass(frozen=True)
class AddressOrCName:
    address: int
    c_name: str


@dataclasses.dataclass(frozen=True)
class AnimationTable:
    file_name: str
    address_or_name: AddressOrCName
    readable_name: str
    dma: bool
    size: Optional[int]
    ignore_bone_count: bool
    directory: Optional[str]
    names: list[str]


@dataclasses.dataclass(frozen=True)
class Collision:
    address_or_name: AddressOrCName
    readable_name: str


@dataclasses.dataclass(frozen=True)
class ModelId:
    address_or_name: AddressOrCName
    level: Optional[str]
    group: Optional[str]


@dataclasses.dataclass
class Model:
    file_name: str
    readable_name: str
    description: str
    dev_comment: str
    geolayout: Optional[AddressOrCName]
    group: Optional[str]
    ids: list[ModelId]
    tables: list[str]
    collisions: Optional[AddressOrCName]
    real_tables: dict[str, AnimationTable] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class Behavior:
    file_name: str
    name_or_address: int | str
    readable_name: str
    description: str
    dev_comment: str
    tags: list[str]
    models: list[str]
    collisions: list[Collision]
    fields: list[BehaviorField]
    real_models: dict[str, Model] = dataclasses.field(default_factory=dict)
