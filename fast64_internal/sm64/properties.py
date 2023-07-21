import enum
import os
import bpy
from bpy.types import PropertyGroup
from bpy.utils import register_class, unregister_class
from bpy.props import (
    StringProperty,
    IntProperty,
    FloatProperty,
    BoolProperty,
    PointerProperty,
    CollectionProperty,
    EnumProperty,
    FloatVectorProperty,
)

from .utility import directory_ui_warnings, draw_error, file_ui_warnings
from ..utility import PluginError, prop_split, toAlnum

from ..render_settings import on_update_render_settings

from .constants import (
    enumRefreshVer,
    enumExportHeaderType,
    enumLevelNames,
    level_enums,
    enumCompressionFormat,
    sm64GoalTypeEnum,
    enumExportType,
    defaultExtendSegment4,
)

from .animation.properties import SM64_AnimExportProps, SM64_AnimImportProps
from .rom_expansion.properties import SM64_ROMExpansionProps
from .geolayout.properties import SM64_ExportGeolayoutProps
from .collision.properties import SM64_CollisionExportProps, SM64_MaterialCollisionProps
from .collision.constants import enumSM64CollisionFormat


class SM64_HeaderType(enum.Enum):
    ACTOR = 0
    LEVEL = 1
    CUSTOM = 2


from_fast64_header_enum = {"Actor": SM64_HeaderType.ACTOR, "Level": SM64_HeaderType.LEVEL, "CUSTOM": SM64_HeaderType.CUSTOM}


class SM64_ExportSettings:
    def __init__(
        self,
        header_type: SM64_HeaderType,
        handle_includes: bool,
        decomp_path: str,
        folder_name: str,
        group_name: str,
        level_name: str,
        custom_path: str,
    ):
        self.header_type = header_type
        self.handle_includes = handle_includes

        self.custom_path = bpy.path.abspath(custom_path)
        self.decomp_path = bpy.path.abspath(decomp_path)

        self.folder_name = toAlnum(folder_name)

        if self.header_type == SM64_HeaderType.ACTOR and not group_name:
            raise PluginError("Actor header type chosen but group name not provided.")
        self.group_name = group_name
        self.level_name = level_name

        self.export_path = self.get_export_path()
        return

    def get_tex_directory(self, tex_directory):
        if self.header_type == SM64_HeaderType.ACTOR:
            return os.path.join("actors/", self.folder_name)
        elif self.header_type == SM64_HeaderType.LEVEL:
            return os.path.join("levels/", self.level_name)
        return tex_directory

    def get_export_path(self):
        if self.header_type == SM64_HeaderType.ACTOR:
            return self.get_actor_directory()
        elif self.header_type == SM64_HeaderType.LEVEL:
            return os.path.join(self.get_level_directory(), self.folder_name)
        elif self.header_type == SM64_HeaderType.CUSTOM:
            return os.path.join(self.custom_path, self.folder_name)

        raise PluginError("Unimplemented Header Type")

    def get_level_directory(self):
        if self.header_type == SM64_HeaderType.LEVEL:
            return os.path.join(self.get_levels_directory(), self.level_name)

    def get_actor_directory(self):
        if self.header_type == SM64_HeaderType.ACTOR:
            return os.path.join(self.get_actors_directory(), self.folder_name)

    def get_actors_directory(self):
        if self.header_type == SM64_HeaderType.ACTOR:
            return os.path.join(self.decomp_path, "actors/")

    def get_levels_directory(self):
        if self.header_type == SM64_HeaderType.LEVEL:
            return os.path.join(self.decomp_path, "levels/")


