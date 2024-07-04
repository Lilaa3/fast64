from functools import cache
from dataclasses import dataclass, field
from enum import Enum
from typing import TypeVar

from ..sm64_utility import int_from_str

DynObjName = str | int  # depends on UseIntegerNames
DynUnion = object | str | int
T = TypeVar("T")


@dataclass(unsafe_hash=True)
class UserEnum:
    name: str
    value: int


class DynListEnum(Enum):
    pass


bit_flag = lambda bit: 2**bit


class ObjTypeFlag(DynListEnum):
    OBJ_TYPE_GROUPS = bit_flag(0)
    OBJ_TYPE_BONES = bit_flag(1)
    OBJ_TYPE_JOINTS = bit_flag(2)
    OBJ_TYPE_PARTICLES = bit_flag(3)
    OBJ_TYPE_SHAPES = bit_flag(4)
    OBJ_TYPE_NETS = bit_flag(5)
    OBJ_TYPE_PLANES = bit_flag(6)
    OBJ_TYPE_FACES = bit_flag(7)
    OBJ_TYPE_VERTICES = bit_flag(8)
    OBJ_TYPE_CAMERAS = bit_flag(9)
    # 0x400 was not used
    OBJ_TYPE_MATERIALS = bit_flag(11)
    OBJ_TYPE_WEIGHTS = bit_flag(12)
    OBJ_TYPE_GADGETS = bit_flag(13)
    OBJ_TYPE_VIEWS = bit_flag(14)
    OBJ_TYPE_LABELS = bit_flag(15)
    OBJ_TYPE_ANIMATORS = bit_flag(16)
    OBJ_TYPE_VALPTRS = bit_flag(17)
    # 0x40000 was not used
    OBJ_TYPE_LIGHTS = bit_flag(19)
    OBJ_TYPE_ZONES = bit_flag(20)
    OBJ_TYPE_UNK200000 = bit_flag(21)
    OBJ_TYPE_ALL = 0x00FFFFFF


class ObjDrawingFlags(DynListEnum):
    OBJ_DRAW_UNK01 = bit_flag(0)
    OBJ_INVISIBLE = bit_flag(1)
    OBJ_PICKED = bit_flag(2)
    OBJ_IS_GRABBABLE = bit_flag(3)
    OBJ_HIGHLIGHTED = bit_flag(4)


class DParmF(DynListEnum):
    PARM_F_ALPHA = 1
    PARM_F_RANGE_MIN = 2
    PARM_F_RANGE_MAX = 3
    PARM_F_VARVAL = 6


class DObjTypes(DynListEnum):
    D_CAR_DYNAMICS = 0
    D_NET = 1
    D_JOINT = 2
    D_ANOTHER_JOINT = 3
    D_CAMERA = 4
    D_VERTEX = 5
    D_FACE = 6
    D_PLANE = 7
    D_BONE = 8
    D_MATERIAL = 9
    D_SHAPE = 10
    D_GADGET = 11
    D_LABEL = 12
    D_VIEW = 13
    D_ANIMATOR = 14
    D_DATA_GRP = 15
    D_PARTICLE = 16
    D_LIGHT = 17
    D_GROUP = 18


class DParmPtr(DynListEnum):
    PARM_PTR_OBJ_VTX = 1
    PARM_PTR_CHAR = 5


class ValPtrType(DynListEnum):
    OBJ_VALUE_INT = 1
    OBJ_VALUE_FLOAT = 2


@dataclass
class GdVec3f:
    x: float = 0
    y: float = 0
    z: float = 0


@dataclass
class GdBoundingBox:
    minX: float = 0
    minY: float = 0
    minZ: float = 0
    maxX: float = 0
    maxY: float = 0
    maxZ: float = 0


@dataclass
class GdTriangleF:
    p0: GdVec3f
    p1: GdVec3f
    p2: GdVec3f


@dataclass
class GdAnimTransform:
    scale: GdVec3f
    rotate: GdVec3f
    pos: GdVec3f


@dataclass
class GdColour:
    r: float = 0
    g: float = 0
    b: float = 0


@dataclass
class ObjShape:  # TODO
    pass


@dataclass
class GdObj:  # TODO
    name: DynObjName = 0
    type: ObjTypeFlag = 0


@dataclass
class ObjGroup(GdObj):
    type: ObjTypeFlag = ObjTypeFlag.OBJ_TYPE_GROUPS
    members: list[GdObj] = field(default_factory=list)


class ObjAnimator(GdObj):  # TODO
    animatedPartsGrp: ObjGroup = field(default_factory=ObjGroup)
    animdataGrp: ObjGroup = field(default_factory=ObjGroup)


