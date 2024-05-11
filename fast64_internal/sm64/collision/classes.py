import dataclasses
from enum import Enum

from ...utility import join_c_args

class SurfaceClass(Enum):
    SURFACE_CLASS_DEFAULT = 0
    SURFACE_CLASS_VERY_SLIPPERY = 1
    SURFACE_CLASS_SLIPPERY = 2
    SURFACE_CLASS_NOT_SLIPPERY = 3
    SURFACE_CLASS_SUPER_SLIPPERY = 4


class WarpsAndLevelTypes(Enum):
    COL_TYPE_LEVEL_DEFAULT = 0
    COL_TYPE_WARP = 1
    COL_TYPE_INSTANT_WARP_0 = 2
    COL_TYPE_INSTANT_WARP_1 = 3
    COL_TYPE_INSTANT_WARP_2 = 4
    COL_TYPE_INSTANT_WARP_3 = 5
    COL_TYPE_LOOK_UP_WARP = 6
    COL_TYPE_TIMER_START = 7
    COL_TYPE_TIMER_END = 8
    COL_TYPE_MUSIC = 9


class SpecialCollisionTypes(Enum):
    COL_TYPE_SPECIAL_DEFAULT = 0
    COL_TYPE_HANGABLE = 1
    COL_TYPE_INTANGIBLE = 2
    COL_TYPE_DEATH_PLANE = 3
    COL_TYPE_BURNING = 4
    COL_TYPE_WATER = 5
    COL_TYPE_WATER_BOTTOM = 6
    COL_TYPE_SLOW = 7
    COL_TYPE_FORCE_AS_SPEED = 8
    COL_TYPE_VERTICAL_WIND = 9
    COL_TYPE_HORIZONTAL_WIND = 10
    COL_TYPE_FLOWING_WATER = 11
    COL_TYPE_QUICKSAND = 12
    COL_TYPE_SHALLOW_QUICKSAND = 13
    COL_TYPE_DEEP_MOVING_QUICKSAND = 14
    COL_TYPE_MOVING_QUICKSAND = 15
    COL_TYPE_SHALLOW_MOVING_QUICKSAND = 16
    COL_TYPE_DEEP_QUICKSAND = 17
    COL_TYPE_INSTANT_QUICKSAND = 18
    COL_TYPE_INSTANT_MOVING_QUICKSAND = 19


class CameraCollisionTypes(Enum):
    COL_FLAG_CAMERA_DEFAULT = 0
    COL_TYPE_NO_CAMERA_COLLISION = 1
    COL_TYPE_CAMERA_WALL = 2
    COL_TYPE_CLOSE_CAMERA = 3
    COL_TYPE_CAMERA_FREE_ROAM = 4
    COL_TYPE_BOSS_FIGHT_CAMERA = 5
    COL_TYPE_CAMERA_8_DIR = 6
    COL_TYPE_CAMERA_MIDDLE = 7
    COL_TYPE_CAMERA_ROTATE_RIGHT = 8
    COL_TYPE_CAMERA_ROTATE_LEFT = 9
    COL_TYPE_CAMERA_BOUNDARY = 10


class ParticlesCollisionTypes(Enum):
    COL_TYPE_PARTICLE_DEFAULT = 0
    COL_TYPE_PARTICLE_SPARKLES = 1
    COL_TYPE_PARTICLE_DUST = 2
    COL_TYPE_PARTICLE_WATER_SPLASH = 3
    COL_TYPE_PARTICLE_WAVE_TRAIL = 4
    COL_TYPE_PARTICLE_FIRE = 5
    COL_TYPE_PARTICLE_SHALLOW_WATER = 6
    COL_TYPE_PARTICLE_LEAF = 7
    COL_TYPE_PARTICLE_SNOW = 8
    COL_TYPE_PARTICLE_BREATH = 9
    COL_TYPE_PARTICLE_DIRT = 10
    COL_TYPE_PARTICLE_TRIANGLE = 11


class SoundTerrain(Enum):
    SOUND_TERRAIN_DEFAULT = 0  # e.g. air
    SOUND_TERRAIN_GRASS = 1
    SOUND_TERRAIN_WATER = 2
    SOUND_TERRAIN_STONE = 3
    SOUND_TERRAIN_SPOOKY = 4  # squeaky floor
    SOUND_TERRAIN_SNOW = 5
    SOUND_TERRAIN_ICE = 6
    SOUND_TERRAIN_SAND = 7


@dataclasses.dataclass
class NewCollisionType:
    non_decal_shadow: bool = False
    vanish: bool = False
    can_get_stuck: bool = False
    warps_and_level: str|int = 0
    special: str|int = 0
    slipperiness: str|int = 0
    camera: str|int = 0
    sound: str|int = 0
    particle: str|int = 0

    def to_c_args(self):
        return join_c_args(
            [
                WarpsAndLevelTypes(self.warps_and_level).name,
                SpecialCollisionTypes(self.special).name,
                SurfaceClass(self.slipperiness).name,
                CameraCollisionTypes(self.camera).name,
                ParticlesCollisionTypes(self.particle).name,
                SoundTerrain(self.sound).name,
                "TRUE" if self.non_decal_shadow else "FALSE",
                "TRUE" if self.vanish else "FALSE",
                "TRUE" if self.can_get_stuck else "FALSE",
            ]
        )

    def to_binary(self):
        data = bytearray()
        data.extend(self.non_decal_shadow.to_bytes(1, "big"))
        data.extend(self.vanish.to_bytes(1, "big"))
        data.extend(self.can_get_stuck.to_bytes(1, "big"))
        data.extend(WarpsAndLevelTypes(self.warps_and_level).value.to_bytes(4, "big"))
        data.extend(SpecialCollisionTypes(self.special).value.to_bytes(5, "big"))
        data.extend(SurfaceClass(self.slipperiness).value.to_bytes(3, "big"))
        data.extend(CameraCollisionTypes(self.camera).value.to_bytes(4, "big"))
        data.extend(ParticlesCollisionTypes(self.particle).value.to_bytes(4, "big"))
        data.extend(SoundTerrain(self.sound).value.to_bytes(4, "big"))
        data.extend(bytearray([0] * 5))
        return data
    

class CollisionTri:
    pass

@dataclasses.dataclass
class CollisionTriSet:
    tris: list[CollisionTri] = dataclasses.field(default_factory=list)
    surface_type: NewCollisionType|None = None

    def to_c(self):
        args = self.surface_type.to_c_args()
        if isinstance(self.surface_type, NewCollisionType):
            return f"COL_TRI_INIT_NEW({args}, {len(self.tris)})"
        return f"COL_TRI_INIT({args}, {self.tris})"