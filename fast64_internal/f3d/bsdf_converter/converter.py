from bpy.types import Object

import dataclasses


@dataclasses.dataclass
class SimpleN64Texture:
    name: str


@dataclasses.dataclass
class SimpleN64Material:
    name: str


def obj_to_f3d(obj: Object):
    print(f"Converting BSDF materials in {obj.name}")

def obj_to_bsdf(obj: Object):
    print(f"Converting F3D materials in {obj.name}")