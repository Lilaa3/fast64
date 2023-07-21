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

from .operators import (
    SM64_SearchMarioAnimEnum,
    SM64_ImportAllMarioAnims,
    SM64_ImportAnim,
    SM64_ExportAnim,
    SM64_ExportAnimTable,
    SM64_TableOperations,
    SM64_AnimVariantOperations,
    SM64_PreviewAnimOperator,
)
from .constants import (
    enumAnimExportTypes,
    enumAnimImportTypes,
    enumAnimBinaryImportTypes,
    marioAnimationNames,
)
from ..constants import (
    MAX_U16,
    MIN_S16,
    MAX_S16,
)
from .utility import (
    getAnimName,
    getAnimFileName,
    getAnimEnum,
    getMaxFrame,
    getSelectedAction,
)
from ...utility_anim import getFrameInterval
from ...utility import (
    PluginError,
    copyPropToProp,
    prop_split,
)

from ..constants import (
    level_enums,
    enumLevelNames,
)


class SM64_HeaderOverwrites(bpy.types.PropertyGroup):
    expandTab: BoolProperty(name="Overwrites")
    overwrite0x28: BoolProperty(name="Overwrite 0x28 behaviour command", default=True)
    setListIndex: BoolProperty(name="Set List Entry", default=True)
    addr0x27: StringProperty(name="0x27 Command Address", default=hex(2215168))
    addr0x28: StringProperty(name="0x28 Command Address", default=hex(2215176))
    listIndexExport: IntProperty(name="Anim List Index", min=0, max=255)

    def draw_props(self, layout: bpy.types.UILayout, binaryExportProps: "SM64_AnimBinaryExportProps"):
        col = layout.column()

        if binaryExportProps.isDMA:
            return

        col.prop(
            self,
            "expandTab",
            icon="TRIA_DOWN" if self.expandTab else "TRIA_RIGHT",
        )
        if not self.expandTab:
            return

        col.box().label(text="These values will not be used when exporting an entire table.")
        col.prop(self, "setListIndex")
        if self.setListIndex:
            prop_split(col, self, "addr0x27", "27 Command Address")
            prop_split(col, self, "listIndexExport", "Anim List Index")
        col = layout.box().column()
        col.prop(self, "overwrite0x28")
        if self.overwrite0x28:
            prop_split(col, self, "addr0x28", "28 Command Address")