# struct DynList {
#    s32 cmd;
#    union DynUnion w1;
#    union DynUnion w2;
#    struct GdVec3f vec;
# };
@dataclass
class DynListCmd:
    cmd: int = field(init=False)

    @classmethod
    def arg_count(cls):
        return len(cls.arg_fields())

    @classmethod
    @cache
    def arg_fields(cls):
        return [field for field in cls.__dataclass_fields__.values() if "var" in field.metadata]

    def get_var(self, var: str) -> DynUnion:
        for key, field in self.__dataclass_fields__.items():
            if field.metadata.get("var", None) == var:
                return getattr(self, key)
        return 0

    def bytes_from_var(self, var: str) -> bytes:
        value = self.get_var(var)
        if isinstance(value, int):
            return value.to_bytes(4, "big", signed=True)
        elif isinstance(value, float):
            return struct.pack(">f", value)
        return b""

    def to_bytes(self) -> bytes:
        data = bytearray()
        data.extend(self.cmd.to_bytes(4, "big", signed=True))
        data.extend(self.bytes_from_var("w1"))
        data.extend(self.bytes_from_var("w2"))
        data.extend(self.bytes_from_var("vec.x"))
        data.extend(self.bytes_from_var("vec.y"))
        data.extend(self.bytes_from_var("vec.z"))
        return data


@dataclass
class BeginList(DynListCmd):
    cmd = 53716


@dataclass
class EndList(DynListCmd):
    cmd = 58


@dataclass
class UseIntegerNames(DynListCmd):  # d_use_integer_names
    cmd = 0

    enable: bool = field(default=False, metadata={"var": "w2"})


@dataclass
class SetInitialPosition(DynListCmd):  # d_set_init_pos
    cmd = 1

    x: float = field(default=0.0, metadata={"var": "vec.x"})
    y: float = field(default=0.0, metadata={"var": "vec.y"})
    z: float = field(default=0.0, metadata={"var": "vec.z"})


@dataclass
class SetRelativePosition(DynListCmd):  # d_set_rel_pos
    cmd = 2

    x: float = field(default=0.0, metadata={"var": "vec.x"})
    y: float = field(default=0.0, metadata={"var": "vec.y"})
    z: float = field(default=0.0, metadata={"var": "vec.z"})


@dataclass
class SetWorldPosition(DynListCmd):  # d_set_world_pos
    cmd = 3

    x: float = field(default=0.0, metadata={"var": "vec.x"})
    y: float = field(default=0.0, metadata={"var": "vec.y"})
    z: float = field(default=0.0, metadata={"var": "vec.z"})


@dataclass
class SetNormal(DynListCmd):  # d_set_normal
    cmd = 4

    x: float = field(default=0.0, metadata={"var": "vec.x"})
    y: float = field(default=0.0, metadata={"var": "vec.y"})
    z: float = field(default=0.0, metadata={"var": "vec.z"})


@dataclass
class SetScale(DynListCmd):  # d_set_scale
    cmd = 5

    x: float = field(default=0.0, metadata={"var": "vec.x"})
    y: float = field(default=0.0, metadata={"var": "vec.y"})
    z: float = field(default=0.0, metadata={"var": "vec.z"})


@dataclass
class SetRotation(DynListCmd):  # d_set_rotation
    cmd = 6

    x: float = field(default=0.0, metadata={"var": "vec.x"})
    y: float = field(default=0.0, metadata={"var": "vec.y"})
    z: float = field(default=0.0, metadata={"var": "vec.z"})


@dataclass
class SetDrawFlag(DynListCmd):  # d_set_obj_draw_flag
    cmd = 7

    flags: ObjDrawingFlags = field(default=0, metadata={"var": "w2"})


@dataclass
class SetFlag(DynListCmd):  # d_set_flags
    cmd = 8

    flags: int = field(default=0, metadata={"var": "w2"})  # TODO: What is this?


@dataclass
class ClearFlag(DynListCmd):  # d_clear_flags
    cmd = 9

    flags: int = field(default=0, metadata={"var": "w2"})  # TODO: What is this?


@dataclass
class SetFriction(DynListCmd):  # d_friction
    cmd = 10

    x: float = field(default=0.0, metadata={"var": "vec.x"})
    y: float = field(default=0.0, metadata={"var": "vec.y"})
    z: float = field(default=0.0, metadata={"var": "vec.z"})


@dataclass
class SetSpring(DynListCmd):  # d_set_spring
    cmd = 11

    x: float = field(default=0.0, metadata={"var": "vec.x"})
    y: float = field(default=0.0, metadata={"var": "vec.y"})
    z: float = field(default=0.0, metadata={"var": "vec.z"})


@dataclass
class CallList(DynListCmd):  # proc_dynlist
    cmd = 12

    dyn_list: list[DynListCmd] = field(default_factory=list, metadata={"var": "w1"})


@dataclass
class SetColourNum(DynListCmd):  # d_set_colour_num
    cmd = 13

    colour_num: int = field(default=0, metadata={"var": "w2"})


