import os
from os import PathLike
from typing import Iterable, Optional

import bpy
from bpy.types import PropertyGroup, Action, UILayout, Scene, Object
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
from ..sm64_utility import upgrade_hex_prop, import_rom_ui_warnings, string_int_prop, string_int_warning
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
    get_table_name,
    get_max_frame,
    get_anim_name,
    get_element_action,
    get_element_header,
    get_selected_action,
)


def draw_list_op(
    layout: UILayout,
    op_cls: type,
    op_name: str,
    index=-1,
    collection: Optional[Iterable] = None,
    keep_first=False,
    text="",
    icon="",
    **op_args,
):
    col = layout.column()
    collection = [] if collection is None else collection
    icon = icon if icon else op_name
    if op_name == "MOVE_UP":
        icon = "TRIA_UP"
        col.enabled = index > 0
    elif op_name == "MOVE_DOWN":
        icon = "TRIA_DOWN"
        col.enabled = index + 1 < len(collection)
    elif op_name == "CLEAR":
        icon = "TRASH"
        col.enabled = len(collection) > (1 if keep_first else 0)
    elif op_name == "REMOVE":
        col.enabled = len(collection) > index >= (1 if keep_first else 0)
    op = col.operator(op_cls.bl_idname, text=text, icon=icon)
    op.index, op.op_name = index, op_name
    for attr, value in op_args.items():
        setattr(op, attr, value)
    return op


def draw_list_ops(layout: UILayout, op_cls: type, index: int, collection: Optional[Iterable], **op_args):
    layout.label(text=str(index))
    ops = ("MOVE_UP", "MOVE_DOWN", "ADD", "REMOVE")
    for op_name in ops:
        draw_list_op(layout, op_cls, op_name, index, collection, **op_args)


class HeaderProperty(PropertyGroup):
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
        "If set to 0, the translation multiplier will be 1. "
        "Otherwise, the translation multiplier is determined by "
        "dividing the object's translation dividend (animYTrans) by this divisor",
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
        name="Loop Backwards",
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
        "When enabled, only the animation horizontal translation will be used during rendering\n"
        "(shadows included), the vertical translation will still be exported and included",
    )
    only_vertical_trans: BoolProperty(
        name="Only Vertical Translation",
        description="(ANIM_FLAG_VERT_TRANS)\n"
        "When enabled, only the animation vertical translation will be applied during rendering\n"
        "(shadows included) the horizontal translation will still be exported and included",
    )
    no_trans: BoolProperty(
        name="No Translation",
        description="(ANIM_FLAG_NO_TRANS/ANIM_FLAG_6)\n"
        "When disabled, the animation translation will not be used during rendering\n"
        "(shadows included), the translation will still be exported and included",
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
                string_int_warning(col, self.custom_int_flags)
            else:
                custom_split.prop(self, "custom_flags", text="")
            return
        # Draw flag toggles
        row = col.row(align=True)
        row.alignment = "LEFT"
        row.prop(self, "no_loop", invert_checkbox=True, text="Loop", toggle=1)
        row.prop(self, "backwards", toggle=1)
        row.prop(self, "no_acceleration", invert_checkbox=True, text="Acceleration", toggle=1)
        if self.no_acceleration and self.backwards:
            col.label(text="Backwards has no porpuse without acceleration.", icon="INFO", toggle=1)

        trans_row = col.row(align=True)
        trans_prop_row = trans_row.row()
        trans_prop_row.prop(self, "no_trans", invert_checkbox=True, text="Translate", toggle=1)

        hor_row = trans_row.row()
        hor_row.enabled = not self.only_horizontal_trans and not self.no_trans
        hor_row.prop(self, "only_vertical_trans", text="Only Vertically", toggle=1)
        vert_row = trans_row.row()
        vert_row.enabled = not self.only_vertical_trans and not self.no_trans
        vert_row.prop(self, "only_horizontal_trans", text="Only Horizontally", toggle=1)
        disabled_row = trans_row.row()
        disabled_row.enabled = not self.only_vertical_trans and not self.no_trans
        disabled_row.prop(self, "disabled", invert_checkbox=True, text="Shadow", toggle=1)

    def draw_frame_range(self, layout: UILayout):
        col = layout.column()
        col.prop(self, "manual_loop")
        if self.manual_loop:
            split = col.split()
            split.prop(self, "start_frame")
            split.prop(self, "loop_start")
            split.prop(self, "loop_end")

    def draw_names(self, layout: UILayout, action: Action, actor_name: str, gen_enums: bool):
        col = layout.column()
        if gen_enums:
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
        in_table: bool,
        dma: bool,
        export_type: str,
        actor_name: str,
        gen_enums: bool,
    ):
        col = layout.column()
        binary = export_type in {"Binary", "Insertable Binary"}
        split = col.split()
        preview_op = PreviewAnim.draw_props(split)
        preview_op.played_header = self.header_variant
        preview_op.played_action = action.name
        if not in_table:
            draw_list_op(
                split,
                TableOps,
                "ADD",
                text="Add To Table",
                icon="LINKED",
                action_name=action.name,
                header_variant=self.header_variant,
            )
            if export_type == "Binary":
                prop_split(col, self, "table_index", "Table Index")
            if not binary:
                self.draw_names(col, action, actor_name, gen_enums)
        col.separator()

        prop_split(col, self, "trans_divisor", "Translation Divisor")
        self.draw_frame_range(col)
        self.draw_flag_props(col, dma or binary)