class SM64_AnimHeaderProps(bpy.types.PropertyGroup):
    expandTab: BoolProperty(name="Header Properties", default=True)

    action: PointerProperty(name="Action", type=bpy.types.Action)
    headerVariant: IntProperty(name="Header Variant Number", default=0)

    overrideName: BoolProperty(name="Override Name")
    customName: StringProperty(name="Name", default="anim_00")
    overwrites: PointerProperty(type=SM64_HeaderOverwrites)

    manualFrameRange: BoolProperty(name="Manual Frame Range")
    startFrame: IntProperty(name="Start Frame", min=0, max=MAX_S16)
    loopStart: IntProperty(name="Loop Start", min=0, max=MAX_S16)
    loopEnd: IntProperty(name="Loop End", min=0, max=MAX_S16)

    yDivisor: IntProperty(
        name="Y Divisor",
        description="When the Y divisor is not 0, the vertical translation multiplier will be calculated by the object´s animation Y multiplier divided by the Y divisor.",
        min=MIN_S16,
        max=MAX_S16,
    )

    # Flags
    setCustomFlags: BoolProperty(name="Set Custom Flags")
    noLoop: BoolProperty(
        name="No Loop", description="ANIM_FLAG_NOLOOP\nOnce the animation reachs the loop end it will not repeat"
    )
    backward: BoolProperty(
        name='"Backward"',
        description="(ANIM_FLAG_FORWARD or ANIM_FLAG_BACKWARD in refresh 16\nThe behaviour of this flag is conflicting but this is tipically used with animations which use acceleration to play an animation backwards",
    )
    noAcceleration: BoolProperty(
        name="No Acceleration",
        description="ANIM_FLAG_NO_ACCEL\nAcceleration will not be used when computing which animation frame should be used",
    )
    disabled: BoolProperty(
        name="No Shadow Translation",
        description="ANIM_FLAG_DISABLED\nDisables the use of animation translation for shadows",
    )

    customFlags: StringProperty(name="Flags", default="ANIM_FLAG_NOLOOP")
    customIntFlags: StringProperty(name="Flags", default=hex(1))

    def getFrameRange(self):
        if self.manualFrameRange:
            return self.startFrame, self.loopStart, self.loopEnd

        loopStart, loopEnd = getFrameInterval(self.action)
        return 0, loopStart, loopEnd

    def copyHeader(self, sm64ExportProps, header: "SM64_AnimHeaderProps"):
        copyPropToProp(header, self, ["customName", "headerVariant", "expandTab"])

        self.customName = f"\
{getAnimName(sm64ExportProps, header)}_variant{self.headerVariant}"

    def draw_flag_props(self, layout: bpy.types.UILayout, sm64Props):
        col = layout.column()
        exportProps: SM64_AnimExportProps = sm64Props.anim_export

        if self.setCustomFlags:
            if sm64Props.is_binary_export() or exportProps.isDmaStructure(sm64Props):
                col.prop(self, "customIntFlags")
            else:
                col.prop(self, "customFlags")
        else:
            row = col.row()
            row.prop(self, "noAcceleration")
            row.prop(self, "noLoop")

            row = col.row()
            row.prop(self, "disabled")
            row.prop(self, "backward")

    def draw_frame_range(self, layout: bpy.types.UILayout):
        col = layout.column()
        if self.manualFrameRange:
            prop_split(col, self, "startFrame", "Start Frame")
            row = col.row()
            prop_split(row, self, "loopStart", "Loop Start")
            prop_split(row, self, "loopEnd", "Loop End")

    def drawNameSettings(self, layout: bpy.types.UILayout, sm64Props):
        if sm64Props.is_binary_export():
            return

        nameSplit = layout.split(factor=0.4)
        nameSplit.prop(self, "overrideName")
        if self.overrideName:
            nameSplit.prop(self, "customName", text="")
        else:
            nameSplit.box().label(text=f"Name: {getAnimName(sm64Props.export, self)}")

        layout.box().label(text=f"Enum: {getAnimEnum(sm64Props.export, self)}")

    def draw_props(self, context: bpy.types.Context, action: bpy.types.Action, layout: bpy.types.UILayout):
        sm64Props = context.scene.fast64.sm64
        exportProps: SM64_AnimExportProps = context.scene.fast64.sm64.anim_export
        col = layout.column()

        previewOp = col.operator(SM64_PreviewAnimOperator.bl_idname)
        previewOp.playedHeader = self.headerVariant
        previewOp.playedAction = action.name
        previewOp.previewAcceleration = exportProps.previewAcceleration

        addOp = col.row().operator(SM64_TableOperations.bl_idname, text="Add Header to Table", icon="ADD")
        addOp.arrayIndex, addOp.type = len(exportProps.table.elements), "ADD"
        addOp.actionName, addOp.headerVariant = action.name, self.headerVariant

        if sm64Props.export_type == "Binary":
            self.overwrites.draw_props(col.box(), exportProps.binary)
        else:
            self.drawNameSettings(col, sm64Props)

        prop_split(col, self, "yDivisor", "Y Divisor")

        boolRow = col.row()
        boolRow.prop(self, "manualFrameRange")
        boolRow.prop(self, "setCustomFlags")

        self.draw_frame_range(col)
        self.draw_flag_props(col, sm64Props)