class SM64_GlobalExportProperties(PropertyGroup):
    from .constants import groupEnum
    folder_name: StringProperty(name="Directory Name", default="mario")
    header_type: EnumProperty(name="Export Type", items=enumExportHeaderType, default="Actor")

    handle_includes: BoolProperty(name="Add Includes", default=True)

    custom_path: StringProperty(name="Directory", subtype="FILE_PATH")

    custom_level_name: StringProperty(name="Level", default="bob")
    level_name: EnumProperty(items=enumLevelNames, name="Level", default="bob")

    group_type: EnumProperty(items=groupEnum, name="Group", default="group0")
    custom_group_name: StringProperty(name="Group", default="group0")

    levels_folder: StringProperty(name="Levels Folder", default="levels")
    actors_folder: StringProperty(name="Actors Folder", default="actors")

    # Binary
    use_bank0: BoolProperty(name="Use Bank 0")
    level_option: EnumProperty(items=level_enums, name="Level", default="HMC")
    insertable_binary_path: StringProperty(name="Filepath", subtype="FILE_PATH")

    def get_export_settings_class(self, sm64_props: "SM64_Properties"):
        return SM64_ExportSettings(
            from_fast64_header_enum[self.header_type],
            self.handle_includes,
            sm64_props.decomp_path,
            self.folder_name,
            self.custom_group_name if self.group_type == "Custom" else self.group_type,
            self.level_name,
            self.custom_path,
        )

    def is_custom_export(self):
        return self.header_type == "Custom"

    def get_level_name(self):
        if self.header_type == "Level":
            if self.level_option == "custom":
                return self.level_option
            return self.custom_level_name
        raise PluginError("Current export type is not a level.")

    def get_export_directory(self):
        name = toAlnum(self.folder_name)

        if self.header_type == "Actor":
            return os.path.join("actors", name)
        elif self.header_type == "Level":
            return os.path.join("levels", toAlnum(self.get_level_name()), name)
        elif self.is_custom_export():
            return bpy.path.abspath(self.custom_path)

        raise PluginError("Unimplemented Export Type")

    def get_path_and_level(self):
        level_name = self.get_level_name() if self.header_type == "Level" else ""
        return self.get_export_path(), level_name

    def get_export_path(self, decomp_path):
        if self.is_custom_export():
            return bpy.path.abspath(self.custom_path)
        return bpy.path.abspath(os.path.join(decomp_path, self.get_export_directory()))

    def write_export_info(self, layout: bpy.types.UILayout):
        if self.header_type == "Custom":
            return

        col = layout.box().column()

        col.label(text="This will write to your decomp path at:")

        try:
            col.label(text=self.get_export_directory())
        except Exception as e:
            draw_error(col, str(e))

    def draw_props(self, layout: bpy.types.UILayout, sm64Props):
        col = layout.column()
        if sm64Props.export_type in ["C", "glTF"]:  # TODO: Add seperate code for gltf
            prop_split(col, self, "header_type", "Export Type")
            if self.header_type == "Custom":
                col.prop(self, "custom_path")
                prop_split(col, self, "folder_name", "Folder Name")
            else:
                if self.header_type == "Actor":
                    prop_split(col, self, "group_type", "Group")
                    if self.group_type == "Custom":
                        prop_split(col, self, "custom_group_name", "Group Name")

                elif self.header_type == "Level":
                    prop_split(col, self, "level_name", "Level")
                    if self.level_name == "custom":
                        prop_split(col, self, "custom_level_name", "Level Name")
                prop_split(col, self, "folder_name", "Folder Name")

            handle_includes_col = col.column()
            handle_includes_col.enabled = self.header_type != "Custom"
            handle_includes_col.prop(self, "handle_includes")

            self.write_export_info(col)

            prop_split(col, self, "levels_folder", "Levels Folder")
            prop_split(col, self, "actors_folder", "Actors Folder")

        elif sm64Props.export_type == "Insertable Binary":
            col.prop(self, "insertable_binary_path")
        elif sm64Props.export_type == "Binary":
            col.prop(self, "use_bank0")
            if not self.use_bank0:
                col.prop(self, "level_option")