class SM64_ActionProperty(PropertyGroup):
    header: PointerProperty(type=HeaderProperty)
    variants_tab: BoolProperty(name="Header Variants")
    header_variants: CollectionProperty(type=HeaderProperty)
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
    def headers(self) -> list[HeaderProperty]:
        return [self.header] + list(self.header_variants)

    def draw_variants(
        self,
        layout: UILayout,
        action: Action,
        in_table: bool,
        dma: bool,
        export_type: str,
        actor_name: str,
        gen_enums: bool = False,
    ):
        col = layout.column()
        args = (action, in_table, dma, export_type, actor_name, gen_enums)
        op_row = col.row()
        op_row.label(text=f"Header Variants ({len(self.headers)})", icon="NLA")
        draw_list_op(op_row, VariantOps, "CLEAR", -1, self.headers, True, action_name=action.name)

        for i, header in enumerate(self.headers):
            if i != 0:
                col.separator()

            row = col.row()
            if draw_and_check_tab(
                row,
                header,
                "expand_tab_in_action",
                get_anim_name(actor_name, action, header),
            ):
                header.draw_props(col, *args)
            op_row = row.row()
            op_row.alignment = "RIGHT"
            draw_list_ops(op_row, VariantOps, i, self.headers, keep_first=True, action_name=action.name)

    def draw_references(self, layout: UILayout, is_binary: bool = False):
        col = layout.column()
        col.prop(self, "reference_tables")
        if not self.reference_tables:
            return
        if is_binary:
            string_int_prop(col, self, "indices_address", "Indices Table")
            string_int_prop(col, self, "values_address", "Value Table")
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
        specific_variant: int | None,
        in_table: bool,
        draw_file_name: bool,
        export_type: str,
        actor_name: str,
        gen_enums: bool,
        dma: bool,
    ):
        col = layout.column()

        if specific_variant is not None:
            col.label(text="Action Properties", icon="ACTION")
        if not in_table:
            split = col.split()
            ExportAnim.draw_props(split)
            draw_list_op(split, TableOps, "ADD_ALL", text="Add All To Table", icon="LINKED", action_name=action.name)
            col.separator()

            if export_type == "Binary" and not dma:
                string_int_prop(col, self, "start_address", "Start Address")
                string_int_prop(col, self, "end_address", "End Address")
        if draw_file_name:
            self.draw_file_name(col, action)
        if dma or not self.reference_tables:
            max_frame_split = col.split()
            max_frame_split.prop(self, "use_custom_max_frame")
            if self.use_custom_max_frame:
                max_frame_split.prop(self, "custom_max_frame", text="")
            else:
                box = max_frame_split.box()
                box.scale_y = 0.4
                box.label(text=f"{get_max_frame(action, self)}")
        if not dma:
            self.draw_references(col, export_type in {"Binary", "Insertable Binary"})

        if specific_variant is not None:
            col.separator()
            if specific_variant < 0 or specific_variant >= len(self.headers):
                col.box().label(text="Header variant does not exist.", icon="ERROR")
                return
            col.label(text="Variant Properties", icon="NLA")
            self.headers[specific_variant].draw_props(col, action, in_table, dma, export_type, actor_name, gen_enums)
        else:
            col.separator()

            self.draw_variants(col, action, in_table, dma, export_type, actor_name, gen_enums)


