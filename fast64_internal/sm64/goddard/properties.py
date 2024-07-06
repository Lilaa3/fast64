from functools import cache
import os
import bpy
from bpy.types import PropertyGroup, UILayout, Scene, Context
from bpy.props import BoolProperty, StringProperty, EnumProperty, IntProperty, FloatProperty, PointerProperty
from bpy.path import abspath
from bpy.utils import register_class, unregister_class

from ...utility import path_ui_warnings, directory_ui_warnings, filepath_ui_warnings, prop_split

from .constants import goddard_import_enum, goddard_import_addresses, MARIO_HEAD_DYNLIST_NAME
from .operators import SM64_ImportDynList


def get_import_file_enum_cached(directory_path):
    last_modification = os.stat(directory_path).st_mtime if os.path.exists(directory_path) else None
    cache_key = (directory_path, last_modification)
    if get_import_file_enum_cached.cache[0] == cache_key:
        return get_import_file_enum_cached.cache[1]
    try:
        files = frozenset(os.listdir(directory_path))
        files = sorted(files)
        if MARIO_HEAD_DYNLIST_NAME in files:
            files.remove(MARIO_HEAD_DYNLIST_NAME)
            files.insert(0, MARIO_HEAD_DYNLIST_NAME)
        result = [(f, f.rstrip(".c"), f) for f in files]
    except OSError:
        result = [("!", "No Files", "", "ERROR", 0)]
    get_import_file_enum_cached.cache = (cache_key, result)
    return result


get_import_file_enum_cached.cache = (None, [])


def get_import_file_enum(self, context: Context):
    directory_path = self.get_path(context.scene.fast64.sm64.decomp_path)
    return get_import_file_enum_cached(directory_path)


class SM64_GoddardImportingProperties(PropertyGroup):
    """Global SM64 Goddard Importing properties found under scene.fast64.sm64.goddard.importing"""

    import_type: EnumProperty(items=goddard_import_enum, name="Import Type", default="C")

    # C
    mario_head: BoolProperty(name="Import Mario Head", default=True)
    use_custom_path: BoolProperty(name="Use Custom Path", default=False)
    custom_path: StringProperty(name="File Path", subtype="FILE_PATH")
    file: EnumProperty(items=get_import_file_enum, name="Files")

    address: EnumProperty(
        items=goddard_import_addresses,
        name="Preset Addresses",
    )

    @property
    def abs_custom_path(self):
        return abspath(self.custom_path)

    def get_path(self, decomp_path: str):
        if not self.use_custom_path or self.mario_head:
            return os.path.join(abspath(decomp_path), "src/goddard/dynlists/")
        else:
            return self.abs_custom_path

    def get_file_path(self, decomp_path: str):
        if self.mario_head:
            return os.path.join(self.get_path(decomp_path), MARIO_HEAD_DYNLIST_NAME)
        return os.path.join(self.get_path(decomp_path), self.file)

    def draw_c(self, layout: UILayout, decomp_path: str):
        decomp_warning_args = (
            decomp_path,
            "Empty decomp folder",
            "Decomp folder does not exist.",
            "Decomp path is not a folder.",
        )
        col = layout.column()
        col.prop(self, "mario_head")
        if self.mario_head:
            if not directory_ui_warnings(col, *decomp_warning_args):
                return False
            return filepath_ui_warnings(
                col,
                os.path.join(self.get_path(decomp_path), MARIO_HEAD_DYNLIST_NAME),
                doesnt_exist=f"{MARIO_HEAD_DYNLIST_NAME} doesn't exist",
            )

        row = col.row()
        left, right = row.column(), row.column()
        left.alignment = "LEFT"
        right.alignment = "EXPAND"
        left.prop(self, "use_custom_path")
        if self.use_custom_path:
            right.prop(self, "custom_path", text="")
            if not directory_ui_warnings(col, self.abs_custom_path):
                return False
        elif not directory_ui_warnings(right, *decomp_warning_args):
            right.scale_y = 0.7
            return False
        else:
            right.scale_y = 0.5
            text_box = right.column().box()
            text_box.label(text=self.get_path(decomp_path))
        col.prop(self, "file", text="")
        return True

    def draw_props(self, layout: UILayout, decomp_path: str):
        col = layout.column()
        import_col = layout.column()
        prop_split(col, self, "import_type", "Import Type")
        if self.import_type == "C":
            import_col.enabled = self.draw_c(col, decomp_path)
        elif self.import_type == "Binary":
            prop_split(import_col, self, "address", "Address")
        SM64_ImportDynList.draw_props(import_col)


class SM64_GoddardProperties(PropertyGroup):
    """Global SM64 Goddard properties found under scene.fast64.sm64.goddard"""

    importing: PointerProperty(type=SM64_GoddardImportingProperties)

    def draw_props(self, layout: UILayout, decomp_path: str):
        col = layout.column()
        col.label(text="Test")


class SM64_DynListProperties(PropertyGroup):
    """Object properties found under object.fast64.sm64.goddard.dynlist"""

    use_integer_names: BoolProperty(
        name="Use Integer Names",
        default=False,
        description="UseIntegerNames(TRUE)\nUse integers instead of strings, off by default but enabled in Mario's master dynlist",
    )

    def draw_props(self, layout: UILayout):
        col = layout.column()
        col.prop(self, "use_integer_names")


classes = (SM64_GoddardImportingProperties, SM64_GoddardProperties, SM64_DynListProperties)


def goddard_props_register():
    for cls in classes:
        register_class(cls)


def goddard_props_unregister():
    for cls in reversed(classes):
        unregister_class(cls)
