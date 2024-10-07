import bpy
from bpy.utils import register_class, unregister_class

from ... import addon_updater_ops
from ..utility_anim import ArmatureApplyWithMeshOperator
from ..utility import prop_split, multilineLabel

from .f3d_material import mat_register, mat_unregister
from .f3d_render_engine import render_engine_register, render_engine_unregister
from .f3d_writer import f3d_writer_register, f3d_writer_unregister
from .f3d_parser import f3d_parser_register, f3d_parser_unregister
from .flipbook import flipbook_register, flipbook_unregister
from .op_largetexture import op_largetexture_register, op_largetexture_unregister, ui_oplargetexture
from .bsdf_converter import bsdf_converter_register, bsdf_converter_unregister, bsdf_converter_panel_draw


class F3D_GlobalSettingsPanel(bpy.types.Panel):
    bl_idname = "F3D_PT_global_settings"
    bl_label = "F3D Global Settings"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Fast64"

    @classmethod
    def poll(cls, context):
        return True

    # called every frame
    def draw(self, context):
        col = self.layout.column()
        col.scale_y = 1.1  # extra padding
        prop_split(col, context.scene, "f3d_type", "F3D Microcode")
        col.prop(context.scene, "saveTextures")
        col.prop(context.scene, "f3d_simple", text="Simple Material UI")
        col.prop(context.scene, "exportInlineF3D", text="Bleed and Inline Material Exports")
        if context.scene.exportInlineF3D:
            multilineLabel(
                col.box(),
                "While inlining, all meshes will be restored to world default values.\n         You can configure these values in the world properties tab.",
                icon="INFO",
            )
        col.prop(context.scene, "ignoreTextureRestrictions")
        if context.scene.ignoreTextureRestrictions:
            col.box().label(text="Width/height must be < 1024. Must be png format.")


class Fast64_GlobalToolsPanel(bpy.types.Panel):
    bl_idname = "FAST64_PT_global_tools"
    bl_label = "Fast64 Tools"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Fast64"

    @classmethod
    def poll(cls, context):
        return True

    # called every frame
    def draw(self, context):
        # TODO: figure out why a circular import is happening, this is bad
        from ..f3d_material_converter import (
            mat_updater_draw,
        )

        col = self.layout.column()
        col.operator(ArmatureApplyWithMeshOperator.bl_idname)
        # col.operator(CreateMetarig.bl_idname)
        ui_oplargetexture(col, context)
        col.separator()

        box = col.box().column()
        box.label(text="Material Updater")
        mat_updater_draw(box, context)
        col.separator()

        box = col.box().column()
        box.label(text="BSDF Converter")
        bsdf_converter_panel_draw(box, context)
        col.separator()

        addon_updater_ops.update_notice_box_ui(self, context)


classes = tuple()
panel_classes = (F3D_GlobalSettingsPanel, Fast64_GlobalToolsPanel)


def f3d_panel_register():
    for cls in panel_classes:
        register_class(cls)


def f3d_panel_unregister():
    for cls in reversed(panel_classes):
        unregister_class(cls)


def f3d_register(register_panels: bool):
    from ..f3d_material_converter import mat_updater_register

    for cls in classes:
        register_class(cls)
    mat_register()
    render_engine_register()
    mat_updater_register()
    f3d_writer_register()
    flipbook_register()
    f3d_parser_register()
    op_largetexture_register()
    bsdf_converter_register()

    if register_panels:
        f3d_panel_register()


def f3d_unregister(unregister_panels):
    from ..f3d_material_converter import mat_updater_unregister

    for cls in reversed(classes):
        unregister_class(cls)
    bsdf_converter_unregister()
    op_largetexture_unregister()
    f3d_parser_unregister()
    flipbook_unregister()
    f3d_writer_unregister()
    mat_updater_unregister()
    render_engine_unregister()
    mat_unregister()

    if unregister_panels:
        f3d_panel_unregister()
