import bpy
from bpy.utils import register_class, unregister_class
from bpy.props import (
    BoolProperty,
    StringProperty,
    EnumProperty,
    IntProperty,
    FloatProperty,
    CollectionProperty,
    PointerProperty,
)
from .functions.expand import getROMFilePath, unexpandedROMPathChecks
from .operators import SM64_ExpandROMOperator

from ...utility import isPowerOf2, prop_split


class SM64_ROMExpansionProps(bpy.types.PropertyGroup):
    """Scene SM64 ROM expansion properties found under scene.fast64.sm64.romExpansion"""

    unExpandedROMPath: StringProperty(name="Unexpanded ROM", subtype="FILE_PATH", default="C:/Users/User/Documents/sm64.us.z64")

    overrideOutputPath: BoolProperty(name="Override Output Path")
    customOutputDir: StringProperty(name="Output File Directory", subtype="FILE_PATH", default="C:/Users/User/Documents/")
    customOutputName: StringProperty(name="Output File Name", default="sm64.us.out.z64")

    expandAdvancedTab: BoolProperty(name="Advanced")
    extendedSize: IntProperty(name="Extended Size (MB)", min=16, max=64, default=64)
    MIO0Padding: IntProperty(name="MIO0 Padding", description="Byte boundary to align MIO0 blocks", min=0, default=32)
    MIO0Alignment: IntProperty(
        name="MIO0 Alignment (KB)", description="Padding to insert between MIO0 blocks in KB", min=0, default=1
    )
    fillOldMIO0Blocks: BoolProperty(name="Fill Old MIO0 Blocks", description="Fill old MIO0 blocks with 0x01")
    dumpMIO0Blocks: BoolProperty(
        name="Dump MIO0 Blocks", description='Dump MIO0 blocks to files in "mio0files" directory'
    )

    def drawAdvancedSettings(self, layout: bpy.types.UILayout):
        col = layout.column()
        col.prop(
            self,
            "expandAdvancedTab",
            icon="TRIA_DOWN" if self.expandAdvancedTab else "TRIA_RIGHT",
        )
        if not self.expandAdvancedTab:
            return

        prop_split(col, self, "extendedSize", "Extended Size (MB)")
        prop_split(col, self, "MIO0Padding", "MIO0 Padding")
        prop_split(col, self, "MIO0Alignment", "MIO0 Alignment (KB)")
        if not isPowerOf2(self.MIO0Alignment):
            col.box().label(text="Alignment must be power of 2.", icon="ERROR")
        col.prop(self, "fillOldMIO0Blocks")
        col.prop(self, "dumpMIO0Blocks")

    def drawPaths(self, layout: bpy.types.UILayout):
        col = layout.column()

        try:
            col.prop(self, "unExpandedROMPath")
            unexpandedROMPathChecks(self.unExpandedROMPath) # Will raise exceptions if values are not valid.
            col.prop(self, "overrideOutputPath")
            if self.overrideOutputPath:
                prop_split(col, self, "customOutputDir", "Directory")
                prop_split(col, self, "customOutputName", "Name")
                getROMFilePath(self) # Will raise exceptions if values are not valid.
            else:
                filePath = getROMFilePath(self)
                col.box().label(text=f"{filePath}")
        except Exception as e:
            col.box().label(text=f"ERROR: {e}", icon="ERROR")

    def draw_props(self, layout: bpy.types.UILayout):
        col = layout.column()
        col.box().label(text="Python reimplementation of sm64Extend")

        col.operator(SM64_ExpandROMOperator.bl_idname)

        self.drawPaths(col.box())

        warningBox = col.box().column()
        warningBox.label(text="WARNING: While this tool can expand any SM64 ROM, all fast64")
        warningBox.label(text="importers expect a USA ROM.")

        self.drawAdvancedSettings(col.box())


sm64_expansion_properties = (SM64_ROMExpansionProps,)


def sm64_expansion_properties_register():
    for cls in sm64_expansion_properties:
        register_class(cls)


def sm64_expansion_properties_unregister():
    for cls in reversed(sm64_expansion_properties):
        unregister_class(cls)
