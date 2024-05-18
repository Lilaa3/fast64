import os
from typing import Iterable, Optional

import bpy
from bpy.types import PropertyGroup, Action, UILayout, Scene
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
from bpy.path import abspath

from ...utility import (
    customExportWarning,
    decompFolderMessage,
    directory_ui_warnings,
    directory_path_checks,
    path_ui_warnings,
    draw_and_check_tab,
    getExportDir,
    makeWriteInfoBox,
    multilineLabel,
    prop_split,
    toAlnum,
    writeBoxExportType,
    intToHex,
)
from ..sm64_utility import upgrade_hex_prop, import_rom_ui_warnings, string_int_warning
from ..sm64_constants import MAX_U16, MIN_S16, MAX_S16, level_enums, enumLevelNames

from .operators import (
    ExportAnimTable,
    ExportAnim,
    PreviewAnim,
    TableOps,
    VariantOps,
    ImportAnim,
    SearchMarioAnim,
    SearchAnimatedBehavior,
    SearchTableAnim,
    CleanObjectAnim,
)


from .constants import (
    enumAnimImportTypes,
    enumAnimBinaryImportTypes,
    marioAnimationNames,
    enumAnimExportTypes,
    enumAnimatedBehaviours,
    enumAnimationTables,
)
from .utility import (
    get_anim_enum,
    get_anim_file_name,
    get_anim_table_name,
    get_max_frame,
    get_anim_name,
    get_element_action,
    get_element_header,
)


def draw_list_op(
    layout: UILayout,
    op_cls: type,
    op_name: str,
    index=-1,
    collection: Optional[Iterable] = None,
    text="",
    icon="",
    keep_first=False,
):
    col = layout.column()
    collection = [] if collection is None else collection
    if not icon:
        icon = {"MOVE_UP": "TRIA_UP", "MOVE_DOWN": "TRIA_DOWN", "CLEAR": "TRASH"}.get(op_name, op_name)
    if op_name == "MOVE_UP":
        col.enabled = index > 0
    elif op_name == "MOVE_DOWN":
        col.enabled = index + 1 < len(collection)
    elif op_name == "CLEAR":
        col.enabled = len(collection) > 0
    elif op_name == "REMOVE":
        col.enabled = index > 0 or not keep_first
    op = col.operator(op_cls.bl_idname, text=text, icon=icon)
    op.index, op.op_name = index, op_name
    return op


