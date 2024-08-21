import os
from os import PathLike
import re
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
    decompFolderMessage,
    directory_ui_warnings,
    path_ui_warnings,
    draw_and_check_tab,
    multilineLabel,
    prop_split,
    toAlnum,
    intToHex,
    upgrade_old_prop,
)
from ..sm64_utility import import_rom_ui_warnings, string_int_prop, string_int_warning
from ..sm64_constants import MAX_U16, MIN_S16, MAX_S16, level_enums

from .operators import (
    OperatorBase,
    SM64_PreviewAnim,
    SM64_AnimTableOps,
    SM64_AnimVariantOps,
    SM64_ImportAnim,
    SM64_SearchAnimPresets,
    SM64_SearchAnimatedBhvs,
    SM64_SearchAnimTablePresets,
)
from .constants import (
    enumAnimImportTypes,
    enumAnimBinaryImportTypes,
    enumAnimatedBehaviours,
    enumAnimationTables,
)
from .utility import (
    get_anim_enum,
    get_max_frame,
    get_anim_name,
    get_dma_anim_name,
    get_element_action,
    get_element_header,
)
from .importing import get_enum_from_import_preset


def draw_custom_or_auto(holder, layout: UILayout, prop: str, default: str):
    use_custom_prop = "use_custom_" + prop
    name_split = layout.split()
    name_split.prop(holder, use_custom_prop)
    if getattr(holder, use_custom_prop):
        name_split.prop(holder, "custom_" + prop, text="")
    else:
        box = name_split.box()
        box.scale_y = 0.5
        box.label(text=default, icon="LOCKED")


def draw_forced(layout: UILayout, holder, prop: str, forced: bool):
    row = layout.row(align=True) if forced else layout.column()
    if forced:
        box = row.box()
        box.scale_y = 0.5
        box.label(text="", icon="LOCKED")
    row.alignment = "LEFT"
    row.enabled = not forced
    row.prop(holder, prop, invert_checkbox=not holder.get(prop) if forced else False)