class SM64_ActionProps(bpy.types.PropertyGroup):
    expandTab: BoolProperty(name="Action Properties", default=True)

    overrideFileName: BoolProperty(name="Override File Name")
    customFileName: StringProperty(name="File Name", default="anim_00.inc.c")

    overrideMaxFrame: BoolProperty(name="Override Max Frame")
    customMaxFrame: IntProperty(name="Max Frame", min=1, max=MAX_U16, default=1)

    referenceTables: BoolProperty(name="Reference Tables")
    indicesTable: StringProperty(name="Indices Table", default="anim_00_indices")
    valuesTable: StringProperty(name="Value Table", default="anim_00_values")
    indicesAddress: StringProperty(name="Indices Table Address", default=hex(10756380))
    valuesAddress: StringProperty(name="Value Table Address", default=hex(10751124))

    DMAEntryAddress: StringProperty(name="DMA Entry Address", default=hex(5160968))
    DMAStartAddress: StringProperty(name="DMA Start Address", default=hex(5160960))
    startAddress: StringProperty(name="Start Address", default=hex(18712880))
    endAddress: StringProperty(name="End Address", default=hex(18874112))

    headerVariants: CollectionProperty(type=SM64_AnimHeaderProps)
    expandVariantsTab: BoolProperty(name="Header Variations", default=True)

    def getHeaders(self) -> list["SM64_AnimHeaderProps"]:
        return self.headerVariants

    def headerFromIndex(self, headerVariant=0) -> "SM64_AnimHeaderProps":
        try:
            return self.headerVariants[headerVariant]
        except IndexError:
            raise PluginError("Header variant does not exist.")

    def drawHeaderVariant(
        self,
        context,
        action: bpy.types.Action,
        layout: bpy.types.UILayout,
        header: SM64_AnimHeaderProps,
        arrayIndex: int,
    ):
        col = layout.column()

        opRow = col.row()
        removeOp = opRow.operator(SM64_AnimVariantOperations.bl_idname, icon="REMOVE")
        removeOp.arrayIndex, removeOp.type, removeOp.actionName = arrayIndex, "REMOVE", action.name

        addOp = opRow.operator(SM64_AnimVariantOperations.bl_idname, icon="ADD")
        addOp.arrayIndex, addOp.type, addOp.actionName = arrayIndex, "ADD", action.name

        moveUpCol = opRow.column()
        moveUpCol.enabled = arrayIndex != 0
        moveUp = moveUpCol.operator(SM64_AnimVariantOperations.bl_idname, icon="TRIA_UP")
        moveUp.arrayIndex, moveUp.type, moveUp.actionName = arrayIndex, "MOVE_UP", action.name

        moveDownCol = opRow.column()
        moveDownCol.enabled = arrayIndex != len(self.headerVariants) - 1
        moveDown = moveDownCol.operator(SM64_AnimVariantOperations.bl_idname, icon="TRIA_DOWN")
        moveDown.arrayIndex, moveDown.type, moveDown.actionName = arrayIndex, "MOVE_DOWN", action.name

        col.prop(
            header,
            "expandTab",
            text=f"Variation {arrayIndex + 1}",
            icon="TRIA_DOWN" if header.expandTab else "TRIA_RIGHT",
        )
        if not header.expandTab:
            return

        header.draw_props(context, action, col)

    def drawVariants(self, layout: bpy.types.UILayout, context: bpy.types.Context, action: bpy.types.Action):
        col = layout.column()

        col.prop(
            self,
            "expandVariantsTab",
            icon="TRIA_DOWN" if self.expandVariantsTab else "TRIA_RIGHT",
        )
        if not self.expandVariantsTab:
            return

        opRow = col.row()
        addOp = opRow.operator(SM64_AnimVariantOperations.bl_idname, icon="ADD")
        addOp.arrayIndex, addOp.type, addOp.actionName = len(self.headerVariants), "ADD", action.name

        if self.headerVariants:
            clearOp = opRow.operator(SM64_AnimVariantOperations.bl_idname, icon="TRASH")
            clearOp.type, clearOp.actionName = "CLEAR", action.name

            box = col.box().column()
        else:
            box = col.box().column()
            box.label(text="WARNING: Without a header, this will only export data.")
            box.label(text="A header is needed to playback the animation ingame.")
            box.label(text="Click the plus button to add a header.")

        for i, variant in enumerate(self.headerVariants):
            if i != 0:
                box.separator(factor=2.0)
            self.drawHeaderVariant(context, action, box, variant, i)

    def drawReferences(self, layout: bpy.types.UILayout, sm64Props):
        col = layout.column()
        shouldShow = not sm64Props.anim_export.binary.isDMA or not sm64Props.is_binary_export()
        if not shouldShow:
            return
        box = col.box().column()
        box.prop(self, "referenceTables")
        if not self.referenceTables:
            return

        if not sm64Props.is_binary_export():
            prop_split(box, self, "indicesTable", "Indices Table")
            prop_split(box, self, "valuesTable", "Value Table")
        else:
            prop_split(box, self, "indicesAddress", "Indices Table Address")
            prop_split(box, self, "valuesAddress", "Value Table Address")

    def draw_props(self, layout: bpy.types.UILayout, context: bpy.types.Context, action: bpy.types.Action):
        scene = context.scene
        sm64Props = scene.fast64.sm64
        exportProps = sm64Props.anim_export
        binaryExportProps = exportProps.binary

        col = layout.column()
        col.prop(
            self,
            "expandTab",
            icon="TRIA_DOWN" if self.expandTab else "TRIA_RIGHT",
        )
        if not self.expandTab:
            return

        col.operator(SM64_ExportAnim.bl_idname)

        if sm64Props.export_type == "Binary":
            prop_split(col, self, "startAddress", "Start Address")
            prop_split(col, self, "endAddress", "End Address")
            if binaryExportProps.isDMA and binaryExportProps.overwriteDMAEntry:
                prop_split(col, self, "DMAStartAddress", "DMA Start Address")
                prop_split(col, self, "DMAEntryAddress", "DMA Entry Address")
        else:
            nameSplit = col.split(factor=0.4)
            nameSplit.prop(self, "overrideFileName")
            if self.overrideFileName:
                nameSplit.prop(self, "customFileName", text="")
            else:
                nameSplit.box().label(text=f"{getAnimFileName(sm64Props, action)}")

        self.drawReferences(col, sm64Props)

        if not self.referenceTables:
            maxFrameSplit = col.split(factor=0.4)
            maxFrameSplit.prop(self, "overrideMaxFrame")
            if self.overrideMaxFrame:
                maxFrameSplit.prop(self, "customMaxFrame", text="")
            else:
                maxFrameSplit.box().label(text=f"{getMaxFrame(scene, action)}")

        self.drawVariants(col, context, action)


