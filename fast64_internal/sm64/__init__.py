import bpy
from bpy.types import Operator, PropertyGroup, Scene
from bpy.props import BoolProperty, StringProperty, EnumProperty, IntProperty, FloatProperty, PointerProperty
from bpy.utils import register_class, unregister_class
from bpy.path import abspath

from .common_properties import SM64_AddressRange
from .properties import SM64_GlobalExportProperties, SM64_MaterialProps, SM64_Properties
from .operators import SM64_AddBoneGroups, SM64_AddWaterBox, SM64_AddrConv, SM64_CreateMetarig, SM64_CreateSimpleLevel
from .panels import SM64_AddressConvertPanel, SM64_GeneralSettingsPanel, SM64_ImportantPanel

from .sm64_level_parser import parseLevelAtPointer
from .constants import level_pointers

from ..utility import (
    prop_split,
    decodeSegmentedAddr,
    encodeSegmentedAddr,
    raisePluginError,
)

from .utility import box_sm64_panel, checkExpanded

from .collision.sm64_collision import (
    sm64_col_register,
    sm64_col_unregister,
)

from .sm64_camera import (
    sm64_cam_panel_register,
    sm64_cam_panel_unregister,
    sm64_cam_register,
    sm64_cam_unregister,
)

from .sm64_objects import (
    sm64_obj_panel_register,
    sm64_obj_panel_unregister,
    sm64_obj_register,
    sm64_obj_unregister,
)

from .geolayout.sm64_geolayout_parser import (
    sm64_geo_parser_panel_register,
    sm64_geo_parser_panel_unregister,
    sm64_geo_parser_register,
    sm64_geo_parser_unregister,
)

from .sm64_level_writer import (
    sm64_level_panel_register,
    sm64_level_panel_unregister,
    sm64_level_register,
    sm64_level_unregister,
)

from .sm64_spline import (
    sm64_spline_panel_register,
    sm64_spline_panel_unregister,
    sm64_spline_register,
    sm64_spline_unregister,
)

from .sm64_f3d_parser import (
    sm64_dl_parser_panel_register,
    sm64_dl_parser_panel_unregister,
    sm64_dl_parser_register,
    sm64_dl_parser_unregister,
)

from .sm64_f3d_writer import (
    sm64_dl_writer_panel_register,
    sm64_dl_writer_panel_unregister,
    sm64_dl_writer_register,
    sm64_dl_writer_unregister,
)

from .animation import sm64_anim_register, sm64_anim_unregister
from .animation.panels import sm64_anim_panel_register, sm64_anim_panel_unregister

from .geolayout import sm64_geolayout_register, sm64_geolayout_unregister
from .geolayout.panels import sm64_geolayout_panel_register, sm64_geolayout_panel_unregister

from .rom_expansion import sm64_expansion_register, sm64_expansion_unregister
from .rom_expansion.panels import sm64_expansion_panel_register, sm64_expansion_panel_unregister

from .collision import sm64_collision_register, sm64_collision_unregister
from .collision.panels import sm64_collision_panel_register, sm64_collision_panel_unregister


sm64_operators = [
    SM64_AddrConv,
    SM64_CreateSimpleLevel,
    SM64_AddBoneGroups,
    SM64_CreateMetarig,
    SM64_AddWaterBox,
]

sm64_common_propeties = [ # Properties used by other properties
    SM64_AddressRange
]

sm64_propeties = [
    SM64_GlobalExportProperties,
    SM64_MaterialProps,
    SM64_Properties,
]

sm64_panel_classes = (
    SM64_ImportantPanel,
    SM64_GeneralSettingsPanel,
    SM64_AddressConvertPanel
)


def sm64_panel_register():
    for cls in sm64_panel_classes:
        register_class(cls)

    sm64_cam_panel_register()
    sm64_geo_parser_panel_register()
    sm64_level_panel_register()
    sm64_spline_panel_register()
    sm64_dl_writer_panel_register()
    sm64_dl_parser_panel_register()
    sm64_geolayout_panel_register()
    sm64_obj_panel_register()
    sm64_collision_panel_register()
    sm64_anim_panel_register()
    sm64_expansion_panel_register()

def sm64_panel_unregister():
    for cls in sm64_panel_classes:
        unregister_class(cls)

    sm64_cam_panel_unregister()
    sm64_geo_parser_panel_unregister()
    sm64_level_panel_unregister()
    sm64_spline_panel_unregister()
    sm64_dl_writer_panel_unregister()
    sm64_dl_parser_panel_unregister()
    sm64_geolayout_panel_unregister()
    sm64_obj_panel_unregister()
    sm64_collision_panel_unregister()
    sm64_anim_panel_unregister()
    sm64_expansion_panel_unregister()


def sm64_register(registerPanels):
    for cls in sm64_common_propeties:
        register_class(cls)

    sm64_col_register()  # register first, so panel goes above mat panel
    sm64_cam_register()
    sm64_geo_parser_register()
    sm64_level_register()
    sm64_spline_register()
    sm64_dl_writer_register()
    sm64_dl_parser_register()
    sm64_anim_register()
    sm64_geolayout_register()
    sm64_obj_register()
    sm64_collision_register()
    sm64_expansion_register()

    if registerPanels:
        sm64_panel_register()
    
    for cls in sm64_operators:
        register_class(cls)
    for cls in sm64_propeties:
        register_class(cls)


def sm64_unregister(unregisterPanels):
    sm64_col_unregister()  # register first, so panel goes above mat panel
    sm64_cam_unregister()
    sm64_geo_parser_unregister()
    sm64_level_unregister()
    sm64_spline_unregister()
    sm64_dl_writer_unregister()
    sm64_dl_parser_unregister()
    sm64_anim_unregister()
    sm64_geolayout_unregister()
    sm64_obj_unregister()
    sm64_collision_unregister()
    sm64_expansion_unregister()

    if unregisterPanels:
        sm64_panel_unregister()

    for cls in reversed(sm64_operators):
        unregister_class(cls)
    for cls in reversed(sm64_common_propeties):
        unregister_class(cls)
    for cls in reversed(sm64_propeties):
        unregister_class(cls)
