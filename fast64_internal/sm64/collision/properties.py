import bpy
from bpy.utils import register_class, unregister_class
from bpy.types import PropertyGroup, UILayout
from bpy.props import (
    BoolProperty,
    StringProperty,
    EnumProperty,
    IntProperty,
    FloatProperty,
    CollectionProperty,
    PointerProperty,
)

from ...utility import intToHex, prop_split
from ..sm64_constants import MAX_U8, MIN_S16, MAX_S16, MIN_U8

from .operators import SM64_SearchCollisionEnum, SM64_ExportCollision
from .constants import (
    NewCollisionTypePreset,
    enumSM64CollisionFormat,
    enumCollisionWarpsAndLevel,
    enumCollisionSpecial,
    enumQuicksandCollision,
    enumCollisionSlipperiness,
    enumCollisionCamera,
    enumCollisionParticle,
    enumCollisionSound,
    enumCollisionType,
    enumCollisionTypeSimple,
    enumCollisionTypeOptions,
    newCollisionPresets,
    vanillaSoundToParticle,
    sTerrainSounds,
    enumCollisionForceBased,
)


def vanilla_to_hackersm64(self, context):
    area_object = context.object.parent
    terrain_enum = None
    while True:
        if area_object is None:
            break
        elif area_object.type == "EMPTY" and area_object.sm64_obj_type == "Area Root":
            if area_object.terrainEnum == "Custom":
                terrain_enum = area_object.terrain_type
            else:
                terrain_enum = area_object.terrainEnum
            break
        area_object = area_object.parent

    hackersm64 = context.material.fast64.sm64.collision.hackersm64

    vanilla_enum = self.get_enum()
    preset = newCollisionPresets.get(vanilla_enum, NewCollisionTypePreset)
    hackersm64.non_decal_shadow = preset.non_decal_shadow
    hackersm64.vanish = preset.vanish
    hackersm64.warps_and_level = preset.warps_and_level
    hackersm64.special = preset.special
    hackersm64.no_camera_collision = preset.no_camera_collision
    hackersm64.camera = preset.camera
    hackersm64.instant_warp_num = preset.instant_warp_num
    hackersm64.quicksand_type = preset.quicksand_type

    hackersm64.sound = sTerrainSounds.get(terrain_enum, "TERRAIN_GRASS").get(preset.sound_type, "SOUND_TERRAIN_DEFAULT")
    hackersm64.particle = vanillaSoundToParticle.get(preset.particle, "COL_TYPE_PARTICLE_DEFAULT")

    if preset.can_get_stuck is not None:
        hackersm64.can_get_stuck = preset.can_get_stuck
    elif terrain_enum == "TERRAIN_SNOW":
        hackersm64.can_get_stuck = True
    else:
        hackersm64.can_get_stuck = False

    if preset.slipperiness is not None:
        hackersm64.slipperiness = preset.slipperiness
    elif terrain_enum == "TERRAIN_SLIDE":
        hackersm64.slipperiness = "SURFACE_CLASS_VERY_SLIPPERY"
    else:
        hackersm64.slipperiness = "SURFACE_CLASS_DEFAULT"