class SM64_TableElement(bpy.types.PropertyGroup):
    action: PointerProperty(name="Action", type=bpy.types.Action)
    headerVariant: bpy.props.IntProperty()


class SM64_AnimTable(bpy.types.PropertyGroup):
    """Scene SM64 animation import properties found under scene.fast64.sm64.anim_export.table"""

    expandTab: BoolProperty(name="Animation Table", default=True)

    elements: CollectionProperty(type=SM64_TableElement)
    overrideFiles: BoolProperty(name="Override Table and Data Files", default=False)
    generateEnums: BoolProperty(name="Generate Enums", default=True)

    startAddress: StringProperty(name="Start Address", default="0x00")
    endAddress: StringProperty(name="End Address", default="0x00")
    overrideTableName: BoolProperty(name="Override Table Name")
    customTableName: StringProperty(name="Table Name", default="mario_anims")

    def getAnimTableName(self, sm64ExportProps):
        if self.overrideTableName:
            return self.customTableName
        return f"{sm64ExportProps.name}_anims"

    def getAnimTableFileName(self, sm64Props):
        if sm64Props.export_type == "Insertable Binary":
            return "table.insertableBinary"
        else:
            return "table.inc.c"

    def drawTableNameSettings(self, context: bpy.types.Context, layout: bpy.types.UILayout):
        sm64Props = context.scene.fast64.sm64
        col = layout.column()

        if sm64Props.export_type == "Binary":
            col.prop(self, "startAddress")
            col.prop(self, "endAddress")
            return
        elif sm64Props.export_type == "Insertable Binary":
            return
        nameSplit = col.split(factor=0.4)
        nameSplit.prop(self, "overrideTableName")
        if self.overrideTableName:
            nameSplit.prop(self, "customTableName", text="")
        else:
            nameSplit.box().label(text=self.getAnimTableName(sm64Props.export))

    def drawTableElement(self, layout: bpy.types.UILayout, sm64Props, tableIndex: int, tableElement):
        exportProps: "SM64_AnimExportProps" = sm64Props.anim_export

        actionBox = layout.box().column()
        row = actionBox.row()

        action, headerVariant = tableElement.action, tableElement.headerVariant

        if action:
            actionProps: SM64_ActionProps = action.fast64.sm64

            row.label(text=f"Index {tableIndex}")
            actionBox.label(text=f'Action "{action.name}", Variant {headerVariant + 1}')
            if headerVariant < len(actionProps.headerVariants):
                header = actionProps.headerFromIndex(headerVariant)
                if not sm64Props.is_binary_export():
                    headerBox = actionBox.box().column()
                    if exportProps.table.generateEnums:
                        headerBox.label(text=f"Enum {getAnimEnum(sm64Props.export, header)}")
                    headerBox.label(text=f'Header Name "{getAnimName(sm64Props.export, header)}')
            else:
                actionBox.box().label(text=f"Header variant does not exist. Please remove.", icon="ERROR")
        else:
            actionBox.label(text=f"Header´s action does not exist. Please remove.", icon="ERROR")

        removeOp = row.operator(SM64_TableOperations.bl_idname, icon="REMOVE")
        removeOp.arrayIndex, removeOp.type = tableIndex, "REMOVE"

        moveUpCol = row.column()
        moveUpCol.enabled = tableIndex != 0
        moveUp = moveUpCol.operator(SM64_TableOperations.bl_idname, icon="TRIA_UP")
        moveUp.arrayIndex, moveUp.type = tableIndex, "MOVE_UP"

        moveDownCol = row.column()
        moveDownCol.enabled = tableIndex != len(self.elements) - 1
        moveDown = moveDownCol.operator(SM64_TableOperations.bl_idname, icon="TRIA_DOWN")
        moveDown.arrayIndex, moveDown.type = tableIndex, "MOVE_DOWN"

    def draw_props(self, context: bpy.types.Context, layout: bpy.types.UILayout):
        sm64Props = context.scene.fast64.sm64

        col = layout.column()
        col.prop(
            self,
            "expandTab",
            icon="TRIA_DOWN" if self.expandTab else "TRIA_RIGHT",
        )
        if not self.expandTab:
            return

        if not sm64Props.is_binary_export():
            col.prop(self, "overrideFiles")
            col.prop(self, "generateEnums")

        self.drawTableNameSettings(context, col)

        if self.elements:
            col.operator(SM64_ExportAnimTable.bl_idname)

        # TODO: Add selected action button should add all variations in action.
        # addOp = col.row().operator(SM64_TableOperations.bl_idname, text="Add Selected Action", icon="ADD")
        # addOp.arrayIndex, addOp.type = len(self.elements), "ADD"
        # addOp.actionName, addOp.headerVariant = getSelectedAction(exportProps, False).name, 0

        box = col.box().column()

        if self.elements:
            clearOp = box.row().operator(SM64_TableOperations.bl_idname, icon="TRASH")
            clearOp.type = "CLEAR"

            for tableIndex, tableElement in enumerate(self.elements):
                self.drawTableElement(box, sm64Props, tableIndex, tableElement)
        else:
            box.label(text="Empty table, add headers from actions.")


