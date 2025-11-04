from bpy.props import FloatProperty, BoolProperty, EnumProperty, PointerProperty
from bpy.types import PropertyGroup, UILayout, Object

import bpy

from ...utility import prop_split, set_prop_if_in_data
from ..f3d_material import F3D_MAT_CUR_VERSION

from .operators import CreateDebugMat


class F3D_SharerdCullingProperties(PropertyGroup):
    tab: BoolProperty(name="Culling", default=True)
    enabled: BoolProperty(name="Culling", default=True)
    max_geometric_error: FloatProperty(name="Max Geometric Error", default=1.0, min=0.0)

    def to_dict(self, owner: "F3D_DefaultCullingProperties"):
        data = {}
        data["enabled"] = self.enabled
        if self.enabled:
            data["type"] = owner.type
            if owner.type == "CONVEX":
                data["max_geometric_error"] = self.max_geometric_error
        return data

    def from_dict(self, owner: "F3D_DefaultCullingProperties", data: dict):
        self.enabled = set_prop_if_in_data(self, "enabled", data, "enabled")
        if self.enabled:
            owner.type = set_prop_if_in_data(owner, "type", data, "type")
            if owner.type == "CONVEX":
                self.max_geometric_error = set_prop_if_in_data(self, "max_geometric_error", data, "max_geometric_error")

    def draw_props(self, layout: UILayout, is_new_gbi: bool, owner: "F3D_CullingProperties"):
        col = layout.column()
        split = col.split(factor=0.5)
        split.prop(self, "enabled", invert_checkbox=self.enabled and not is_new_gbi)
        if not self.enabled:
            return

        type_row = split.row()
        type_row.prop(owner, "type", text="")
        type_row.enabled = self.enabled

        properties_col = col.column()
        properties_col.enabled = self.enabled
        if owner.type == "CONVEX":
            prop_split(properties_col, self, "max_geometric_error", "Max Geometric Error")
        elif owner.type == "CUSTOM":
            prop_split(properties_col, owner, "obj", "Cull Mesh")


class F3D_CullingProperties(PropertyGroup):
    edit_default: BoolProperty(name="Edit Default", default=False)
    shared: PointerProperty(type=F3D_SharerdCullingProperties)
    type: EnumProperty(
        name="Type",
        items=[
            ("ROTATED_BB", "Rotated Bounding Box", "Rotated Bounding Box"),
            ("CONVEX", "Convex", "Convex"),
            ("CUSTOM", "Custom", "Custom"),
        ],
        default="CONVEX",
    )

    obj: PointerProperty(
        type=Object, poll=lambda self, obj: obj.type == "MESH" and obj is not getattr(bpy.context, "object", None)
    )

    def to_dict(self):
        if not self.edit_default:
            return {}
        return self.shared.to_dict(self)

    def from_dict(self, data: dict):
        self.shared.from_dict(self, data)

    def draw_props(self, layout: UILayout, default: "F3D_DefaultCullingProperties", is_new_gbi: bool):
        col = layout.column()
        col.prop(self, "edit_default")
        if self.edit_default:
            self.shared.draw_props(layout, is_new_gbi, self)
        else:
            col = col.column()
            col.enabled = False
            default.draw_props(col, is_new_gbi)


class F3D_DefaultCullingProperties(PropertyGroup):
    shared: PointerProperty(type=F3D_SharerdCullingProperties)

    type: EnumProperty(
        name="Type",
        items=[
            ("ROTATED_BB", "Rotated Bounding Box", "Rotated Bounding Box"),
            ("CONVEX", "Convex", "Convex"),
        ],
        default="CONVEX",
    )

    debug_mode: BoolProperty(
        name="Debug Mode", description="Draw points in game, rudementary and only for debugging", default=False
    )
    debug_mat: PointerProperty(
        type=bpy.types.Material, poll=lambda self, mat: mat.is_f3d and mat.mat_ver == F3D_MAT_CUR_VERSION
    )
    cube_size: FloatProperty(name="Cube Size", default=0.05, min=0.0)

    def to_dict(self):
        return self.shared.to_dict(self)

    def from_dict(self, data: dict):
        self.shared.from_dict(self, data)

    def draw_props(self, layout: UILayout, is_new_gbi: bool, show_debug=False):
        col = layout.column()
        self.shared.draw_props(col, is_new_gbi, self)

        if show_debug:
            col.separator()

            col.label(text="Debug, not saved to Repo Settings", icon="PROPERTIES")
            split = col.split(factor=0.5)
            split.prop(self, "debug_mode")
            if self.debug_mode:
                split.prop(self, "cube_size")
                prop_split(col, self, "debug_mat", "Debug Material")
                CreateDebugMat.draw_props(col)


classes = (
    F3D_SharerdCullingProperties,
    F3D_DefaultCullingProperties,
    F3D_CullingProperties,
)


def register_culling_props():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister_culling_props():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