class TableElementProperty(PropertyGroup):
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

    def draw_reference(self, layout: UILayout, export_type: str = "C", gen_enums: bool = False):
        row = layout.row()
        if export_type in {"Binary", "Insertable Binary"}:
            string_int_prop(row, self, "header_address", "Header Address")
            return
        if gen_enums:
            text_row = row.row()
            text_row.alignment = "LEFT"
            text_row.label(text="Enum")
        prop_row = row.row()
        prop_row.alignment = "EXPAND"
        if gen_enums:
            prop_row.prop(self, "enum_name", text="")
        row.prop(self, "header_name", text="")

    def draw_props(
        self,
        row: UILayout,  # left side of the row for table ops
        prop_layout: UILayout,
        dma: bool,
        can_reference: bool,
        export_seperately: bool,
        export_type: str,
        gen_enums: bool,
        actor_name: str,
    ):
        col = prop_layout.column()
        if can_reference:
            reference_row = row.row()
            reference_row.alignment = "LEFT"
            reference_row.prop(self, "reference")
            if self.reference:
                self.draw_reference(col, export_type, gen_enums)
                return
        action_row = row.row()
        action_row.alignment = "EXPAND"
        action_row.prop(self, "action_prop", text="")

        if not self.action_prop:
            col.box().label(text="Header´s action does not exist.", icon="ERROR")
            return
        action = self.action_prop
        action_props: SM64_ActionProperty = action.fast64.sm64
        headers = action_props.headers
        variant = self.variant
        if 0 <= variant < len(headers):
            header_props = get_element_header(self, can_reference)
            name = get_anim_name(actor_name, action, header_props)
            if not draw_and_check_tab(col, self, "expand_tab", f"{name} (Variant {variant + 1})"):
                return
        row = col.row()
        row.alignment = "LEFT"
        row.prop(self, "variant")
        action_name = action.name
        draw_list_op(row, VariantOps, "REMOVE", variant, headers, True, action_name=action_name)
        draw_list_op(row, VariantOps, "ADD", variant, action_name=action_name)
        file_name = export_type == "C" and not dma and export_seperately
        action_props.draw_props(
            col,
            action,
            variant,
            True,
            file_name,
            export_type,
            actor_name,
            gen_enums,
            dma,
        )