class HeaderProps(PropertyGroup):
    expand_tab_in_action: BoolProperty(name="Header Properties", default=True)
    header_variant: IntProperty(name="Header Variant Number", min=0)

    set_custom_name: BoolProperty(name="Custom Name")
    custom_name: StringProperty(name="Name", default="anim_00")
    set_custom_enum: BoolProperty(name="Custom Enum")
    custom_enum: StringProperty(name="Enum", default="ANIM_00")
    manual_loop: BoolProperty(name="Manual Loop Points")
    start_frame: IntProperty(name="Start", min=0, max=MAX_S16)
    loop_start: IntProperty(name="Loop Start", min=0, max=MAX_S16)
    loop_end: IntProperty(name="End", min=0, max=MAX_S16)
    trans_divisor: IntProperty(
        name="Translation Divisor",
        description="(animYTransDivisor)\n"
        "If set to 0, the translation multiplier will be 1.\n"
        "Otherwise, the translation multiplier is determined by dividing the object's"
        "translation dividend (animYTrans) by this divisor",
        min=MIN_S16,
        max=MAX_S16,
    )
    set_custom_flags: BoolProperty(name="Set Custom Flags")
    custom_flags: StringProperty(name="Flags", default="ANIM_NO_LOOP")
    # Some flags are inverted in the ui for readability, descriptions match ui behavior
    no_loop: BoolProperty(
        name="No Loop",
        description="(ANIM_FLAG_NOLOOP)\n"
        "When disabled, the animation will not repeat from the loop start after reaching the loop "
        "end frame",
    )
    backwards: BoolProperty(
        name="Backwards",
        description="(ANIM_FLAG_FORWARD/ANIM_FLAG_BACKWARD)\n"
        "When enabled, the animation will loop (or stop if looping is disabled) after reaching "
        "the loop start frame.\n"
        "Tipically used with animations which use acceleration to play an animation backwards",
    )
    no_acceleration: BoolProperty(
        name="No Acceleration",
        description="(ANIM_FLAG_NO_ACCEL/ANIM_FLAG_2)\n"
        "When disabled, acceleration will not be used when calculating which animation frame is "
        "next",
    )
    disabled: BoolProperty(
        name="No Shadow Translation",
        description="(ANIM_FLAG_DISABLED/ANIM_FLAG_5)\n"
        "When disabled, the animation translation will not be applied to shadows",
    )
    only_horizontal_trans: BoolProperty(
        name="Only Horizontal Translation",
        description="(ANIM_FLAG_HOR_TRANS)\n"
        "When enabled, the animation horizontal translation will not be used during rendering "
        "(shadows included), the data will still be exported and included",
    )
    only_vertical_trans: BoolProperty(
        name="Only Vertical Translation",
        description="(ANIM_FLAG_VERT_TRANS)\n"
        "When enabled, the animation vertical translation will not be applied during rendering, "
        "the data will still be exported and included",
    )
    no_trans: BoolProperty(
        name="No Translation",
        description="(ANIM_FLAG_NO_TRANS/ANIM_FLAG_6)\n"
        "When disabled, the animation translation will not be used during rendering "
        "(shadows included), the data will still be exported and included",
    )
    # Binary
    table_index: IntProperty(name="Table Index", min=0)
    custom_int_flags: StringProperty(name="Flags", default="0x01")

    def draw_flag_props(self, layout: UILayout, use_int_flags: bool = False):
        col = layout.column()
        custom_split = col.split()
        custom_split.prop(self, "set_custom_flags")
        if self.set_custom_flags:
            if use_int_flags:
                custom_split.prop(self, "custom_int_flags", text="")
            else:
                custom_split.prop(self, "custom_flags", text="")
            return
        # Draw flag toggles
        row = col.row()
        row.alignment = "LEFT"
        row.prop(self, "no_loop", invert_checkbox=True, text="Loop")
        row.prop(self, "no_acceleration", invert_checkbox=True, text="Acceleration")
        row.prop(self, "backwards")
        if self.no_acceleration and self.backwards:
            col.label(text="Backwards has no porpuse without acceleration.", icon="INFO")

        row = col.row()
        no_row = row.row()
        no_row.alignment = "LEFT"
        no_row.enabled = not self.only_horizontal_trans and not self.only_vertical_trans
        no_row.prop(self, "no_trans", invert_checkbox=True, text="Translate")
        hor_row = row.row()
        hor_row.alignment = "LEFT"
        hor_row.enabled = not self.only_horizontal_trans and not self.no_trans
        hor_row.prop(self, "only_vertical_trans", text="Only Vertically")
        vert_row = row.row()
        vert_row.alignment = "LEFT"
        vert_row.enabled = not self.only_vertical_trans and not self.no_trans
        vert_row.prop(self, "only_horizontal_trans", text="Only Horizontally")
        disabled_row = row.row()
        disabled_row.alignment = "LEFT"
        disabled_row.enabled = not self.only_vertical_trans and not self.no_trans
        disabled_row.prop(self, "disabled", invert_checkbox=True, text="Shadow")

    def draw_frame_range(self, layout: UILayout):
        col = layout.column()
        col.prop(self, "manual_loop")
        if self.manual_loop:
            split = col.split()
            split.prop(self, "start_frame")
            split.prop(self, "loop_start")
            split.prop(self, "loop_end")

    def draw_names(self, layout: UILayout, action: Action, actor_name: str, generate_enums: bool):
        col = layout.column()
        if generate_enums:
            enum_split = col.split()
            enum_split.prop(self, "set_custom_enum")
            if self.set_custom_enum:
                enum_split.prop(self, "custom_enum", text="")
            else:
                auto_enum_box = enum_split.row().box()
                auto_enum_box.scale_y = 0.5
                auto_enum_box.label(text=get_anim_enum(actor_name, action, self))

        name_split = col.split()
        name_split.prop(self, "set_custom_name")
        if self.set_custom_name:
            name_split.prop(self, "custom_name", text="")
        else:
            auto_name_box = name_split.row().box()
            auto_name_box.scale_y = 0.5
            auto_name_box.label(text=get_anim_name(actor_name, action, self))

    def draw_props(
        self,
        layout: UILayout,
        action: Action,
        in_table: bool = False,
        is_dma: bool = False,
        export_type: str = "C",
        actor_name: str = "mario",
        generate_enums: bool = False,
    ):
        col = layout.column()
        binary = export_type in {"Binary", "Insertable Binary"}
        split = col.split()
        preview_op = PreviewAnim.draw_props(split)
        preview_op.played_header = self.header_variant
        preview_op.played_action = action.name
        if not in_table:
            add_op = draw_list_op(split, TableOps, "ADD", text="Add To Table", icon="LINKED")
            add_op.action_name, add_op.header_variant = action.name, self.header_variant
            if export_type == "Binary":
                prop_split(col, self, "table_index", "Table Index")
            if not binary:
                self.draw_names(col, action, actor_name, generate_enums)
        col.separator()

        prop_split(col, self, "trans_divisor", "Translation Divisor")
        self.draw_frame_range(col)
        self.draw_flag_props(col.box(), is_dma or binary)


