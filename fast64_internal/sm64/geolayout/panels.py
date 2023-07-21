import bpy
from bpy.types import Panel, Armature, Mesh
from bpy.utils import register_class, unregister_class
from ...utility import PluginError, prop_split, obj_scale_is_unified
from ..panels import SM64_Panel
from ..utility import box_sm64_panel
from .operators import drawLayerWarningBox

class SM64_GeolayoutBonePanel(Panel):
    bl_label = "Geolayout Inspector"
    bl_idname = "BONE_PT_SM64_Geolayout_Inspector"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "bone"
    bl_options = {"HIDE_HEADER"}

    @classmethod
    def poll(cls, context):
        return context.scene.gameEditorMode == "SM64"

    def draw(self, context):
        col = box_sm64_panel(self.layout).column()

        col.box().label(text="Geolayout Inspector")

        if context.mode == "POSE":
            context.bone.fast64.sm64.draw_props(col, context)
        else:
            col.box().label(text="Edit geolayout properties in Pose mode.")


class SM64_GeolayoutArmaturePanel(Panel):
    bl_label = "Geolayout Armature Inspector"
    bl_idname = "OBJECT_PT_SM64_Armature_Geolayout_Inspector"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "object"
    bl_options = {"HIDE_HEADER"}

    @classmethod
    def poll(cls, context):
        return (
            context.scene.gameEditorMode == "SM64"
            and context.object is not None
            and isinstance(context.object.data, Armature)
        )

    def draw(self, context):
        col = box_sm64_panel(self.layout).column()
        col.box().label(text="SM64 Geolayout (Armature) Inspector")

        context.object.fast64.sm64.draw_armature_props(col, context.object)


class SM64_GeolayoutObjectPanel(Panel):
    bl_label = "Object Geolayout Inspector"
    bl_idname = "OBJECT_PT_SM64_Object_Geolayout_Inspector"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "object"
    bl_options = {"HIDE_HEADER"}

    @classmethod
    def poll(cls, context):
        return (
            context.scene.gameEditorMode == "SM64"
            and context.object is not None
            and isinstance(context.object.data, Mesh)
        )

    def draw(self, context):
        obj = context.object
        col = self.layout.column().box()
        col.box().label(text="Object Geolayout Inspector")

        prop_split(col, obj, "geo_cmd_static", "Geolayout Command")
        drawLayerWarningBox(col, obj, "draw_layer_static")

        obj.fast64.sm64.draw_armature_props(col, context.object)
        if obj_scale_is_unified(obj) and len(obj.modifiers) == 0:
            col.prop(obj, "scaleFromGeolayout")

        col.prop(obj, "ignore_render")
        col.prop(obj, "ignore_collision")
        col.prop(obj, "use_f3d_culling")
        # prop_split(col, obj, 'room_num', 'Room')


class SM64_ExportGeolayoutPanel(SM64_Panel):
    bl_idname = "SM64_PT_export_geolayout"
    bl_label = "Geolayout Exporter"
    goal = "Object/Actor/Anim"

    # called every frame
    def draw(self, context):
        scene = context.scene
        scene.fast64.sm64.geolayout_export.draw_props(box_sm64_panel(self.layout), scene)


sm64_bone_panel_classes = (
    SM64_GeolayoutBonePanel,
    SM64_GeolayoutObjectPanel,
    SM64_GeolayoutArmaturePanel,
    SM64_ExportGeolayoutPanel,
)


def sm64_geolayout_panel_register():
    for cls in sm64_bone_panel_classes:
        register_class(cls)


def sm64_geolayout_panel_unregister():
    for cls in sm64_bone_panel_classes:
        unregister_class(cls)