class SM64_HackerSM64CollisionType(PropertyGroup):
    non_decal_shadow: BoolProperty(name="Don’t Render Shadow as Decal")
    vanish: BoolProperty(name="Vanish Cap Surface")
    can_get_stuck: BoolProperty(name="Can Get Stuck")

    warps_and_level: EnumProperty(
        name="Level Properties", items=enumCollisionWarpsAndLevel, default="COL_TYPE_LEVEL_DEFAULT"
    )
    warps_and_level_custom: StringProperty(name="Value", default="COL_TYPE_LEVEL_DEFAULT")

    special: EnumProperty(
        name="Special Physics",
        items=enumCollisionSpecial,
        default="COL_TYPE_SPECIAL_DEFAULT",
    )
    special_custom: StringProperty(name="Value", default="COL_TYPE_SPECIAL_DEFAULT")

    slipperiness: EnumProperty(name="Slipperiness", items=enumCollisionSlipperiness, default="SURFACE_CLASS_DEFAULT")
    slipperiness_custom: StringProperty(name="Value", default="SURFACE_CLASS_DEFAULT")

    no_camera_collision: BoolProperty(name="No Camera Collision", default=False)

    camera: EnumProperty(name="Camera Mode", items=enumCollisionCamera, default="COL_TYPE_CAMERA_DEFAULT")
    camera_custom: StringProperty(name="Value", default="COL_TYPE_CAMERA_DEFAULT")

    particle: EnumProperty(name="Footstep Particle", items=enumCollisionParticle, default="COL_TYPE_PARTICLE_DEFAULT")
    particle_custom: StringProperty(name="Value", default="COL_TYPE_PARTICLE_DEFAULT")

    sound: EnumProperty(name="Footstep Sound", items=enumCollisionSound, default="SOUND_TERRAIN_DEFAULT")
    sound_custom: StringProperty(name="Value", default="SOUND_TERRAIN_DEFAULT")

    instant_warp_num: IntProperty(name="Instant Warp Number", min=0, max=255)
    warp_id: StringProperty(name="Warp ID", default="0x00")
    speed: IntProperty(name="Speed", default=45, min=MIN_S16, max=MAX_S16)
    push_force: IntProperty(name="Speed", default=0, min=MIN_U8, max=MAX_U8)
    angle: FloatProperty(name="Angle", default=0.0, step=(360.0 / MAX_U8 * 100.0))
    quicksand_type: EnumProperty(name="Quicksand Variation", items=enumQuicksandCollision, default="NORMAL")

    def get_generated_force(self) -> int | None:
        if self.warps_and_level in ["COL_TYPE_WARP", "COL_TYPE_FORCE_INSTANT_WARP"]:
            return int(self.warp_id, 0)

        if self.special in ["COL_TYPE_HORIZONTAL_WIND", "COL_TYPE_FLOWING_WATER", "MOVING_QUICKSAND"]:
            unsigned_result = (self.angle % 360) * (360 / 2**8)
            if self.special in ["COL_TYPE_FLOWING_WATER", "MOVING_QUICKSAND"]:
                unsigned_result |= self.push_force << 8
            return int.from_bytes(int.to_bytes(unsigned_result, 2, "big"), "big", signed=True)
        elif self.special in ["COL_TYPE_FORCE_AS_SPEED"]:
            return self.speed

    def draw_enum_or_custom(self, layout: UILayout, propName: str, text: str):
        col = layout.column()
        if getattr(self, propName) == "CUSTOM":
            col = col.box().column()
            prop_split(col, self, propName, text)
            col.prop(self, f"{propName}_custom")
        else:
            prop_split(col, self, propName, text)

    specialTypesWithForceProps = [
        "QUICKSAND",
        "MOVING_QUICKSAND",
        "COL_TYPE_FORCE_AS_SPEED",
        "COL_TYPE_FLOWING_WATER",
        "MOVING_QUICKSAND",
        "COL_TYPE_HORIZONTAL_WIND",
    ]

    def drawSpecial(self, layout: UILayout):
        col = layout.column()

        self.draw_enum_or_custom(col, "special", "Special Physics")
        if self.special in ["QUICKSAND", "MOVING_QUICKSAND"]:
            prop_split(col, self, "quicksand_type", "Quicksand Variation")

        if self.special in ["COL_TYPE_FORCE_AS_SPEED"]:
            prop_split(col, self, "speed", "Speed")
        if self.special in ["COL_TYPE_FLOWING_WATER", "MOVING_QUICKSAND"]:
            prop_split(col, self, "push_force", "Push Force")
        if self.special in ["COL_TYPE_HORIZONTAL_WIND", "COL_TYPE_FLOWING_WATER", "MOVING_QUICKSAND"]:
            prop_split(col, self, "angle", "Angle (Degrees)")

    def drawWarpsAndLevel(self, layout: UILayout):
        col = layout.column()
        self.draw_enum_or_custom(col, "warps_and_level", "Level Properties")
        if self.warps_and_level == "INSTANT_WARP":
            col.prop(self, "instant_warp_num")
            if self.instant_warp_num > 3:
                col.box().label(text="HackerSM64 only has 4 instant warp types by default.", icon="ERROR")
        elif self.warps_and_level in ["COL_TYPE_WARP", "COL_TYPE_FORCE_INSTANT_WARP"]:
            col.prop(self, "warp_id")
            if not self.warp_id:
                col.box().label(text="Empty field.", icon="ERROR")
            try:
                int(self.warp_id, 16)
            except:
                col.box().label(text="Invalid value.", icon="ERROR")

    def draw_props(self, layout: UILayout):
        col = layout.column()

        physics_box = col.box().column()
        self.draw_enum_or_custom(physics_box, "slipperiness", "Slipperiness")
        physics_box.prop(self, "can_get_stuck")

        special_box = col.box().column()
        self.drawSpecial(special_box)
        self.drawWarpsAndLevel(special_box)
        special_box.prop(self, "vanish")

        if self.warps_and_level in enumCollisionForceBased and self.special in enumCollisionForceBased:
            warning_box = col.box().column()
            warning_box.label(text="Both level and special properties are using force.", icon="ERROR")
            warning_box.label(text="Only level´s automatic parameter will be used.")

        footstep_box = col.box().column()
        self.draw_enum_or_custom(footstep_box, "particle", "Footstep Particle")
        self.draw_enum_or_custom(footstep_box, "sound", "Footstep Sound")
        footstep_box.prop(self, "non_decal_shadow")

        camera_box = col.box().column()
        self.draw_enum_or_custom(camera_box, "camera", "Camera Mode")
        camera_box.prop(self, "no_camera_collision")