# No 14th command.


@dataclass
class MakeDynObj(DynListCmd):  # d_makeobj
    cmd = 15

    type: DObjTypes = field(default=0, metadata={"var": "w2"})
    name: DynObjName = field(default=None, metadata={"var": "w1"})


@dataclass
class StartGroup(DynListCmd):  # d_start_group
    cmd = 16

    name: DynObjName = field(default=None, metadata={"var": "w1"})


@dataclass
class EndGroup(DynListCmd):  # d_end_group
    cmd = 17

    name: DynObjName = field(default=None, metadata={"var": "w1"})


@dataclass
class AddToGroup(DynListCmd):  # d_addto_group
    cmd = 18

    name: DynObjName = field(default=None, metadata={"var": "w1"})


@dataclass
class SetType(DynListCmd):  # d_set_type, actually sets object specific type field, like netType or debugPrint
    cmd = 19

    type: int = field(default=0, metadata={"var": "w2"})


@dataclass
class SetMaterialGroup(DynListCmd):  # d_set_matgroup
    cmd = 20

    name: DynObjName = field(default=None, metadata={"var": "w1"})


@dataclass
class SetNodeGroup(DynListCmd):  # d_set_nodegroup
    cmd = 21

    name: DynObjName = field(default=None, metadata={"var": "w1"})


@dataclass
class SetSkinShape(DynListCmd):  # d_set_skinshape
    cmd = 22

    name: DynObjName = field(default=None, metadata={"var": "w1"})


@dataclass
class SetPlaneGroup(DynListCmd):  # d_set_planegroup
    cmd = 23

    name: DynObjName = field(default=None, metadata={"var": "w1"})


@dataclass
class SetShapePtrPtr(DynListCmd):  # d_set_shapeptrptr
    cmd = 24

    obj_shape: ObjShape = field(default=ObjShape(), metadata={"var": "w1", "is_dptr": True})


@dataclass
class SetShapePtr(DynListCmd):  # d_set_shapeptr
    cmd = 25

    name: DynObjName = field(default=None, metadata={"var": "w1"})


@dataclass
class SetShapeOffset(DynListCmd):  # d_set_shape_offset
    cmd = 26

    x: float = field(default=0.0, metadata={"var": "vec.x"})
    y: float = field(default=0.0, metadata={"var": "vec.y"})
    z: float = field(default=0.0, metadata={"var": "vec.z"})


@dataclass
class SetCenterOfGravity(DynListCmd):  # d_center_of_gravity
    cmd = 27

    x: float = field(default=0.0, metadata={"var": "vec.x"})
    y: float = field(default=0.0, metadata={"var": "vec.y"})
    z: float = field(default=0.0, metadata={"var": "vec.z"})


@dataclass
class LinkWith(DynListCmd):  # d_link_with
    cmd = 28

    name: DynObjName = field(default=None, metadata={"var": "w1"})


@dataclass
class LinkWithPtr(DynListCmd):  # d_link_with_ptr
    cmd = 29

    ptr: object = field(default=object, metadata={"var": "w1"})


@dataclass
class UseObj(DynListCmd):  # d_use_obj
    cmd = 30

    name: DynObjName = field(default=None, metadata={"var": "w1"})


@dataclass
class SetControlType(DynListCmd):  # d_set_control_type
    cmd = 31

    ctrl_type: ObjTypeFlag = field(default=0, metadata={"var": "w2"})


@dataclass
class SetSkinWeight(DynListCmd):  # d_set_skin_weight
    cmd = 32

    vtxNum: int = field(default=0, metadata={"var": "w2"})  # TODO: d_set_skin_weight calls it ID
    weight: float = field(default=0.0, metadata={"var": "vec.x"})  #  0.0 to 100.0


@dataclass
class SetAmbient(DynListCmd):  # d_set_ambient
    cmd = 33

    r: float = field(default=0.0, metadata={"var": "vec.x"})
    g: float = field(default=0.0, metadata={"var": "vec.y"})
    b: float = field(default=0.0, metadata={"var": "vec.z"})


@dataclass
class SetDiffuse(DynListCmd):  # d_set_diffuse
    cmd = 34

    r: float = field(default=0.0, metadata={"var": "vec.x"})
    g: float = field(default=0.0, metadata={"var": "vec.y"})
    b: float = field(default=0.0, metadata={"var": "vec.z"})


@dataclass
class SetId(DynListCmd):  # d_set_id
    cmd = 35

    id: int = field(default=0, metadata={"var": "w2"})


@dataclass
class SetMaterial(DynListCmd):  # d_set_material
    cmd = 36

    id: int = field(default=0, metadata={"var": "w2"})


@dataclass
class MapMaterials(DynListCmd):  # d_map_materials
    cmd = 37

    name: DynObjName = field(default=None, metadata={"var": "w1"})