class SM64_ActionProps(PropertyGroup):
    header: PointerProperty(type=HeaderProps)
    variants_tab: BoolProperty(name="Header Variants")
    header_variants: CollectionProperty(type=HeaderProps)
    use_custom_file_name: BoolProperty(name="Custom File Name")
    custom_file_name: StringProperty(name="File Name", default="anim_00.inc.c")
    use_custom_max_frame: BoolProperty(name="Custom Max Frame")
    custom_max_frame: IntProperty(name="Max Frame", min=1, max=MAX_U16, default=1)
    reference_tables: BoolProperty(name="Reference Tables")
    indices_table: StringProperty(name="Indices Table", default="anim_00_indices")
    values_table: StringProperty(name="Value Table", default="anim_00_values")
    # Binary
    indices_address: StringProperty(name="Indices Table")  # TODO: Toad example
    values_address: StringProperty(name="Value Table")
    start_address: StringProperty(name="Start Address", default=intToHex(18712880))
    end_address: StringProperty(name="End Address", default=intToHex(18874112))

    @property
    def headers(self) -> list[HeaderProps]:
        return [self.header] + list(self.header_variants)

    def draw_variants(
        self,
        layout: UILayout,
        action: Action,
        in_table: bool = False,
        is_dma: bool = False,
        export_type: str = "C",
        actor_name: str = "mario",
        generate_enums: bool = False,
    ):
        col = layout.column()
        args = (action, in_table, is_dma, export_type, actor_name, generate_enums)
        if draw_and_check_tab(col, self.header, "expand_tab_in_action", "Main Header", "NLA"):
            self.header.draw_props(col, *args)
        col.separator()

        op_row = col.row()
        op_row.label(
            text="Header Variants" + (f" ({len(self.header_variants)})" if self.header_variants else ""),
            icon="NLA",
        )
        add_op = draw_list_op(op_row, VariantOps, "ADD")
        add_op.action_name = action.name
        clear_op = draw_list_op(op_row, VariantOps, "CLEAR", collection=self.header_variants)
        clear_op.action_name = action.name
        if self.header_variants:
            box = col.box().column()
        for i, header in enumerate(self.header_variants):
            if i != 0:
                box.separator()

            row = box.row()
            remove_op = draw_list_op(row, VariantOps, "REMOVE", i)
            remove_op.action_name = action.name
            add_op = draw_list_op(row, VariantOps, "ADD", i)
            add_op.action_name = action.name
            up_op = draw_list_op(row, VariantOps, "MOVE_UP", i, self.header_variants)
            up_op.action_name = action.name
            down_op = draw_list_op(row, VariantOps, "MOVE_DOWN", i, collection=self.header_variants)
            down_op.action_name = action.name
            if draw_and_check_tab(row, header, "expand_tab_in_action", f"Variant {i + 1}"):
                header.draw_props(box, *args)

    def draw_references(self, layout: UILayout, is_binary: bool = False):
        col = layout.column()
        col.prop(self, "reference_tables")
        if not self.reference_tables:
            return
        if is_binary:
            prop_split(col, self, "indices_address", "Indices Table")
            prop_split(col, self, "values_address", "Value Table")
        else:
            prop_split(col, self, "indices_table", "Indices Table")
            prop_split(col, self, "values_table", "Value Table")

    def draw_file_name(self, layout: UILayout, action: Action):
        name_split = layout.split()
        name_split.prop(self, "use_custom_file_name")
        if self.use_custom_file_name:
            name_split.prop(self, "custom_file_name", text="")
        else:
            box = name_split.box()
            box.scale_y = 0.5
            box.label(text=get_anim_file_name(action, self))

    def draw_props(
        self,
        layout: UILayout,
        action: Action,
        specific_variant: int | None = None,
        in_table: bool = False,
        draw_file_name: bool = True,
        export_type: str = "C",
        actor_name: str = "mario",
        generate_enums: bool = False,
        is_dma: bool = False,
    ):
        col = layout.column()

        if not in_table:
            split = col.split()
            ExportAnim.draw_props(split)
            add_all_op = draw_list_op(split, TableOps, "ADD_ALL", text="Add All To Table", icon="LINKED")
            add_all_op.action_name = action.name
            col.separator()

            if export_type == "Binary" and not is_dma:
                prop_split(col, self, "start_address", "Start Address")
                prop_split(col, self, "end_address", "End Address")
            elif draw_file_name:
                self.draw_file_name(col, action)
        if is_dma or not self.reference_tables:
            max_frame_split = col.split()
            max_frame_split.prop(self, "use_custom_max_frame")
            if self.use_custom_max_frame:
                max_frame_split.prop(self, "custom_max_frame", text="")
            else:
                box = max_frame_split.box()
                box.scale_y = 0.4
                box.label(text=f"{get_max_frame(action, self)}")
        if not is_dma:
            self.draw_references(col, export_type in {"Binary", "Insertable Binary"})

        if specific_variant is not None:
            self.headers[specific_variant].draw_props(
                col, action, in_table, is_dma, export_type, actor_name, generate_enums
            )
        else:
            col.separator()

            self.draw_variants(col, action, in_table, is_dma, export_type, actor_name, generate_enums)