class TableProperty(PropertyGroup):
    elements: CollectionProperty(type=TableElementProperty)

    export_seperately: BoolProperty(name="Export All Seperately")
    write_data_seperately: BoolProperty(name="Write Data Seperately")
    add_null_delimiter: BoolProperty(name="Add Null Delimiter")
    override_files_prop: BoolProperty(name="Override Table and Data Files", default=True)
    gen_enums: BoolProperty(name="Generate Enums", default=True)
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
        return not self.export_seperately or self.override_files_prop

    def draw_element(
        self,
        layout: UILayout,
        index: int,
        table_element: TableElementProperty,
        dma: bool,
        can_reference: bool,
        export_type: str,
        actor_name: str,
    ):
        col = layout.column()
        row = col.row()
        left_row = row.row()
        left_row.alignment = "EXPAND"
        op_row = row.row()
        op_row.alignment = "RIGHT"
        draw_list_ops(op_row, TableOps, index, self.elements)

        table_element.draw_props(
            left_row,
            col,
            dma,
            can_reference,
            self.export_seperately,
            export_type,
            self.gen_enums,
            actor_name,
        )

    def draw_non_exclusive_settings(self, layout: UILayout, dma: bool, export_type, actor_name: str):
        col = layout.column()
        if export_type == "C":
            col.prop(self, "gen_enums")
            name_split = col.split()
            name_split.prop(self, "use_custom_table_name")
            if self.use_custom_table_name:
                name_split.prop(self, "custom_table_name", text="")
            else:
                box = name_split.row().box()
                box.scale_y = 0.5
                box.label(text=get_table_name(self, actor_name))
        elif export_type == "Binary":
            if dma:
                string_int_prop(col, self, "dma_address", "DMA Table Address")
                string_int_prop(col, self, "dma_end_address", "DMA Table End")
                return
            string_int_prop(col, self, "address", "Table Address")
            string_int_prop(col, self, "end_address", "Table End")

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
        col.prop(self, "add_null_delimiter")

    def draw_props(self, layout: UILayout, dma: bool, non_exclusive: bool, export_type: str, actor_name: str):
        col = layout.column()
        if non_exclusive:
            self.draw_non_exclusive_settings(col, dma, export_type, actor_name)

        if not dma:
            if export_type == "Binary":
                col.prop(self, "write_data_seperately")
                if self.write_data_seperately:
                    string_int_prop(col, self, "data_address", "Data Address")
                    string_int_prop(col, self, "data_end_address", "Data End")
            elif export_type == "C":
                col.prop(self, "export_seperately")
                if self.export_seperately:
                    col.prop(self, "override_files_prop")
        if export_type == "Insertable Binary":
            prop_split(col, self, "insertable_file_name", "File Name")

        export_col = col.column()
        ExportAnimTable.draw_props(export_col)
        export_col.enabled = True if self.elements else False
        if dma and export_type == "C":
            multilineLabel(
                col,
                "The export will follow the vanilla DMA naming\n"
                "conventions (anim_xx.inc.c, anim_xx, anim_xx_values, etc).",
                icon="INFO",
            )
        export_col.separator()

        can_reference = not dma
        op_row = col.row()
        op_row.label(text="Headers" + (f" ({len(self.elements)})" if self.elements else ""), icon="NLA")
        draw_list_op(op_row, TableOps, "ADD")
        draw_list_op(op_row, TableOps, "CLEAR", collection=self.elements)
        if self.elements:
            box = col.box().column()
        actions = []  # for checking for duplicates
        element_props: TableElementProperty
        for i, element_props in enumerate(self.elements):
            if i != 0:
                box.separator()

            self.draw_element(box, i, element_props, dma, can_reference, export_type, actor_name)
            action = get_element_action(element_props, can_reference)
            if dma and action:
                duplicate_indeces = [str(j) for j, a in enumerate(actions) if a == action and j < i - 1]
                if duplicate_indeces:
                    multilineLabel(
                        box.box(),
                        "In DMA tables, headers for each action must be \n"
                        "in one sequence or the data will be duplicated.\n"
                        f'Data duplicate{"s in elements" if len(duplicate_indeces) > 1 else " in element"} '
                        + ", ".join(duplicate_indeces),
                        "INFO",
                    )
                actions.append(action)


class CleanAnimProperty(PropertyGroup):
    translation_threshold: FloatProperty(
        name="Threshold",
        default=1 / MAX_U16,
        min=0,
        max=0.01,
    )
    rotation_threshold: FloatProperty(
        name="Threshold",
        default=16 / MAX_U16,  # SM64's sine LUT is 1/16th of the full range
        min=0,
        max=0.01,
    )
    scale_threshold: FloatProperty(
        name="Threshold",
        default=1 / MAX_U16,
        min=0,
        max=0.01,
    )
    continuity_filter: BoolProperty(name="Continuity Filter", default=True)
    force_quaternion: BoolProperty(
        name="Force Quaternions", description="Changes bones to quaternion rotation mode, breaks existing actions"
    )

    def draw_props(self, layout: UILayout, tools_context: bool = True):
        col = layout.column()
        col.label(text="Thresholds")
        prop_split(col, self, "translation_threshold", "Translation", slider=True)
        prop_split(col, self, "rotation_threshold", "Rotation", slider=True)
        if tools_context:
            prop_split(col, self, "scale_threshold", "Scale", slider=True)
        col.separator()

        row = col.row()
        row.prop(self, "force_quaternion")
        continuity_row = row.row()
        continuity_row.enabled = not self.force_quaternion
        continuity_row.prop(
            self,
            "continuity_filter",
            text="Continuity Filter" + (" (Always on)" if self.force_quaternion else ""),
            invert_checkbox=not self.continuity_filter if self.force_quaternion else False,
        )
        if tools_context:
            CleanObjectAnim.draw_props(col)