class SM64_Properties(PropertyGroup):
    """Global SM64 Scene Properties found under scene.fast64.sm64"""

    version: IntProperty(name="SM64_Properties Version", default=0)
    cur_version = 2  # version after property migration

    # UI Selection
    show_importing_menus: BoolProperty(name="Show Importing Menus", default=False)
    export_type: EnumProperty(items=enumExportType, name="Export Type", default="C")
    goal: EnumProperty(items=sm64GoalTypeEnum, name="Goal", default="All")

    import_rom: StringProperty(name="Import ROM", subtype="FILE_PATH")
    export_rom: StringProperty(name="Export ROM", subtype="FILE_PATH")
    output_rom: StringProperty(name="Output ROM", subtype="FILE_PATH")

    extend_bank_4: BoolProperty(
        name="Extend Bank 4 on Export?",
        default=True,
        description=f"\
Sets bank 4 range to ({hex(defaultExtendSegment4[0])}, {hex(defaultExtendSegment4[1])}) and copies data from old bank",
    )
    convertible_addr: StringProperty(name="Address")
    level_convert: EnumProperty(items=level_enums, name="Level", default="IC")
    refresh_version: EnumProperty(items=enumRefreshVer, name="Refresh", default="Refresh 13")
    disable_scroll: BoolProperty(name="Disable Scrolling Textures")
    set_extended_ram: BoolProperty(name="Set Extended RAM (Recommended)")
    blender_to_sm64_scale: FloatProperty(name="Blender To SM64 Scale", default=100, update=on_update_render_settings)
    decomp_path: StringProperty(name="Decomp Folder", subtype="FILE_PATH")

    compression_format: EnumProperty(items=enumCompressionFormat, name="Compression", default="mio0")

    # HackerSM64
    collision_format: EnumProperty(items=enumSM64CollisionFormat, name="Collision Format", default="SM64")

    anim_import: PointerProperty(type=SM64_AnimImportProps)
    anim_export: PointerProperty(type=SM64_AnimExportProps)
    rom_expansion: PointerProperty(type=SM64_ROMExpansionProps)
    geolayout_export: PointerProperty(type=SM64_ExportGeolayoutProps)
    collision_export: PointerProperty(type=SM64_CollisionExportProps)

    export: PointerProperty(type=SM64_GlobalExportProperties)

    def get_export_settings_class(self):
        return self.export.get_export_settings_class(self)

    def is_binary_export(self):
        return self.export_type in ["Binary", "Insertable Binary"]

    def get_path_and_level(self):
        return self.export.get_path_and_level(self.decomp_path)

    def get_legacy_export_type(self, scene):
        legacy_export_types = ("C", "Binary", "Insertable Binary")

        for exportKey in ["animExportType", "colExportType", "DLExportType", "geoExportType"]:
            eType = scene.pop(exportKey, None)
            if eType is not None and legacy_export_types[eType] != "C":
                return legacy_export_types[eType]

        return "C"

    def upgrade_version_1(self, scene):
        old_scene_properties_to_new = {
            "importRom": "import_rom",
            "exportRom": "export_rom",
            "outputRom": "output_rom",
            "convertibleAddr": "convertible_addr",
            "levelConvert": "level_convert",
            "disableScroll": "disable_scroll",
            "blenderToSM64Scale": "blender_to_sm64_scale",
            "decompPath": "decomp_path",
        }
        for old, new in old_scene_properties_to_new.items():
            setattr(self, new, scene.get(old, getattr(self, new)))

        refresh_version = scene.get("refreshVer", None)
        if refresh_version:
            self.refresh_version = enumRefreshVer[refresh_version][0]
        compression_format = scene.get("compression_format", None)
        if compression_format:
            self.compression_format = enumCompressionFormat[compression_format][0]

        self.version = 2

    def upgrade_version_0(self, scene):
        self.export_type = self.get_legacy_export_type(scene)
        self.version = 1

    @staticmethod
    def upgrade_changed_props():
        for scene in bpy.data.scenes:
            sm64_props: SM64_Properties = scene.fast64.sm64

            if sm64_props.version == 0:
                sm64_props.upgrade_version_0(scene)
            if sm64_props.version == 1:
                sm64_props.upgrade_version_1(scene)

    def draw_props(self, layout: bpy.types.UILayout):
        col = layout.column()
        self.export.draw_props(layout.column().box(), self)

        prop_split(col, self, "goal", "Goal")
        prop_split(col, self, "show_importing_menus", "Show Importing Options")

        prop_split(col, self, "blender_to_sm64_scale", "Blender To SM64 Scale")

        if self.show_importing_menus:
            col.prop(self, "import_rom")
            file_ui_warnings(col, self.import_rom)

        prop_split(col, self, "export_type", "Export type")

        if self.export_type == "Binary":
            col.prop(self, "export_rom")
            file_ui_warnings(col, self.export_rom)
            col.prop(self, "output_rom")
            file_ui_warnings(col, self.output_rom)
            col.prop(self, "extend_bank_4")
            return
        if self.export_type == "Insertable Binary":
            return

        # C and glTF
        col.prop(self, "decomp_path")
        directory_ui_warnings(col, self.decomp_path)

        if self.export_type == "C":
            prop_split(col, self, "refresh_version", "Decomp Func Map")
            prop_split(col, self, "compression_format", "Compression Format")
            col.prop(self, "set_extended_ram")

        col.prop(self, "disable_scroll")
        prop_split(col, self, "collision_format", "Collision Format")


class SM64_MaterialProps(bpy.types.PropertyGroup):
    expandTab: BoolProperty(name="Action Properties", default=True)
    collision: PointerProperty(type=SM64_MaterialCollisionProps)