@dataclass
class MapVertices(DynListCmd):  # d_map_vertices
    cmd = 38

    name: DynObjName = field(default=None, metadata={"var": "w1"})


@dataclass
class Attach(DynListCmd):  # d_attach
    cmd = 39

    name: DynObjName = field(default=None, metadata={"var": "w1"})


@dataclass
class AttachTo(DynListCmd):  # d_attachto_dynid
    cmd = 40

    flags: int = field(default=0, metadata={"var": "w2"})  # if equals 9 some logic is run
    name: DynObjName = field(default=None, metadata={"var": "w1"})


@dataclass
class SetAttachOffset(DynListCmd):  # d_set_att_offset
    cmd = 41

    x: float = field(default=0.0, metadata={"var": "vec.x"})
    y: float = field(default=0.0, metadata={"var": "vec.y"})
    z: float = field(default=0.0, metadata={"var": "vec.z"})


@dataclass
class SetNameSuffix(DynListCmd):  # d_set_name_suffix
    cmd = 43

    suffix: str = field(default="", metadata={"var": "w1"})


@dataclass
class SetParamF(DynListCmd):  # d_set_parm_f
    cmd = 44

    param: DParmF = field(default=0, metadata={"var": "w2"})
    value: float = field(default=0.0, metadata={"var": "vec.x"})


@dataclass
class SetParamPtr(DynListCmd):  # d_set_parm_ptr
    cmd = 45

    param: DParmPtr = field(default=0, metadata={"var": "w2"})
    value: int | str = field(default=0, metadata={"var": "w1"})  # TODO: when param is PARM_PTR_OBJ_VTX it's an index


@dataclass
class MakeNetWithSubGroup(DynListCmd):
    cmd = 46

    name: DynObjName = field(default=None, metadata={"var": "w1"})


@dataclass
class MakeAttachedJoint(DynListCmd):
    cmd = 47

    name: DynObjName = field(default=None, metadata={"var": "w2"})


@dataclass
class EndNetWithSubGroup(DynListCmd):  # d_end_net_with_subgroup
    cmd = 48

    name: DynObjName = field(default=None, metadata={"var": "w1"})


@dataclass
class MakeVertex(DynListCmd):  # d_make_vertex
    cmd = 49

    x: float = field(default=0.0, metadata={"var": "vec.x"})
    y: float = field(default=0.0, metadata={"var": "vec.y"})
    z: float = field(default=0.0, metadata={"var": "vec.z"})


@dataclass
class MakeValPtr(DynListCmd):  # d_add_valptr
    # If `vflags` is 0x40000, then `name` is the name of an object, and `offset`
    # is an offset to a field in that object. Otherwise, `offset` specifies a
    # the address of a standalone variable.
    cmd = 50

    id: DynObjName = field(default=None, metadata={"var": "w1"})
    vflags: int = field(default=0, metadata={"var": "vec.y"})
    type: ValPtrType = field(default=0, metadata={"var": "w2"})
    offset: int = field(default=0, metadata={"var": "vec.x"})


@dataclass
class UseTexture(DynListCmd):  # d_use_texture
    cmd = 52

    texture: object = field(default=object(), metadata={"var": "w2"})


@dataclass
class SetTextureST(DynListCmd):  # d_set_texture_st
    cmd = 53

    s: float = field(default=0.0, metadata={"var": "vec.x"})
    t: float = field(default=0.0, metadata={"var": "vec.y"})


@dataclass
class MakeNetFromShape(DynListCmd):  # d_make_netfromshapeid
    cmd = 54

    shape: DynObjName = field(default=None, metadata={"var": "w1"})


@dataclass
class MakeNetFromShapePtrPtr(DynListCmd):  # d_make_netfromshape_ptrptr
    cmd = 55

    shapes: ObjShape = field(default=ObjShape(), metadata={"var": "w1", "is_dptr": True})


dynlist_cmds_by_name = {cls.__name__: cls for cls in DynListCmd.__subclasses__()}
dynlist_cmds_by_num = {cls.cmd: cls for cls in DynListCmd.__subclasses__()}
enum_to_value = {e.name: e for cls in DynListEnum.__subclasses__() for e in cls}


@dataclass
class DynContext:
    lists: dict[str | int, DynListCmd] = field(default_factory=dict)
    shapes: dict[str | int, ObjShape] = field(default_factory=dict)
    objs: dict[str | int, GdObj] = field(default_factory=dict)
    use_integer_names: bool = False
    cur_obj: GdObj = field(default_factory=GdObj)
    enums: dict[str, int] = field(default_factory=dict)

    def int_or_enum(self, arg: str):
        if arg in self.enums:
            return self.enums[arg]
        if arg in enum_to_value:
            return enum_to_value[arg]
        return int_from_str(arg)