class ImportProperty(PropertyGroup):
    clean_up: BoolProperty(name="Clean Up Keyframes", default=True)
    clean_up_props: PointerProperty(type=CleanAnimProperty)

    clear_table: BoolProperty(name="Clear Table On Import", default=True)
    import_type: EnumProperty(items=enumAnimImportTypes, name="Type", default="C")
    preset: bpy.props.EnumProperty(items=enumAnimationTables, name="Preset", default="Mario")
    decomp_path: StringProperty(name="Decomp Path", subtype="FILE_PATH", default="/home/user/sm64")
    binary_import_type: EnumProperty(items=enumAnimBinaryImportTypes, name="Type", default="Table")
    assume_bone_count: BoolProperty(
        name="Assume Bone Count",
        description="When enabled, the selected armature's bone count will be used instead of "
        "the header's, as old fast64 binary exports did no export this value",
    )
    read_entire_table: BoolProperty(name="Read Entire Table", default=True)
    check_null: BoolProperty(name="Check NULL Delimiter", default=True)
    table_size_prop: IntProperty(name="Size", min=1)
    table_index_prop: IntProperty(name="Index", min=0)
    mario_animation: EnumProperty(name="Selected Preset Mario Animation", items=marioAnimationNames)

    rom: StringProperty(name="Import ROM", subtype="FILE_PATH")
    table_address: StringProperty(name="Address", default=intToHex(0x0600FC48))  # Toad
    animation_address: StringProperty(name="Address", default=intToHex(0x0600B75C))
    is_segmented_address_prop: BoolProperty(name="Is Segmented Address", default=True)
    level: EnumProperty(items=level_enums, name="Level", default="IC")
    dma_table_address: StringProperty(name="DMA Table Address", default="0x4EC000")

    read_from_rom: BoolProperty(
        name="Read From Import ROM",
        description="When enabled, the importer will read from the import ROM given a non defined address",
    )

    path: StringProperty(name="Path", subtype="FILE_PATH", default="anims/")
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
        if self.import_type != "Binary":
            return
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
        col.prop(self, "use_custom_name")

    def draw_import_rom(self, layout: UILayout, import_rom: PathLike = ""):
        col = layout.column()
        col.label(text="Uses scene import ROM by default", icon="INFO")
        prop_split(col, self, "rom", "Import ROM")
        picked_rom = abspath(self.rom if self.rom else import_rom)
        return import_rom_ui_warnings(col, picked_rom)

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
            right_row.prop(self, "table_size_prop")

    def draw_binary(self, layout: UILayout, import_rom: PathLike):
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
            string_int_prop(col, self, "dma_table_address", "DMA Table Address")
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

    def draw_insertable_binary(self, layout: UILayout, import_rom: PathLike):
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

    def draw_props(self, layout: UILayout, import_rom: PathLike = None):
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
            self.clean_up_props.draw_props(col.box(), False)
        ImportAnim.draw_props(col)