class SM64_AnimBinaryExportProps(bpy.types.PropertyGroup):
    level: EnumProperty(items=level_enums, name="Level", default="IC")
    overwriteDMAEntry: BoolProperty(name="Overwrite DMA Entry")
    isSegPtr: BoolProperty(name="Is Segmented Address")
    isList: BoolProperty(name="Is Anim List", default=True)
    isDMA: BoolProperty(name="Is DMA", default=True)

    insertableDirectory: StringProperty(name="Insertable Export Directory", subtype="FILE_PATH")

    def draw_props(self, layout: bpy.types.UILayout, context: bpy.types.Context, exportProps: "SM64_AnimExportProps"):
        col = layout.column()

        scene = context.scene
        sm64Props = scene.fast64.sm64

        col.prop(self, "isDMA")

        if sm64Props.export_type == "Binary":
            if self.isDMA:
                col.prop(self, "overwriteDMAEntry")
            else:
                col.prop(self, "level")

        if sm64Props.export_type == "Insertable Binary":
            split = layout.split(factor=0.3)
            split.label(text="Export Directory")
            split.prop(self, "insertableDirectory", text="")


class SM64_AnimExportProps(bpy.types.PropertyGroup):
    """Scene SM64 animation export properties found under scene.fast64.sm64.anim_export"""

    expandTab: BoolProperty(name="Export Settings", default=True)

    previewAcceleration: FloatProperty(name="Preview acceleration", default=1.0)
    playedHeader: IntProperty(min=0, default=0)
    playedAction: PointerProperty(name="Action", type=bpy.types.Action)
    playedStartFrame: IntProperty(min=0, default=0)
    playedLoopStart: IntProperty(min=0, default=0)
    playedLoopEnd: IntProperty(min=0, default=0)

    selectedAction: StringProperty(name="Action")

    binary: PointerProperty(type=SM64_AnimBinaryExportProps)
    table: PointerProperty(type=SM64_AnimTable)

    handleTables: BoolProperty(name="Create and Modify Tables", default=True)
    isDMAExport: BoolProperty(name="Export DMA Animation (Mario)")
    DMAFolder: StringProperty(name="DMA Folder", default="assets/anims/")

    bestFrameAmounts: BoolProperty(name="Best Frame Amounts", default=True)
    mergeValues: BoolProperty(name="Merge Values", default=True)

    useDMAStructure: BoolProperty(
        name="Use Vanilla DMA Structure",
        description="Headers before values and index tables and designated initialisers are not available",
        default=True,
    )
    useHexValues: BoolProperty(
        name="Hex Values for Data",
        description="Use hex values in the values and indices tables, only a visual difference",
    )
    designated: BoolProperty(
        name="Use Designated Initializers", description="Ex: \{\n.loopStart = 0, .loopEnd = 2, ...\n\}", default=True
    )

    def isDmaStructure(self, sm64Props):
        if sm64Props.is_binary_export():
            return self.binary.isDMA
        else:
            if self.isDMAExport:
                return self.useDMAStructure
            else:
                if sm64Props.export.header_type == "Custom":
                    return self.useDMAStructure
        return False

    def drawActionProperties(self, layout, context: bpy.types.Context, exportProps: "SM64_AnimExportProps"):
        col = layout.column()

        col.prop_search(self, "selectedAction", bpy.data, "actions")
        selectedAction = getSelectedAction(exportProps, False)
        if selectedAction:
            selectedAction.fast64.sm64.draw_props(col.box(), context, selectedAction)

    def canUseDMAStructure(self, sm64ExportProps):
        return sm64ExportProps.header_type == "Custom" or self.isDMAExport

    def drawCFormattingSettings(self, layout: bpy.types.UILayout, sm64ExportProps):
        col = layout.column()
        col.box().label(text="Formatting")

        useDMAStructure = self.canUseDMAStructure(sm64ExportProps) and self.useDMAStructure
        if self.canUseDMAStructure(sm64ExportProps):
            col.prop(self, "useDMAStructure")

        col.prop(self, "useHexValues")

        if useDMAStructure:
            col = col.box().column()
            col.box().label(text="Not available with the vanilla mario animation converter")
        nonDMACol = col.column()
        nonDMACol.enabled = not useDMAStructure
        nonDMACol.prop(self, "designated")

    def drawCSettings(self, layout: bpy.types.UILayout, context: bpy.types.Context):
        sm64Props = context.scene.fast64.sm64
        sm64ExportProps = sm64Props.export
        col = layout.column()

        col.prop(self, "isDMAExport")
        if self.isDMAExport:
            col.prop(self, "DMAFolder")
            writeBox = col.box().column()
            writeBox.label(text="This will write to:")
            writeBox.label(text=self.DMAFolder)

        elif sm64ExportProps.header_type != "Custom":
            col.prop(self, "handleTables")

        self.drawCFormattingSettings(col.box(), sm64ExportProps)

    def drawExportSettings(self, context: bpy.types.Context, layout: bpy.types.UILayout):
        scene = context.scene
        sm64Props = scene.fast64.sm64

        col = layout.column()
        col.prop(
            self,
            "expandTab",
            icon="TRIA_DOWN" if self.expandTab else "TRIA_RIGHT",
        )
        if not self.expandTab:
            return

        row = col.row()
        row.prop(self, "bestFrameAmounts")
        row.prop(self, "mergeValues")

        if sm64Props.export_type in ["C", "glTF"]:
            self.drawCSettings(col, context)
        elif sm64Props.is_binary_export():
            self.binary.draw_props(col, context, self)

    def draw_props(self, context: bpy.types.Context, layout: bpy.types.UILayout):
        exportProps: SM64_AnimExportProps = context.scene.fast64.sm64.anim_export

        col = layout.column()

        col.box().prop(self, "previewAcceleration")

        self.drawExportSettings(context, col.box())
        self.drawActionProperties(col.box(), context, exportProps)
        self.table.draw_props(context, col.box())