class SM64_VanillaCollisionType(bpy.types.PropertyGroup):
    options: EnumProperty(
        name="Collision Option", items=enumCollisionTypeOptions, default="SIMPLE", update=vanilla_to_hackersm64
    )
    type: EnumProperty(
        name="Collision Type", items=enumCollisionType, default="SURFACE_DEFAULT", update=vanilla_to_hackersm64
    )
    simple_type: EnumProperty(
        name="Collision Type", items=enumCollisionTypeSimple, default="SURFACE_DEFAULT", update=vanilla_to_hackersm64
    )
    custom: StringProperty(name="Collision Value", default="SURFACE_DEFAULT", update=vanilla_to_hackersm64)

    def get_enum(self):
        if self.options == "ALL":
            return self.type
        elif self.options == "SIMPLE":
            return self.simple_type
        elif self.options == "CUSTOM":
            return self.custom

    def draw_props(self, layout: UILayout):
        split = layout.split()

        prop_split(split, self, "options", "Options")

        if self.options == "ALL":
            SM64_SearchCollisionEnum.draw_props(split, self, "type", "Collision Type")
        elif self.options == "SIMPLE":
            prop_split(split, self, "simple_type", "Collision Type")
        elif self.options == "CUSTOM":
            prop_split(split, self, "custom", "Collision Type")


class SM64_MaterialCollisionProps(bpy.types.PropertyGroup):
    material_menu_tab: BoolProperty(name="SM64 Collision Inspector", default=True)

    hasCollision: BoolProperty(name="Has Collision", default=True)

    vanilla: PointerProperty(type=SM64_VanillaCollisionType, name="Vanilla Collision Type")
    hackersm64: PointerProperty(type=SM64_HackerSM64CollisionType, name="New Collision Type")

    set_force: BoolProperty(name="Set Parameter (Force)")
    force: StringProperty(name="Parameter")

    def get_generated_force(self, collision_format: str):
        if collision_format == "SM64":
            return
        elif collision_format == "HackerSM64":
            return self.hackersm64.get_generated_force()

    def draw_props(self, layout: UILayout, collision_format: str):
        layout.box().prop(self, "hasCollision")
        col = layout.column()
        col.enabled = self.hasCollision

        if collision_format == "SM64":
            self.vanilla.draw_props(col)
        elif collision_format == "HackerSM64":
            self.hackersm64.draw_props(col)

        generated_force = self.get_generated_force(collision_format)

        if generated_force is None:
            box = col.box().column()
            box.prop(self, "set_force")
            col = box.column()
            col.enabled = self.set_force
            prop_split(col, self, "force", "Parameter")


class SM64_CollisionProps(bpy.types.PropertyGroup):
    format: EnumProperty(
        name="Collision Format",
        items=enumSM64CollisionFormat
    )
    start_address: StringProperty(name="Start Address", default=intToHex(0x11D8930))
    end_address: StringProperty(name="End Address", default=intToHex(0x11FFF00))
    set_addr_0x2A: BoolProperty(name="Overwrite 0x2A Behaviour Command")
    addr_0x2A: StringProperty(name="0x2A Behaviour Command Address", default=intToHex(0x21A9CC))
    col_include_children: BoolProperty(name="Include child objects", default=True)
    col_export_rooms: BoolProperty(name="Export Rooms", default=False)

    def draw_props(self, layout: bpy.types.UILayout, export_type: str):
        col = layout.column()
        prop_split(col, self, "format", "Format")
        col.operator(SM64_ExportCollision.bl_idname)
        col.prop(self, "col_include_children")

        if export_type == "C":
            col.prop(self, "col_export_rooms")
        else:
            prop_split(col, self, "start_address", "Start Address")
            prop_split(col, self, "end_address", "End Address")
            col.prop(self, "set_addr_0x2A")
            if self.set_addr_0x2A:
                prop_split(col, self, "addr_0x2A", "0x2A Behaviour Command Address")


properties = [
    SM64_HackerSM64CollisionType,
    SM64_VanillaCollisionType,
    SM64_MaterialCollisionProps,
    SM64_CollisionProps,
]


def properties_register():
    for cls in properties:
        register_class(cls)


def properties_unregister():
    for cls in reversed(properties):
        unregister_class(cls)
