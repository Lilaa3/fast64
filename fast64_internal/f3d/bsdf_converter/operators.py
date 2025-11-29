import copy

import bpy
from bpy.utils import register_class, unregister_class
from bpy.props import EnumProperty, BoolProperty
from bpy.types import Context, Object, Material, Operator, UILayout

from ...utility import PluginError, raisePluginError

from .converter import obj_to_f3d, obj_to_bsdf
from ..f3d_material import is_mat_f3d

converter_enum = [("Object", "Selected Objects", "Object"), ("Scene", "Scene", "Scene"), ("All", "All", "All")]
RECOGNISED_GAMEMODES = ["SM64", "OOT", "MK64"]


def draw_generic_converter_props(owner, layout: UILayout, direction: str, context: Context):
    if direction == "":
        layout.prop(owner, "converter_type")
        layout.prop(owner, "backup")
    if direction == "BSDF":
        layout.prop(owner, "put_alpha_into_color")
    elif direction == "F3D":
        recognised_gamemode = context.scene.gameEditorMode in RECOGNISED_GAMEMODES
        if recognised_gamemode:
            layout.prop(owner, "use_recommended")
        if not owner.use_recommended or not recognised_gamemode:
            layout.prop(owner, "lights_for_colors")
            layout.prop(owner, "default_to_fog")
            layout.prop(owner, "set_rendermode_without_fog")