class TableElementProps(PropertyGroup):
    expand_tab: BoolProperty()
    action_prop: PointerProperty(name="Action", type=Action)
    variant: IntProperty(name="Variant", min=0)
    reference: BoolProperty(name="Reference")
    header_name: StringProperty(name="Header Reference", default="toad_seg6_anim_0600B66C")
    header_address: StringProperty(name="Header Reference", default=intToHex(0x0600B75C))  # Toad animation 0
    enum_name: StringProperty(name="Enum Name")

    def set_variant(self, action: Action, variant: int):
        self.action_prop = action
        self.variant = variant

    def draw_reference(self, layout: UILayout, export_type: str = "C", generate_enums: bool = False):
        row = layout.row()
        if export_type in {"Binary", "Insertable Binary"}:
            prop_split(row, self, "header_address", "Header Address")
            return
        if generate_enums:
            text_row = row.row()
            text_row.alignment = "LEFT"
            text_row.label(text="Enum")
        prop_row = row.row()
        prop_row.alignment = "EXPAND"
        if generate_enums:
            prop_row.prop(self, "enum_name", text="")
        row.prop(self, "header_name", text="")

    def draw_props(
        self,
        row: UILayout,  # left side of the row for table ops
        prop_layout: UILayout,
        is_dma: bool = False,
        can_reference: bool = True,
        export_seperately: bool = True,
        export_type: str = "C",
        generate_enums: bool = False,
        actor_name: str = "mario",
    ):
        col = prop_layout.column()
        reference_row = row.row()
        reference_row.alignment = "LEFT"
        if can_reference:
            reference_row.prop(self, "reference")
            if self.reference:
                self.draw_reference(col, export_type, generate_enums)
                return
        action_row = row.row()
        action_row.alignment = "EXPAND"
        action_row.prop(self, "action_prop", text="")

        if not self.action_prop:
            col.box().label(text="Header´s action does not exist. Use references for NULLs", icon="ERROR")
            return
        action_props: SM64_ActionProps = self.action_prop.fast64.sm64

        variant_row = col.row()
        variant_row.alignment = "LEFT"
        variant_row.prop(self, "variant")
        remove_op = draw_list_op(variant_row, VariantOps, "REMOVE", self.variant, keep_first=True)
        remove_op.action_name = self.action_prop.name
        add_op = draw_list_op(variant_row, VariantOps, "ADD", self.variant)
        add_op.action_name = self.action_prop.name
        if not 0 <= self.variant < len(action_props.headers):
            col.box().label(text="Header variant does not exist.", icon="ERROR")
            return
        elif self.variant != 0:
            variant_row.label(text=f"Variant")

        header_props = get_element_header(self, can_reference)
        if draw_and_check_tab(
            col,
            self,
            "expand_tab",
            f"{get_anim_name(actor_name, self.action_prop, header_props)} Properties",
        ):
            action_props.draw_props(
                layout=col,
                action=self.action_prop,
                export_type=export_type,
                specific_variant=self.variant,
                in_table=True,
                draw_file_name=export_type == "C" and not is_dma and export_seperately,
                actor_name=actor_name,
                generate_enums=generate_enums,
                is_dma=is_dma,
            )


class TableProps(PropertyGroup):
    elements: CollectionProperty(type=TableElementProps)

    export_seperately: BoolProperty(name="Export All Seperately")
    write_data_seperately: BoolProperty(name="Write Data Seperately")
    override_files_prop: BoolProperty(name="Table and Data Files", default=True)
    generate_enums: BoolProperty(name="Generate Enums", default=True)
    use_custom_table_name: BoolProperty(name="Custom Table Name")
    custom_table_name: StringProperty(name="Table Name", default="mario_anims")
    # Binary
    data_address: StringProperty(
        name="Data Address",
        default=intToHex(0x00A3F7E0),  # Toad animation table data
    )
    data_end_address: StringProperty(
        name="Data End",
        default=intToHex(0x00A466C0),
    )
    address: StringProperty(
        name="Table Address",
        default=intToHex(0x00A46738),  # Toad animation table
    )
    end_address: StringProperty(name="Table End", default=intToHex(0x00A4675C))
    dma_address: StringProperty(name="DMA Table Address", default=intToHex(0x4EC000))
    dma_end_address: StringProperty(name="DMA Table End", default=intToHex(0x4EC000 + 0x8DC20))
    update_behavior: BoolProperty(name="Update Behavior", default=True)
    behaviour: bpy.props.EnumProperty(items=enumAnimatedBehaviours, default=intToHex(0x13002EF8))
    behavior_address_prop: StringProperty(name="Behavior Address", default=intToHex(0x13002EF8))
    begining_animation: StringProperty(name="Begining Animation", default="0x00")
    insertable_file_name: StringProperty(name="Insertable File Name", default="toad.insertable")

    @property
    def behavior_address(self):
        return int(self.behavior_address_prop if self.behaviour == "Custom" else self.behaviour, 0)

    @property
    def override_files(self):
        return self.export_seperately and self.override_files_prop

    def draw_element(
        self,
        layout: UILayout,
        index: int,
        table_element: TableElementProps,
        is_dma: bool = False,
        can_reference: bool = True,
        duplicate_index: int | None = 0,
        export_type: str = "c",
        actor_name: str = "mario",
    ):
        col = layout.column()
        row = col.row()

        left_row = row.row()
        left_row.alignment = "EXPAND"

        op_row = row.row()
        op_row.alignment = "RIGHT"
        op_row.label(text=str(index))

        draw_list_op(op_row, TableOps, "ADD", index)
        draw_list_op(op_row, TableOps, "REMOVE", index)
        draw_list_op(op_row, TableOps, "MOVE_UP", index, self.elements)
        draw_list_op(op_row, TableOps, "MOVE_DOWN", index, self.elements)

        table_element.draw_props(
            left_row,
            col,
            is_dma,
            can_reference,
            self.export_seperately,
            export_type,
            self.generate_enums,
            actor_name,
        )

        if is_dma and duplicate_index is not None:
            multilineLabel(
                col.box(),
                "In DMA tables, headers for each action must be \nin one sequence or the data will be duplicated.\n"
                f"Data duplicate at index {duplicate_index}",
                "INFO",
            )

    def draw_non_exclusive_settings(self, layout: UILayout, is_dma: bool, export_type, actor_name: str):
        col = layout.column()
        if export_type == "C":
            col.prop(self, "generate_enums")
            name_split = col.split()
            name_split.prop(self, "use_custom_table_name")
            if self.use_custom_table_name:
                name_split.prop(self, "custom_table_name", text="")
            else:
                box = name_split.row().box()
                box.scale_y = 0.5
                box.label(text=get_anim_table_name(self, actor_name))
        elif export_type == "Binary":
            if is_dma:
                prop_split(col, self, "dma_address", "DMA Table Address")
                prop_split(col, self, "dma_end_address", "DMA Table End")
                return
            prop_split(col, self, "address", "Table Address")
            prop_split(col, self, "end_address", "Table End")

            box = col.box().column()
            box.prop(self, "update_behavior")
            if self.update_behavior:
                multilineLabel(
                    box,
                    "Will update the LOAD_ANIMATIONS and ANIMATE commands.\n"
                    "Does not raise an error if there is no ANIMATE command",
                    "INFO",
                )
                SearchAnimatedBehavior.draw_props(box, self, "behaviour", "Behaviour")
                if self.behaviour == "Custom":
                    prop_split(box, self, "behavior_address_prop", "Behavior Address")
                prop_split(box, self, "begining_animation", "Beginning Animation")

    def draw_props(
        self,
        layout: UILayout,
        is_dma: bool = False,
        non_exclusive_settings: bool = True,
        export_type: str = "C",
        actor_name: str = "mario",
    ):
        col = layout.column()
        can_reference = not is_dma
        if non_exclusive_settings:
            self.draw_non_exclusive_settings(col, is_dma, export_type, actor_name)

        if not is_dma:
            if export_type == "Binary":
                col.prop(self, "write_data_seperately")
                if self.write_data_seperately:
                    prop_split(col, self, "data_address", "Data Address")
                    prop_split(col, self, "data_end_address", "Data End")
            elif export_type == "C":
                col.prop(self, "export_seperately")
                if self.export_seperately:
                    col.prop(self, "override_files_prop")
        if export_type == "Insertable Binary":
            prop_split(col, self, "insertable_file_name", "File Name")

        export_col = col.column()
        ExportAnimTable.draw_props(export_col)
        export_col.enabled = True if self.elements else False
        if is_dma and export_type == "C":
            multilineLabel(
                col,
                "The export will follow the vanilla DMA naming\n"
                "conventions (anim_xx.inc.c, anim_xx, anim_xx_values, etc).",
                icon="INFO",
            )
        export_col.separator()

        op_row = col.row()
        op_row.label(text="Headers" + (f" ({len(self.elements)})" if self.elements else ""), icon="NLA")
        draw_list_op(op_row, TableOps, "ADD")
        draw_list_op(op_row, TableOps, "CLEAR", collection=self.elements)
        if self.elements:
            box = col.box().column()
        actions = []
        element_props: TableElementProps
        for i, element_props in enumerate(self.elements):
            if i != 0:
                box.separator()

            action = get_element_action(element_props, can_reference)
            if action in actions and actions[-1] != action:
                duplicate_index = actions.index(action)
            else:
                duplicate_index = None
            self.draw_element(
                box,
                i,
                element_props,
                is_dma,
                can_reference,
                duplicate_index,
                export_type,
                actor_name,
            )
            actions.append(action)