# Importing


class SM64_AnimImportProps(bpy.types.PropertyGroup):
    """Scene SM64 animation import properties found under scene.fast64.sm64.anim_import"""

    importType: EnumProperty(items=enumAnimImportTypes, name="Import Type", default="C")

    binaryImportType: EnumProperty(items=enumAnimBinaryImportTypes, name="Binary Import Type", default="Animation")

    address: StringProperty(name="Address", default="4EC690")
    isSegPtr: BoolProperty(name="Is Segmented Address")
    level: EnumProperty(items=level_enums, name="Level", default="IC")

    # Table
    readEntireTable: BoolProperty(name="Read All Animations", default=False)
    tableIndex: IntProperty(name="Table Index", min=0)

    # DMA
    DMATableAddress: StringProperty(name="DMA Table Address", default=hex(0x4EC000))
    marioAnimation: IntProperty(name="Selected Preset Mario Animation", default=0)

    path: StringProperty(name="Path", subtype="FILE_PATH", default="U:/home/user/sm64/assets/anims/")

    def isBinaryImport(self):
        return self.importType == "Binary"

    def isSegmentedPointer(self):
        return self.importType == "Binary" and self.binaryImportType != "DMA" and self.isSegPtr

    def drawBinaryAddress(self, layout: bpy.types.UILayout):
        col = layout.column()
        col.prop(self, "isSegPtr")
        prop_split(col, self, "address", "Address")

    def drawBinary(self, layout: bpy.types.UILayout):
        col = layout.column()

        col.operator(SM64_ImportAllMarioAnims.bl_idname)

        prop_split(col, self, "binaryImportType", "Binary Import Type")

        if self.binaryImportType == "DMA":
            prop_split(col, self, "DMATableAddress", "DMA Table Address")

            col.prop(self, "readEntireTable")
            if not self.readEntireTable:
                col.operator(SM64_SearchMarioAnimEnum.bl_idname, icon="VIEWZOOM")
                if self.marioAnimation == -1:
                    prop_split(col, self, "tableIndex", "Entry")
                else:
                    col.box().label(text=f"{marioAnimationNames[self.marioAnimation + 1][1]}")
        else:
            prop_split(col, self, "level", "Level")
            self.drawBinaryAddress(col.box())

        if self.binaryImportType == "Table":
            col.prop(self, "readEntireTable")
            if not self.readEntireTable:
                prop_split(col, self, "tableIndex", "List Index")

    def drawC(self, layout: bpy.types.UILayout):
        col = layout.column()
        col.prop(self, "path")

    def draw_props(self, layout: bpy.types.UILayout):
        col = layout.column()
        col.prop(self, "importType")

        box = col.box().column()
        if self.isBinaryImport():
            self.drawBinary(box)
        else:
            self.drawC(box)
        box.operator(SM64_ImportAnim.bl_idname)


sm64_anim_properties = (
    # Exporting
    SM64_HeaderOverwrites,
    SM64_AnimHeaderProps,
    SM64_TableElement,
    SM64_AnimTable,
    SM64_ActionProps,
    SM64_AnimBinaryExportProps,
    SM64_AnimExportProps,
    # Importing
    SM64_AnimImportProps,
)


def sm64_anim_properties_register():
    for cls in sm64_anim_properties:
        register_class(cls)


def sm64_anim_properties_unregister():
    for cls in reversed(sm64_anim_properties):
        unregister_class(cls)