class F3D_ConvertBSDF(Operator):
    bl_idname = "scene.f3d_convert_to_bsdf"
    bl_label = "BSDF Converter (F3D To BSDF or BSDF To F3D)"
    bl_options = {"REGISTER", "UNDO", "PRESET"}
    icon = "MATERIAL"

    # we store these in the operator itself for user presets!
    direction: EnumProperty(items=[("F3D", "BSDF To F3D", "F3D"), ("BSDF", "F3D To BSDF", "BSDF")], name="Direction")
    converter_type: EnumProperty(items=converter_enum, name="Type")
    backup: BoolProperty(default=True, name="Backup")
    put_alpha_into_color: BoolProperty(default=False, name="Put Alpha Into Color")
    use_recommended: BoolProperty(default=True, name="Use Recommended For Current Gamemode")
    lights_for_colors: BoolProperty(default=False, name="Lights For Colors")
    default_to_fog: BoolProperty(default=False, name="Default To Fog")
    set_rendermode_without_fog: BoolProperty(default=False, name="Set RenderMode Even Without Fog")

    def draw(self, context: Context):
        layout = self.layout.column()
        layout.prop(self, "direction")
        draw_generic_converter_props(self, layout, self.direction, context)

    @classmethod
    def draw_props(cls, layout: UILayout, icon: str = "", text: str | None = None, **op_values):
        icon_name = icon if icon else cls.icon
        op = layout.operator(cls.bl_idname, icon=icon_name, text=text or "")
        for key, value in op_values.items():
            setattr(op, key, value)
        return op

    def execute(self, context: Context):
        try:
            self.execute_operator(context)
            return {"FINISHED"}
        except Exception as exc:
            raisePluginError(self, exc)
            return {"CANCELLED"}

    def execute_operator(self, context: Context):
        collection = context.scene.collection
        view_layer = context.view_layer
        scene = context.scene

        def exclude_non_mesh(objs: list[Object]) -> list[Object]:
            return [obj for obj in objs if obj.type == "MESH" and not obj.library]

        if self.converter_type == "Object":
            objs = exclude_non_mesh(context.selected_objects)
            if not objs:
                raise PluginError("No objects selected to convert.")
        elif self.converter_type == "Scene":
            objs = exclude_non_mesh(scene.objects)
            if not objs:
                raise PluginError("No objects in current scene to convert.")
        elif self.converter_type == "All":
            objs = exclude_non_mesh(bpy.data.objects)
            if not objs:
                raise PluginError("No objects in current file to convert.")

        if self.use_recommended and scene.gameEditorMode in RECOGNISED_GAMEMODES:
            game_mode: str = scene.gameEditorMode
            lights_for_colors = game_mode == "SM64"
            default_to_fog = game_mode != "SM64"
            set_rendermode_without_fog = default_to_fog
        else:
            lights_for_colors, default_to_fog, set_rendermode_without_fog = (
                self.lights_for_colors,
                self.default_to_fog,
                self.set_rendermode_without_fog,
            )
        # Skip objects that already only contain F3D or BSDF materials (depending on direction)
        def _has_f3d_material(o: Object) -> bool:
            for slot in o.material_slots:
                mat = slot.material
                if mat is not None and is_mat_f3d(mat):
                    return True
            return False

        candidates = list(objs)
        if self.direction == "F3D":
            objs = [o for o in objs if not _has_f3d_material(o)]
            skipped = [o for o in candidates if o not in objs]
            if skipped:
                names = ", ".join([s.name for s in skipped[:8]])
                self.report({"INFO"}, f"Skipped {len(skipped)} objects with only F3D materials: {names}{'...' if len(skipped) > 8 else ''}")
            if not objs:
                raise PluginError("No objects with non-F3D materials to convert.")
        else:
            objs = [o for o in objs if _has_f3d_material(o)]
            skipped = [o for o in candidates if o not in objs]
            if skipped:
                names = ", ".join([s.name for s in skipped[:8]])
                self.report({"INFO"}, f"Skipped {len(skipped)} objects without F3D materials: {names}{'...' if len(skipped) > 8 else ''}")
            if not objs:
                raise PluginError("No objects with F3D materials to convert.")
        original_names = [obj.name for obj in objs]
        new_objs: list[Object] = []
        backup_collection = None

        try:
            materials: dict[Material, Material] = {}
            mesh_data_map: dict = {}  # Track copied mesh data to preserve sharing
            converted_something = False
            for old_obj in objs:  # make copies and convert them
                obj = old_obj.copy()
                # Link to same collections as original
                for collection in old_obj.users_collection:
                    collection.objects.link(obj)
                # Only assign and convert mesh data once per shared mesh
                if old_obj.data not in mesh_data_map:
                    mesh_data_map[old_obj.data] = old_obj.data
                    obj.data = mesh_data_map[old_obj.data]
                    if self.direction == "F3D":
                        converted_something |= obj_to_f3d(
                            obj, materials, lights_for_colors, default_to_fog, set_rendermode_without_fog
                        )
                    elif self.direction == "BSDF":
                        converted_something |= obj_to_bsdf(obj, materials, self.put_alpha_into_color)
                else:
                    # Reuse already converted mesh data
                    obj.data = mesh_data_map[old_obj.data]
                new_objs.append(obj)
            if not converted_something:  # nothing converted
                raise PluginError("No materials to convert.")

            bpy.ops.object.select_all(action="DESELECT")
            if self.backup:
                name = "BSDF -> F3D Backup" if self.direction == "F3D" else "F3D -> BSDF Backup"
                if name in bpy.data.collections:
                    backup_collection = bpy.data.collections[name]
                else:
                    backup_collection = bpy.data.collections.new(name)
                    scene.collection.children.link(backup_collection)

            for old_obj, obj, name in zip(objs, new_objs, original_names):
                # Move or remove the original object first so the new copy can
                # take the original name without Blender auto-suffixing it.
                if self.backup:
                    old_obj.name = f"{name}_backup"

                    if backup_collection is not None:
                        backup_collection.objects.link(old_obj)

                    for col in list(old_obj.users_collection):
                        if col is backup_collection:
                            continue
                        col.objects.unlink(old_obj)
                else:
                    try:
                        bpy.data.objects.remove(old_obj)
                    except Exception:
                        for col in list(old_obj.users_collection):
                            col.objects.unlink(old_obj)
                obj.name = name
            if self.backup:
                for layer_collection in view_layer.layer_collection.children:
                    if layer_collection.collection == backup_collection:
                        layer_collection.exclude = True
        except Exception as exc:
            for obj in new_objs:
                bpy.data.objects.remove(obj)
            if backup_collection is not None:
                bpy.data.collections.remove(backup_collection)
            raise exc
        self.report({"INFO"}, "Done.")


classes = (F3D_ConvertBSDF,)


def bsdf_converter_ops_register():
    for cls in classes:
        register_class(cls)


def bsdf_converter_ops_unregister():
    for cls in reversed(classes):
        unregister_class(cls)