class CleanAnimProps(PropertyGroup):
    threshold: FloatProperty(name="Threshold", min=0.0, max=0.1, default=0.01, description="When zero, only identical keyframes will be removed",)
    to_quaternion: BoolProperty(name="Force Quaternions", default=True)
    def draw_props(self, layout: UILayout, tools_context: bool = True):
        col = layout.column()
        prop_split(col, self, "threshold", "Threshold", slider=True)
        if tools_context:
            col.prop(self, "to_quaternion")
            CleanObjectAnim.draw_props(col)


class ImportProps(PropertyGroup):
    clean_up: BoolProperty(name="Clean Up Keyframes", default=True)
    clean_up_props: PointerProperty(type=CleanAnimProps)

    clear_table: BoolProperty(name="Clear Table On Import", default=True)
    import_type: EnumProperty(items=enumAnimImportTypes, name="Type", default="C")
    preset: bpy.props.EnumProperty(items=enumAnimationTables, name="Preset", default="Mario")
    decomp_path: StringProperty(name="Decomp Path", subtype="FILE_PATH", default="/home/user/sm64")
    binary_import_type: EnumProperty(
        items=enumAnimBinaryImportTypes,
        name="Type",
        default="Table",
    )
    assume_bone_count: BoolProperty(
        name="Assume Bone Count",
        description="When enabled, the selected armature's bone count will be used instead of "
        "the header's, as old fast64 binary exports did no export this value",
    )

    rom: StringProperty(name="Import ROM", subtype="FILE_PATH")
    read_entire_table: BoolProperty(name="Read Entire Table", default=True)
    check_null: BoolProperty(name="Check NULL Delimiter", default=True)
    table_size_prop: IntProperty(name="Table Size", min=0)
    table_index_prop: IntProperty(name="Table Index", min=0)
    table_address: StringProperty(name="Address", default=intToHex(0x0600FC48))  # Toad animation table
    animation_address: StringProperty(name="Address", default=intToHex(0x0600B75C))  # Toad animation 0
    is_segmented_address_prop: BoolProperty(name="Is Segmented Address", default=True)
    level: EnumProperty(items=level_enums, name="Level", default="IC")
    dma_table_address: StringProperty(name="DMA Table Address", default="0x4EC000")
    mario_animation: EnumProperty(name="Selected Preset Mario Animation", items=marioAnimationNames)

    read_from_rom: BoolProperty(
        name="Read From Import ROM",
        description="When enabled, the importer will read from the import ROM given a non defined address",
    )

    path: StringProperty(name="Path", subtype="FILE_PATH", default="anims/")
    remove_name_footer: BoolProperty(
        name="Remove Name Footers",
        description='Remove "anim_" from imported animations',
        default=True,
    )
    use_custom_name: BoolProperty(name="Use Custom Name", default=True)

    @property
    def mario_table_index(self):
        return (
            None
            if self.read_entire_table
            else int(self.mario_animation, 0)
            if self.mario_animation != "Custom"
            else self.table_index
        )

    @property
    def table_index(self):
        return None if self.read_entire_table else self.table_index_prop

    @property
    def address(self):
        if self.import_type != "Binary":
            return
        return int(
            self.dma_table_address
            if self.binary_import_type == "DMA"
            else (self.table_address if self.binary_import_type == "Table" else self.animation_address),
            0,
        )

    @property
    def is_segmented_address(self):
        return (
            self.is_segmented_address_prop
            if self.import_type == "Binary" and self.binary_import_type in {"Table", "Animation"}
            else False
        )

    @property
    def table_size(self):
        return None if self.check_null else self.table_size_prop

    def draw_path(self, layout: UILayout):
        prop_split(layout, self, "path", "Directory or File Path")
        path_ui_warnings(layout, abspath(self.path))

    def draw_c(self, layout: UILayout):
        col = layout.column()
        if self.preset == "Custom":
            self.draw_path(col)
        else:
            prop_split(col, self, "decomp_path", "Decomp Path")
            directory_ui_warnings(col, abspath(self.decomp_path))
        col.prop(self, "remove_name_footer")
        col.prop(self, "use_custom_name")

    def draw_import_rom(self, layout: UILayout, import_rom: os.PathLike | None = None):
        col = layout.column()
        col.label(text="Uses scene import ROM by default", icon="INFO")
        prop_split(col, self, "rom", "Import ROM")
        return import_rom_ui_warnings(col, self.rom if import_rom is None else import_rom)

    def draw_table_settings(self, layout: UILayout):
        row = layout.row(align=True)
        left_row = row.row(align=True)
        left_row.alignment = "LEFT"
        left_row.prop(self, "read_entire_table")
        left_row.prop(self, "check_null")
        right_row = row.row(align=True)
        right_row.alignment = "EXPAND"
        if not self.read_entire_table:
            right_row.prop(self, "table_index_prop", text="Index")
        elif not self.check_null:
            right_row.prop(self, "table_size_prop", text="Size")

    def draw_binary(self, layout: UILayout, import_rom: os.PathLike | None = None):
        col = layout.column()
        self.draw_import_rom(col, import_rom)
        col.separator()

        if self.preset != "Custom":
            split = col.split()
            split.prop(self, "read_entire_table")
            if not self.read_entire_table:
                if self.preset == "Mario":
                    SearchMarioAnim.draw_props(split, self, "mario_animation", "")
                if self.preset != "Mario" or self.mario_animation == "Custom":
                    split.prop(self, "table_index_prop", text="Index")
            return
        prop_split(col, self, "binary_import_type", "Animation Type")
        if self.binary_import_type == "DMA":
            prop_split(col, self, "dma_table_address", "DMA Table Address")
            split = col.split()
            split.prop(self, "read_entire_table")
            if not self.read_entire_table:
                split.prop(self, "table_index_prop", text="Index")
            return

        split = col.split()
        split.prop(self, "is_segmented_address_prop")
        if self.binary_import_type == "Table":
            split.prop(self, "table_address", text="")
            string_int_warning(col, self.table_address)
        elif self.binary_import_type == "Animation":
            split.prop(self, "animation_address", text="")
            string_int_warning(col, self.animation_address)
        prop_split(col, self, "level", "Level")
        if self.binary_import_type == "Table":  # Draw settings after level
            self.draw_table_settings(col)

    def draw_insertable_binary(self, layout: UILayout, import_rom: os.PathLike | None = None):
        col = layout.column()
        self.draw_path(col)
        col.separator()

        col.label(text="Animation type will be read from the files", icon="INFO")

        table_box = col.column()
        table_box.label(text="Table Imports", icon="ANIM")
        self.draw_table_settings(table_box)
        col.separator()

        col.prop(self, "read_from_rom")
        if self.read_from_rom:
            self.draw_import_rom(col, import_rom)
            prop_split(col, self, "level", "Level")

    def draw_props(self, layout: UILayout, import_rom: os.PathLike | None = None):
        col = layout.column()

        prop_split(col, self, "import_type", "Type")

        if self.import_type in {"C", "Binary"}:
            SearchTableAnim.draw_props(col, self, "preset", "Preset")
            col.separator()

        if self.import_type == "C":
            self.draw_c(col)
        elif self.import_type in {"Binary", "Insertable Binary"}:
            if self.import_type == "Binary":
                self.draw_binary(col, import_rom)
            elif self.import_type == "Insertable Binary":
                self.draw_insertable_binary(col, import_rom)
            col.prop(self, "assume_bone_count")
        col.separator()

        col.prop(self, "clear_table")
        col.prop(self, "clean_up")
        if self.clean_up:
            self.clean_up_props.draw_props(col, False)
        ImportAnim.draw_props(col)


