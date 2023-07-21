import bpy
from bpy.types import PropertyGroup
from bpy.utils import register_class, unregister_class
from bpy.props import (
    StringProperty,
)
from ..utility import prop_split

class SM64_AddressRange(PropertyGroup):
    start_address: StringProperty(name="Start", default="11D8930")
    end_address: StringProperty(name="End", default="11FFF00")

    def draw_props(self, layout: bpy.types.UILayout):
        col = layout.column()
        prop_split(col, self, "start_address", "Start Address")
        prop_split(col, self, "end_address", "End Address")