def draw_list_op(
    layout: UILayout,
    op_cls: OperatorBase,
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
    return op_cls.draw_props(col, icon, text, index=index, op_name=op_name, **op_args)


def draw_list_ops(layout: UILayout, op_cls: type, index: int, collection: Optional[Iterable], **op_args):
    layout.label(text=str(index))
    ops = ("MOVE_UP", "MOVE_DOWN", "ADD", "REMOVE")
    for op_name in ops:
        draw_list_op(layout, op_cls, op_name, index, collection, **op_args)


class SM64_AnimHeaderProperties(PropertyGroup):
    expand_tab_in_action: BoolProperty(name="Header Properties", default=True)
    header_variant: IntProperty(name="Header Variant Number", min=0)

    use_custom_name: BoolProperty(name="Name")
    custom_name: StringProperty(name="Name", default="anim_00")
    use_custom_enum: BoolProperty(name="Enum")
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
            draw_custom_or_auto(self, col, "enum", get_anim_enum(actor_name, action, self))
        draw_custom_or_auto(self, col, "name", get_anim_name(actor_name, action, self))

    def draw_props(
        self,
        layout: UILayout,
        action: Action,
        in_table: bool,
        updates_table: bool,
        dma: bool,
        export_type: str,
        actor_name: str,
        gen_enums: bool,
    ):
        col = layout.column()
        split = col.split()
        preview_op = SM64_PreviewAnim.draw_props(split)
        preview_op.played_header = self.header_variant
        preview_op.played_action = action.name
        if not in_table:  # Don´t show index or name in table props
            draw_list_op(
                split,
                SM64_AnimTableOps,
                "ADD",
                text="Add To Table",
                icon="LINKED",
                action_name=action.name,
                header_variant=self.header_variant,
            )
            if export_type == "Binary" and updates_table:  # Only show table index if table will be updated
                prop_split(col, self, "table_index", "Table Index")
            elif export_type == "C":
                self.draw_names(col, action, actor_name, gen_enums)
        col.separator()

        prop_split(col, self, "trans_divisor", "Translation Divisor")
        self.draw_frame_range(col)
        self.draw_flag_props(col, use_int_flags=dma or export_type in {"Binary", "Insertable Binary"})


class SM64_ActionProperty(PropertyGroup):  # TODO:Should this be SM64_ActionAnimProperties
    header: PointerProperty(type=SM64_AnimHeaderProperties)
    variants_tab: BoolProperty(name="Header Variants")
    header_variants: CollectionProperty(type=SM64_AnimHeaderProperties)
    use_custom_file_name: BoolProperty(name="File Name")
    custom_file_name: StringProperty(name="File Name", default="anim_00.inc.c")
    use_custom_max_frame: BoolProperty(name="Max Frame")
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
    def headers(self) -> list[SM64_AnimHeaderProperties]:
        return [self.header] + list(self.header_variants)

    def get_file_name(self, action: Action, export_type: str) -> str:
        if not export_type in {"C", "Insertable Binary"}:
            return ""
        if self.use_custom_file_name:
            return self.custom_file_name
        else:
            name = f"anim_{action.name}."
            if export_type == "C":
                name += "inc.c"
            else:
                name += "insertable"
            # Replace any invalid characters with an underscore, TODO: Could this be an issue anywhere else in fast64?
            name = re.sub(r'[/\\?%*:|"<>]', " ", name)
            return name

    def draw_variants(
        self,
        layout: UILayout,
        action: Action,
        actor_name: str,
        header_args: list,
    ):
        col = layout.column()
        op_row = col.row()
        op_row.label(text=f"Header Variants ({len(self.headers)})", icon="NLA")
        draw_list_op(op_row, SM64_AnimVariantOps, "CLEAR", -1, self.headers, True, action_name=action.name)

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
                header.draw_props(col, *header_args)
            op_row = row.row()
            op_row.alignment = "RIGHT"
            draw_list_ops(op_row, SM64_AnimVariantOps, i, self.headers, keep_first=True, action_name=action.name)

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

    def draw_props(
        self,
        layout: UILayout,
        action: Action,
        specific_variant: int | None,
        in_table: bool,
        updates_table: bool,
        draw_file_name: bool,
        export_type: str,
        actor_name: str,
        gen_enums: bool,
        dma: bool,
    ):
        # Args to pass to the headers
        header_args = (action, in_table, updates_table, dma, export_type, actor_name, gen_enums)

        col = layout.column()
        if specific_variant is not None:
            col.label(text="Action Properties", icon="ACTION")
        if not in_table:
            draw_list_op(
                col,
                SM64_AnimTableOps,
                "ADD_ALL",
                text="Add All Variants To Table",
                icon="LINKED",
                action_name=action.name,
            )
            col.separator()

            if export_type == "Binary" and not dma:
                string_int_prop(col, self, "start_address", "Start Address")
                string_int_prop(col, self, "end_address", "End Address")
        if draw_file_name:
            draw_custom_or_auto(self, col, "file_name", self.get_file_name(action, export_type))
        if dma or not self.reference_tables:  # DMA tables don´t allow references
            draw_custom_or_auto(self, col, "max_frame", str(get_max_frame(action, self)))
        if not dma:
            self.draw_references(col, export_type in {"Binary", "Insertable Binary"})
        col.separator()

        if specific_variant is not None:
            if specific_variant < 0 or specific_variant >= len(self.headers):
                col.box().label(text="Header variant does not exist.", icon="ERROR")
            else:
                col.label(text="Variant Properties", icon="NLA")
                self.headers[specific_variant].draw_props(col, *header_args)
        else:
            self.draw_variants(col, action, actor_name, header_args)


class SM64_AnimTableElement(PropertyGroup):
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
        index: int,
        dma: bool,
        updates_table: bool,
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
            if dma:
                name = get_dma_anim_name(index)
            else:
                name = get_anim_name(actor_name, action, header_props)
            if not draw_and_check_tab(col, self, "expand_tab", f"{name} (Variant {variant + 1})"):
                return
        row = col.row()
        row.alignment = "LEFT"
        row.prop(self, "variant")
        draw_list_op(row, SM64_AnimVariantOps, "REMOVE", variant, headers, True, action_name=action.name)
        draw_list_op(row, SM64_AnimVariantOps, "ADD", variant, action_name=action.name)
        action_props.draw_props(
            layout=col,
            action=action,
            specific_variant=variant,
            in_table=True,
            updates_table=True,
            draw_file_name=export_type == "C" and not dma and export_seperately,
            export_type=export_type,
            actor_name=actor_name,
            gen_enums=gen_enums,
            dma=dma,
        )


class SM64_AnimTableProperties(PropertyGroup):  # TODO: Should this be moved to armature anim props?
    elements: CollectionProperty(type=SM64_AnimTableElement)

    export_seperately: BoolProperty(name="Export All Seperately")
    write_data_seperately: BoolProperty(name="Write Data Seperately")
    null_delimiter: BoolProperty(name="Add Null Delimiter")
    override_files_prop: BoolProperty(name="Override Table and Data Files", default=True)
    gen_enums: BoolProperty(name="Generate Enums", default=True)
    use_custom_table_name: BoolProperty(name="Table Name")
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

    def get_name(self, actor_name: str) -> str:
        if self.use_custom_table_name:
            return self.custom_table_name
        return f"{actor_name}_anims"

    def get_table_actions(self, can_reference: bool) -> list[Action]:
        actions = []
        for element_props in self.elements:
            action = get_element_action(element_props, can_reference)
            if action and action not in actions:
                actions.append(action)
        return actions

    def draw_element(
        self,
        layout: UILayout,
        index: int,
        table_element: SM64_AnimTableElement,
        dma: bool,
        updates_table: bool,
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
        draw_list_ops(op_row, SM64_AnimTableOps, index, self.elements)

        table_element.draw_props(
            left_row,
            col,
            index,
            dma,
            updates_table,
            can_reference,
            self.export_seperately,
            export_type,
            self.gen_enums,
            actor_name,
        )

    def draw_props(self, layout: UILayout, dma: bool, updates_table: bool, export_type: str, actor_name: str):
        col = layout.column()

        if dma:
            if export_type == "Binary":
                string_int_prop(col, self, "dma_address", "DMA Table Address")
                string_int_prop(col, self, "dma_end_address", "DMA Table End")
            elif export_type == "C":
                multilineLabel(
                    col,
                    "The export will follow the vanilla DMA naming\n"
                    "conventions (anim_xx.inc.c, anim_xx, anim_xx_values, etc).",
                    icon="INFO",
                )
        else:
            if export_type == "C":
                col.prop(self, "gen_enums")
                draw_custom_or_auto(self, col, "table_name", self.get_name(actor_name))
                col.prop(self, "export_seperately")
                draw_forced(col, self, "override_files_prop", not self.export_seperately)
            elif export_type == "Binary":
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
                    SM64_SearchAnimatedBhvs.draw_props(box, self, "behaviour", "Behaviour")
                    if self.behaviour == "Custom":
                        prop_split(box, self, "behavior_address_prop", "Behavior Address")
                    prop_split(box, self, "begining_animation", "Beginning Animation")

                col.prop(self, "write_data_seperately")
                if self.write_data_seperately:
                    string_int_prop(col, self, "data_address", "Data Address")
                    string_int_prop(col, self, "data_end_address", "Data End")
            col.prop(self, "null_delimiter")
        if export_type == "Insertable Binary":
            prop_split(col, self, "insertable_file_name", "File Name")

        col.separator()

        can_reference = not dma
        op_row = col.row()
        op_row.label(text="Headers" + (f" ({len(self.elements)})" if self.elements else ""), icon="NLA")
        draw_list_op(op_row, SM64_AnimTableOps, "ADD")
        draw_list_op(op_row, SM64_AnimTableOps, "CLEAR", collection=self.elements)
        if self.elements:
            box = col.box().column()
        actions = []  # for checking for dma duplicates
        element_props: SM64_AnimTableElement
        for i, element_props in enumerate(self.elements):
            if i != 0:
                box.separator()

            self.draw_element(box, i, element_props, dma, updates_table, can_reference, export_type, actor_name)
            action = get_element_action(element_props, can_reference)
            if dma and action:
                duplicate_indeces = [str(j) for j, a in enumerate(actions) if a == action and j < i - 1]
                if duplicate_indeces:  # TODO: Should this show up once at the top instead?
                    multilineLabel(
                        box.box(),
                        "In DMA tables, headers for each action must be \n"
                        "in one sequence or the data will be duplicated.\n"
                        f'Data duplicate{"s in elements" if len(duplicate_indeces) > 1 else " in element"} '
                        + ", ".join(duplicate_indeces),
                        "INFO",
                    )
            actions.append(action)


class SM64_AnimImportProperties(PropertyGroup):
    run_decimate: BoolProperty(name="Run Decimate (Allowed Change)", default=True)
    decimate_margin: FloatProperty(
        name="Error Margin",
        default=0.025,
        min=0.0,
        max=0.025,
        description="Use blender's builtin decimate (allowed change) operator to clean up all the keyframes, generally the better option compared to clean keyframes but can be slow",
    )

    continuity_filter: BoolProperty(name="Continuity Filter", default=True)
    force_quaternion: BoolProperty(
        name="Force Quaternions", description="Changes bones to quaternion rotation mode, can break actions"
    )

    clear_table: BoolProperty(name="Clear Table On Import", default=True)
    import_type: EnumProperty(items=enumAnimImportTypes, name="Type", default="C")
    preset: bpy.props.EnumProperty(items=enumAnimationTables, name="Preset", default="Mario")
    decomp_path: StringProperty(name="Decomp Path", subtype="FILE_PATH", default="")
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
    preset_animation: EnumProperty(name="Selected Preset Animation", items=get_enum_from_import_preset)

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
    def table_index(self):
        return (
            None
            if self.read_entire_table
            else int(self.preset_animation, 0)
            if self.preset_animation != "Custom" and self.import_type != "Insertable Binary"
            else self.table_index_prop
        )

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

    def draw_clean_up(self, layout: UILayout):
        col = layout.column()
        col.prop(self, "run_decimate")
        if self.run_decimate:
            prop_split(col, self, "decimate_margin", "Error Margin")
            col.box().label(text="While very useful and stable, it can be very slow", icon="INFO")
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

    def draw_path(self, layout: UILayout):
        prop_split(layout, self, "path", "Directory or File Path")
        path_ui_warnings(layout, abspath(self.path))

    def draw_c(self, layout: UILayout, decomp_path: PathLike = ""):
        col = layout.column()
        if self.preset == "Custom":
            self.draw_path(col)
        else:
            col.label(text="Uses scene decomp path by default", icon="INFO")
            prop_split(col, self, "decomp_path", "Decomp Path")
            picked_decomp_path = abspath(self.decomp_path if self.decomp_path else decomp_path)
            directory_ui_warnings(col, picked_decomp_path)
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
                SM64_SearchAnimPresets.draw_props(split, self, "preset_animation", "")
                if self.preset_animation == "Custom":
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

    def draw_props(self, layout: UILayout, import_rom: PathLike = None, decomp_path: PathLike = None):
        col = layout.column()

        prop_split(col, self, "import_type", "Type")

        if self.import_type in {"C", "Binary"}:
            SM64_SearchAnimTablePresets.draw_props(col, self, "preset", "Preset")
            col.separator()

        if self.import_type == "C":
            self.draw_c(col, decomp_path)
        elif self.import_type in {"Binary", "Insertable Binary"}:
            if self.import_type == "Binary":
                self.draw_binary(col, import_rom)
            elif self.import_type == "Insertable Binary":
                self.draw_insertable_binary(col, import_rom)
            col.prop(self, "assume_bone_count")
        col.separator()

        self.draw_clean_up(col)
        col.prop(self, "clear_table")
        SM64_ImportAnim.draw_props(col)


class SM64_AnimProperties(PropertyGroup):
    version: IntProperty(name="SM64_AnimProperties Version", default=0)
    cur_version = 1  # version after property migration

    played_header: IntProperty(min=0)
    played_action: PointerProperty(name="Action", type=Action)

    importing: PointerProperty(type=SM64_AnimImportProperties)
    selected_action: PointerProperty(name="Action", type=Action)

    def update_version_0(self, scene: Scene):
        importing: SM64_AnimImportProperties = self.importing

        upgrade_old_prop(importing, "animation_address", scene, "animStartImport", fix_forced_base_16=True)
        upgrade_old_prop(importing, "is_segmented_address_prop", scene, "animIsSegPtr")
        upgrade_old_prop(importing, "level", scene, "levelAnimImport")
        upgrade_old_prop(importing, "table_index_prop", scene, "animListIndexImport")
        if scene.pop("isDMAImport", False):
            importing.binary_import_type = "DMA"
        elif scene.pop("animIsAnimList", True):
            importing.binary_import_type = "Table"
        # Export
        loop = scene.pop("loopAnimation", False)
        for action in bpy.data.actions:
            action_props: SM64_ActionProperty = action.fast64.sm64
            action_props.header.no_loop = not loop
            upgrade_old_prop(action_props, "start_address", scene, "animExportStart", fix_forced_base_16=True)
            upgrade_old_prop(action_props, "start_address", scene, "animExportStart", fix_forced_base_16=True)
            upgrade_old_prop(action_props, "end_address", scene, "animExportEnd", fix_forced_base_16=True)
        custom_export = scene.pop("animCustomExport", False)
        if custom_export:
            self.header_type = "Custom"
        else:
            upgrade_old_prop(self, "header_type", scene, "animExportHeaderType")

        self.directory_path = scene.get("animExportPath", self.directory_path)
        upgrade_old_prop(self, "directory_path", scene, "animExportPath")
        upgrade_old_prop(self, "actor_name_prop", scene, "animName")
        upgrade_old_prop(self, "group_name", scene, "animGroupName")
        upgrade_old_prop(self, "level_option", scene, "animLevelOption")
        upgrade_old_prop(self, "custom_level_name", scene, "animLevelName")
        upgrade_old_prop(self, "is_dma", scene, "isDMAExport")
        upgrade_old_prop(self, "binary_level", scene, "levelAnimExport")

        insertable_directory_path = scene.pop("animInsertableBinaryPath", "")
        if insertable_directory_path:
            # Ignores file name
            self.insertable_directory_path = os.path.split(insertable_directory_path)[0]

        upgrade_old_prop(self, "update_table", scene, "setAnimListIndex")
        table: SM64_AnimTableProperties = self.table
        # upgrade_old_prop(table, "", scene, "addr_0x27", fix_forced_base_16=True)
        # upgrade_old_prop(table, "", scene, "addr_0x28", fix_forced_base_16=True)
        upgrade_old_prop(table, "update_behavior", scene, "overwrite_0x28")
        upgrade_old_prop(table, "begining_animation", scene, "animListIndexExport")

        self.version = 1

    def upgrade_changed_props(self, scene):
        if self.version == 0:
            self.update_version_0(scene)
        self.version = SM64_AnimProperties.cur_version


class SM64_ArmatureAnimProperties(PropertyGroup):
    version: IntProperty(name="SM64_AnimProperties Version", default=0)
    cur_version = 1  # version after property migration

    # Revise locations of props
    is_dma: BoolProperty(name="Is DMA Export")
    dma_folder: StringProperty(name="DMA Folder", default="assets/anims/")
    update_table: BoolProperty(
        name="Update Table On Action Export",
        description="Update table outside of table exports",
        default=True,
    )
    table: PointerProperty(type=SM64_AnimTableProperties)

    def update_version_0(self, scene: Scene):
        importing: SM64_AnimImportProperties = self.importing

        upgrade_old_prop(importing, "animation_address", scene, "animStartImport", fix_forced_base_16=True)
        upgrade_old_prop(importing, "is_segmented_address_prop", scene, "animIsSegPtr")
        upgrade_old_prop(importing, "level", scene, "levelAnimImport")
        upgrade_old_prop(importing, "table_index_prop", scene, "animListIndexImport")
        if scene.pop("isDMAImport", False):
            importing.binary_import_type = "DMA"
        elif scene.pop("animIsAnimList", True):
            importing.binary_import_type = "Table"
        # Export
        loop = scene.pop("loopAnimation", False)
        for action in bpy.data.actions:
            action_props: SM64_ActionProperty = action.fast64.sm64
            action_props.header.no_loop = not loop
            upgrade_old_prop(action_props, "start_address", scene, "animExportStart", fix_forced_base_16=True)
            upgrade_old_prop(action_props, "start_address", scene, "animExportStart", fix_forced_base_16=True)
            upgrade_old_prop(action_props, "end_address", scene, "animExportEnd", fix_forced_base_16=True)
        custom_export = scene.pop("animCustomExport", False)
        if custom_export:
            self.header_type = "Custom"
        else:
            upgrade_old_prop(self, "header_type", scene, "animExportHeaderType")

        self.directory_path = scene.get("animExportPath", self.directory_path)
        upgrade_old_prop(self, "directory_path", scene, "animExportPath")
        upgrade_old_prop(self, "actor_name_prop", scene, "animName")
        upgrade_old_prop(self, "group_name", scene, "animGroupName")
        upgrade_old_prop(self, "level_option", scene, "animLevelOption")
        upgrade_old_prop(self, "custom_level_name", scene, "animLevelName")
        upgrade_old_prop(self, "is_dma", scene, "isDMAExport")
        upgrade_old_prop(self, "binary_level", scene, "levelAnimExport")

        insertable_directory_path = scene.pop("animInsertableBinaryPath", "")
        if insertable_directory_path:
            # Ignores file name
            self.insertable_directory_path = os.path.split(insertable_directory_path)[0]

        upgrade_old_prop(self, "update_table", scene, "setAnimListIndex")
        table: SM64_AnimTableProperties = self.table
        # upgrade_old_prop(table, "", scene, "addr_0x27", fix_forced_base_16=True)
        # upgrade_old_prop(table, "", scene, "addr_0x28", fix_forced_base_16=True)
        upgrade_old_prop(table, "update_behavior", scene, "overwrite_0x28")
        upgrade_old_prop(table, "begining_animation", scene, "animListIndexExport")

        self.version = 1

    def upgrade_changed_props(self, scene):
        if self.version == 0:
            self.update_version_0(scene)
        self.version = SM64_AnimProperties.cur_version

    def draw_c_settings(self, layout: UILayout, header_type: str):
        col = layout.column()
        if self.is_dma:
            prop_split(col, self, "dma_folder", "Folder", icon="FILE_FOLDER")
            if header_type == "Custom":
                col.label(text="This folder will be relative to your custom path")
            else:
                decompFolderMessage(col)
            return

    def draw_props(self, layout: UILayout, export_type: str, header_type: str):
        col = layout.column()
        col.prop(self, "is_dma")
        if export_type == "C":
            self.draw_c_settings(col, header_type)
        else:
            col.prop(self, "update_table")


classes = (
    SM64_AnimHeaderProperties,
    SM64_AnimTableElement,
    SM64_ActionProperty,
    SM64_AnimTableProperties,
    SM64_AnimImportProperties,
    SM64_AnimProperties,
    SM64_ArmatureAnimProperties,
)


def anim_props_register():
    for cls in classes:
        register_class(cls)


def anim_props_unregister():
    for cls in reversed(classes):
        unregister_class(cls)