class AnimProps(PropertyGroup):
    version: bpy.props.IntProperty(name="AnimProps Version", default=0)
    cur_version = 1  # version after property migration
    played_header: IntProperty(min=0)
    played_action: PointerProperty(name="Action", type=Action)
    object_menu_tab: BoolProperty(name="SM64 Animation Inspector")

    table_tab: BoolProperty(name="Table", default=True)
    table: PointerProperty(type=TableProps)
    importing_tab: BoolProperty(name="Importing")
    importing: PointerProperty(type=ImportProps)
    action_tab: BoolProperty(name="Action", default=False)
    selected_action: PointerProperty(name="Action", type=Action)

    tools_tab: BoolProperty(name="Tools")
    clean_up: PointerProperty(type=CleanAnimProps)

    update_table: BoolProperty(
        name="Update Table On Action Export",
        description="Update table outside of table exports",
        default=True,
    )
    quick_read: BoolProperty(
        name="Quick Data Read", default=True, description="Read fcurves directly, should work with the majority of rigs"
    )
    directory_path: StringProperty(name="Directory Path", subtype="FILE_PATH")
    dma_folder: StringProperty(name="DMA Folder", default="assets/anims/")
    use_dma_structure: BoolProperty(
        name="Use DMA Structure",
        description="When enabled, the Mario animation converter order is used (headers, indicies, values)",
    )
    actor_name_prop: StringProperty(name="Name", default="mario")  # TODO: Does this need to be passed to a @property?
    # TODO: Ideally, this pr will be merged after combined exports, so this should be updated to use the group enum there
    group_name: StringProperty(name="Group Name", default="group0")
    header_type: EnumProperty(items=enumAnimExportTypes, name="Export Type", default="Actor")
    custom_level_name: StringProperty(name="Level", default="bob")
    level_option: EnumProperty(items=enumLevelNames, name="Level", default="bob")
    # Binary
    binary_level: EnumProperty(items=level_enums, name="Level", default="IC")
    is_binary_dma: BoolProperty(name="Is DMA", default=True)
    assume_bone_count: BoolProperty(
        name="Assume Bone Count",
        description="When importing a DMA table for insertion, "
        "assume the bone count based on the armature instead of the headers",
    )
    insertable_directory_path: StringProperty(name="Directory Path", subtype="FILE_PATH")  # Insertable

    def update_version_0(self, scene: Scene):
        importing: ImportProps = self.importing

        upgrade_hex_prop(importing, scene, "animation_address", "animStartImport")
        importing.is_segmented_address_prop = scene.get(
            "animIsSegPtr",
            importing.is_segmented_address_prop,
        )
        importing.level = scene.get("levelAnimImport", importing.level)
        importing.table_index_prop = scene.get("animListIndexImport", importing.table_index_prop)
        if importing.get("isDMAImport", False):
            importing.binary_import_type = "DMA"
        elif importing.get("animIsAnimList", True):
            importing.binary_import_type = "Table"
        # Export
        for action in bpy.data.actions:
            action_props: SM64_ActionProps = action.fast64.sm64
            action_props.header.no_loop = not scene.get(
                "loopAnimation",
                not action_props.header.no_loop,
            )
            upgrade_hex_prop(action_props, scene, "start_address", "animExportStart")
            upgrade_hex_prop(action_props, scene, "end_address", "animExportEnd")
        custom_export = scene.get("animCustomExport", False)
        if custom_export:
            self.header_type = "Custom"
        else:
            header_type = scene.get("animExportHeaderType", None)
            if header_type:
                self.header_type = enumAnimExportTypes[header_type][0]

        self.directory_path = scene.get("animExportPath", self.directory_path)
        self.actor_name_prop = scene.get("animName", self.actor_name_prop)
        self.group_name = scene.get("animGroupName", self.group_name)
        level_option = scene.get("animLevelOption", None)
        if level_option:
            self.level_option = enumLevelNames[level_option][0]
        self.custom_level_name = scene.get("animLevelName", self.custom_level_name)
        self.is_binary_dma = scene.get("isDMAExport", self.is_binary_dma)

        insertable_directory_path = scene.get("animInsertableBinaryPath", "")
        if insertable_directory_path:
            # Ignores file name
            self.insertable_directory_path = os.path.split(insertable_directory_path)[0]

        self.update_table = scene.get("setAnimListIndex", self.update_table)
        table: TableProps = self.table
        # upgrade_hex_prop(table, scene, "", "addr_0x27")
        table.update_behavior = scene.get("overwrite_0x28", table.update_behavior)
        upgrade_hex_prop(table, scene, "animate_command_address", "addr_0x28")
        table.begining_animation = scene.get("animListIndexExport", table.begining_animation)
        self.binary_level = scene.get("levelAnimExport", self.binary_level)

        self.version = 1
        print("Upgraded global SM64 animation settings to version 1")

    @staticmethod
    def upgrade_changed_props():
        for scene in bpy.data.scenes:
            anim_props: AnimProps = scene.fast64.sm64.animation
            if anim_props.version == 0:
                anim_props.update_version_0(scene)

    @property
    def actor_name(self):
        return self.actor_name_prop if self.header_type != "DMA" else None

    @property
    def is_c_dma(self):
        return self.use_dma_structure if self.header_type == "Custom" else self.header_type == "DMA"

    @property
    def level_name(self):
        return self.custom_level_name if self.level_option == "Custom" else self.level_option

    def get_c_paths(self, decomp: os.PathLike):
        custom_export = self.header_type == "Custom"
        base_path = self.directory_path if custom_export else decomp
        if self.is_c_dma:  # DMA or Custom with DMA structure
            anim_directory: os.PathLike = abspath(os.path.join(base_path, self.dma_folder))
            directory_path_checks(anim_directory)
            return (anim_directory, None, None)
        dir_name = toAlnum(self.actor_name)
        header_directory: os.PathLike = abspath(
            getExportDir(
                custom_export,
                base_path,
                self.header_type,
                self.level_name,
                "",
                dir_name,
            )[0]
        )
        directory_path_checks(header_directory)
        geo_directory: os.PathLike = abspath(os.path.join(header_directory, dir_name))
        anim_directory: os.PathLike = abspath(os.path.join(geo_directory, "anims"))
        return (anim_directory, geo_directory, header_directory)

    def draw_insertable_binary_settings(self, layout: UILayout):
        col = layout.column()
        prop_split(col, self, "directory_path", "Directory")
        directory_ui_warnings(col, abspath(self.directory_path))

    def draw_binary_settings(self, layout: UILayout):
        col = layout.column()
        box = layout.box().column()
        if self.is_binary_dma:
            col.prop(self, "assume_bone_count")
        else:
            col.prop(self, "binary_level")
            box.prop(self, "update_table")
            if not self.update_table:
                return
        self.table.draw_non_exclusive_settings(box, self.is_binary_dma, "Binary", self.actor_name)

    def draw_c_settings(self, layout: UILayout):
        col = layout.column()
        prop_split(col, self, "header_type", "Header Type")
        if self.header_type == "DMA":
            prop_split(col, self, "dma_folder", "Folder", icon="FILE_FOLDER")
            decompFolderMessage(col)
            return

        prop_split(col, self, "actor_name_prop", "Name")
        if self.header_type == "Custom":
            col.prop(self, "use_dma_structure")
            col.prop(self, "directory_path")
            col.separator()

            if directory_ui_warnings(col, abspath(self.directory_path)):
                customExportWarning(col)
        else:
            if self.header_type == "Actor":
                prop_split(col, self, "group_name", "Group Name")
            elif self.header_type == "Level":
                prop_split(col, self, "level_option", "Level")
                if self.level_option == "custom":
                    prop_split(col, self, "custom_level_name", "Level Name")
            col.separator()

            decompFolderMessage(col)
            write_box = makeWriteInfoBox(col).column()
            writeBoxExportType(
                write_box,
                self.header_type,
                self.actor_name,
                self.custom_level_name,
                self.level_option,
            )
        if not self.is_c_dma:
            box = col.box().column()
            box.prop(self, "update_table")
            if self.update_table:
                self.table.draw_non_exclusive_settings(box, False, "C", self.actor_name)

    def draw_export_settings(self, layout: UILayout, export_type: str):
        col = layout.column()
        is_binary = export_type in {"Binary", "Insertable Binary"}
        is_dma = (is_binary and self.is_binary_dma) or (not is_binary and self.is_c_dma)

        if is_binary:
            col.prop(self, "is_binary_dma")
            if export_type == "Binary":
                self.draw_binary_settings(col)
            elif export_type == "Insertable Binary":
                self.draw_insertable_binary_settings(col)
        elif export_type == "C":
            self.draw_c_settings(col)
        col.prop(self, "quick_read")
        col.separator(factor=2)

        if draw_and_check_tab(col, self, "table_tab", icon="ANIM"):
            self.table.draw_props(
                col,
                is_dma,
                not self.update_table and not is_dma,
                export_type,
                self.actor_name,
            )
        if draw_and_check_tab(col, self, "action_tab", icon="ACTION"):
            col.prop(self, "selected_action")
            if self.selected_action:
                self.selected_action.fast64.sm64.draw_props(
                    layout=col,
                    action=self.selected_action,
                    export_type=export_type,
                    actor_name=self.actor_name,
                    generate_enums=self.table.generate_enums,
                    is_dma=is_dma,
                )

    def draw_props(
        self,
        layout: UILayout,
        export_type: str,
        show_importing: bool = True,
        import_rom: os.PathLike | None = None,
    ):
        col = layout.column()
        self.draw_export_settings(col, export_type)
        col.separator()
        if show_importing:
            if draw_and_check_tab(col, self, "importing_tab", icon="IMPORT"):
                self.importing.draw_props(col, import_rom)
        if draw_and_check_tab(col, self, "tools_tab", icon="TOOL_SETTINGS"):
            self.clean_up.draw_props(col)


properties = (
    HeaderProps,
    TableElementProps,
    SM64_ActionProps,
    TableProps,
    CleanAnimProps,
    ImportProps,
    AnimProps,
)


def anim_props_register():
    for cls in properties:
        register_class(cls)


def anim_props_unregister():
    for cls in reversed(properties):
        unregister_class(cls)