class AnimProperty(PropertyGroup):
    version: bpy.props.IntProperty(name="AnimProperty Version", default=0)
    cur_version = 1  # version after property migration

    played_header: IntProperty(min=0)
    played_action: PointerProperty(name="Action", type=Action)

    table: PointerProperty(type=TableProperty)
    importing: PointerProperty(type=ImportProperty)
    selected_action: PointerProperty(name="Action", type=Action)
    clean_up: PointerProperty(type=CleanAnimProperty)

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
        importing: ImportProperty = self.importing

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
            action_props: SM64_ActionProperty = action.fast64.sm64
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
        table: TableProperty = self.table
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
            anim_props: AnimProperty = scene.fast64.sm64.animation
            if anim_props.version == 0:
                anim_props.update_version_0(scene)

    @property
    def actor_name(self):
        return self.actor_name_prop if self.header_type != "DMA" else None

    @property
    def is_c_dma(self):
        return self.use_dma_structure if self.header_type == "Custom" else self.header_type == "DMA"

    def is_dma(self, export_type: str):
        is_binary = export_type in {"Binary", "Insertable Binary"}
        return (is_binary and self.is_binary_dma) or (not is_binary and self.is_c_dma)

    def updates_table(self, export_type: str):
        return self.update_table and export_type != "Insertable Binary"

    @property
    def level_name(self):
        return self.custom_level_name if self.level_option == "Custom" else self.level_option

    def get_c_paths(self, decomp: PathLike) -> tuple[PathLike, PathLike, PathLike]:
        custom_export = self.header_type == "Custom"
        base_path = self.directory_path if custom_export else decomp
        if self.is_c_dma:  # DMA or Custom with DMA structure
            return (abspath(os.path.join(base_path, self.dma_folder)), "", "")
        dir_name = toAlnum(self.actor_name)
        header_directory = abspath(
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
        geo_directory = abspath(os.path.join(header_directory, dir_name))
        anim_directory = abspath(os.path.join(geo_directory, "anims"))
        return (anim_directory, geo_directory, header_directory)

    def draw_non_exclusive_settings(self, layout: UILayout, is_dma: bool, export_type: str):
        col = layout.column()
        if is_dma and export_type == "C" or export_type == "Insertable Binary":
            return

        is_binary_dma = export_type == "Binary" and self.is_binary_dma
        if not is_binary_dma:
            col.prop(self, "update_table")
        if self.update_table or is_binary_dma:
            box = col.box().column()
            box.label(text="Table Settings:", icon="ANIM")
            self.table.draw_non_exclusive_settings(box, is_dma, export_type, self.actor_name)

    def draw_binary_settings(self, layout: UILayout, export_type: str):
        col = layout.column()
        col.prop(self, "is_binary_dma")
        if export_type == "Insertable Binary":
            prop_split(col, self, "directory_path", "Directory")
            directory_ui_warnings(col, abspath(self.directory_path))
        else:
            if self.is_binary_dma:
                layout.prop(self, "assume_bone_count")
            else:
                layout.prop(self, "binary_level")

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

    def draw_table(self, layout: UILayout, export_type: str):
        dma = self.is_dma(export_type)
        draw_exclusive = not self.updates_table(export_type)
        self.table.draw_props(layout, dma, draw_exclusive, export_type, self.actor_name)

    def draw_action(self, layout: UILayout, export_type: str, armature: Object):
        is_dma = self.is_dma(export_type)
        file_name, gen_enums = export_type != "Binary", self.table.gen_enums
        col = layout.column()

        if armature:
            col.label(text=f'Uses "{armature.name}"\'s action by default', icon="INFO")

        split = col.split()
        split.prop(self, "selected_action")
        try:
            action = get_selected_action(self, armature)
            action_props: SM64_ActionProperty = action.fast64.sm64
            action_props.draw_props(
                col, action, None, False, file_name, export_type, self.actor_name, gen_enums, is_dma
            )
        except ValueError as exc:
            multilineLabel(col, str(exc), "ERROR")

    def draw_export_settings(self, layout: UILayout, export_type: str):
        col = layout.column()
        if export_type in {"Binary", "Insertable Binary"}:
            self.draw_binary_settings(col, export_type)
        elif export_type == "C":
            self.draw_c_settings(col)
        col.prop(self, "quick_read")
        col.separator()

        self.draw_non_exclusive_settings(col, self.is_dma(export_type), export_type)

    def draw_tools(self, layout: UILayout):
        col = layout.column()
        col.label(text="Clean Up Keyframes", icon="KEYFRAME")
        self.clean_up.draw_props(col)

    def draw_props(self, layout: UILayout, export_type: str):
        col = layout.column()
        self.draw_export_settings(col, export_type)


properties = (
    HeaderProperty,
    TableElementProperty,
    SM64_ActionProperty,
    TableProperty,
    CleanAnimProperty,
    ImportProperty,
    AnimProperty,
)


def anim_props_register():
    for cls in properties:
        register_class(cls)


def anim_props_unregister():
    for cls in reversed(properties):
        unregister_class(cls)
