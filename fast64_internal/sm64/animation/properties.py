import os
import re
from typing import Optional

import bpy
from bpy.types import PropertyGroup, Action, UILayout, Object, Scene
from bpy.utils import register_class, unregister_class
from bpy.props import (
    BoolProperty,
    StringProperty,
    EnumProperty,
    IntProperty,
    CollectionProperty,
    PointerProperty,
)
from bpy.path import abspath

from ...utility_anim import getFrameInterval
from ...utility import (
    PluginError,
    customExportWarning,
    decompFolderMessage,
    directory_ui_warnings,
    getExportDir,
    getPathAndLevel,
    makeWriteInfoBox,
    multilineLabel,
    path_ui_warnings,
    prop_split,
    toAlnum,
    writeBoxExportType,
    is_bit_active,
)
from ..sm64_utility import import_rom_checks
from ..sm64_constants import (
    MAX_U16,
    MIN_S16,
    MAX_S16,
    level_enums,
    enumLevelNames,
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
from .classes import SM64_Anim, SM64_AnimData, SM64_AnimHeader, SM64_AnimTable, SM64_AnimTableElement
from .constants import (
    enumAnimImportTypes,
    enumAnimBinaryImportTypes,
    marioAnimationNames,
    enumAnimExportTypes,
    C_FLAGS,
    FLAG_PROPS,
)
from .utility import get_anim_pose_bones, eval_num_from_str
from .exporting import get_animation_pairs


class SM64_AnimHeaderProps(PropertyGroup):
    expand_tab_in_action: BoolProperty(name="Header Properties", default=True)

    header_variant: IntProperty(name="Header Variant Number", min=0)

    override_name: BoolProperty(name="Override Name")
    custom_name: StringProperty(name="Name", default="anim_00")

    manual_frame_range: BoolProperty(name="Manual Frame Range")
    start_frame: IntProperty(name="Start Frame", min=0, max=MAX_S16)
    loop_start: IntProperty(name="Loop Start", min=0, max=MAX_S16)
    loop_end: IntProperty(name="Loop End", min=0, max=MAX_S16)

    trans_divisor: IntProperty(
        name="Translation Divisor",
        description="(animYTransDivisor)\n"
        "If set to 0, the translation multiplier will be 1.\n"
        "Otherwise, the translation multiplier is determined by dividing the object's"
        "translation dividend (animYTrans) by this divisor",
        min=MIN_S16,
        max=MAX_S16,
    )

    # Flags
    no_loop: BoolProperty(
        name="No Loop",
        description="(ANIM_FLAG_NOLOOP)\n"
        "When enabled, the animation will not repeat from the loop start after reaching the loop "
        "end frame",
    )
    backwards: BoolProperty(
        name="Backwards",
        description="(ANIM_FLAG_FORWARD or ANIM_FLAG_BACKWARD in refresh 16\n"
        "When enabled, the animation will loop (or stop if looping is disabled) after reaching "
        "the loop start frame.\n"
        "Tipically used with animations which use acceleration to play an animation backwards",
    )
    no_acceleration: BoolProperty(
        name="No Acceleration",
        description="(ANIM_FLAG_NO_ACCEL)\n"
        "When enabled, acceleration will not be used when calculating which animation frame is "
        "next",
    )
    disabled: BoolProperty(
        name="No Shadow Translation",
        description="(ANIM_FLAG_DISABLED)\n"
        "When enabled, the animation translation "
        "will not be applied to shadows",
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
        description="(ANIM_FLAG_NO_TRANS)\n"
        "When enabled, the animation translation will not be used during rendering "
        "(shadows included), the data will still be exported and included",
    )
    set_custom_flags: BoolProperty(name="Set Custom Flags")
    custom_flags: StringProperty(name="Flags", default="ANIM_NO_LOOP")
    custom_int_flags: StringProperty(name="Flags", default="0x01")

    override_enum: BoolProperty(name="Override Enum")
    custom_enum: StringProperty(name="Enum", default="ANIM_00")

    # Binary
    overwrite0x28: BoolProperty(name="Overwrite 0x28 behaviour command", default=True)
    setListIndex: BoolProperty(name="Set List Entry", default=True)
    addr0x27: StringProperty(name="0x27 Command Address", default=hex(2215168))
    addr0x28: StringProperty(name="0x28 Command Address", default=hex(2215176))
    table_index: IntProperty(name="Table Index", min=0, max=255)

    def get_frame_range(self, action: Action):
        if self.manual_frame_range:
            return self.start_frame, self.loop_start, self.loop_end

        if not action:
            raise PluginError("Cannot auto generate a frame range without a provided action")
        loop_start, loop_end = getFrameInterval(action)
        return 0, loop_start, loop_end + 1

    def get_anim_name(self, actor_name: str, action: Action):
        if self.override_name:
            return self.custom_name
        if self.header_variant == 0:
            if actor_name:
                name = f"{actor_name}_anim_{action.name}"
            else:
                name = f"anim_{action.name}"
        else:
            main_header_name = action.fast64.sm64.headers[0].get_anim_name(actor_name, action)
            name = f"{main_header_name}_{self.header_variant}"

        return toAlnum(name)

    def get_anim_enum(self, actor_name: str, action: Action):
        if self.override_enum:
            return self.custom_enum
        else:
            anim_name = self.get_anim_name(actor_name, action)
            enum_name = anim_name.upper()
            if anim_name == enum_name:
                enum_name = f"_{enum_name}"
            return enum_name

    def get_int_flags(self):
        flags: int = 0
        if self.no_loop:
            flags |= 1 << 0
        if self.backwards:
            flags |= 1 << 1
        if self.no_acceleration:
            flags |= 1 << 2
        if self.only_horizontal_trans:
            flags |= 1 << 3
        if self.only_vertical_trans:
            flags |= 1 << 4
        if self.disabled:
            flags |= 1 << 5
        if self.no_trans:
            flags |= 1 << 6

        return flags

    def to_header_class(
        self,
        bone_count: int,
        data: SM64_AnimData,
        action: Action,
        use_int_flags: bool = False,
        values_reference: Optional[int | str] = None,
        indice_reference: Optional[int | str] = None,
        actor_name: str | None = "mario",
        generate_enums: bool = False,
        file_name: str | None = "anim_00.inc.c",
    ):
        header = SM64_AnimHeader()
        header.reference = self.get_anim_name(actor_name, action)
        if generate_enums:
            header.enum_reference = self.get_anim_enum(actor_name, action)

        if self.set_custom_flags:
            if use_int_flags:
                header.flags = eval_num_from_str(self.custom_int_flags)
            else:
                header.flags = self.custom_flags
        else:
            header.flags = self.get_int_flags()

        start_frame, loop_start, loop_end = self.get_frame_range(action)

        header.trans_divisor = self.trans_divisor
        header.start_frame = start_frame
        header.loop_start = loop_start
        header.loop_end = loop_end
        header.values_reference = values_reference
        header.indice_reference = indice_reference
        header.bone_count = bone_count
        header.file_name = file_name

        header.data = data

        return header

    def from_header_class(
        self,
        header: SM64_AnimHeader,
        action: Action,
        actor_name: str = "mario",
        use_custom_name: bool = True,
    ):
        if (
            isinstance(header.reference, str)
            and header.reference != self.get_anim_name(actor_name, action)
            and use_custom_name
        ):
            self.custom_name = header.reference
            self.override_name = True

        correct_frame_range = header.start_frame, header.loop_start, header.loop_end
        self.start_frame, self.loop_start, self.loop_end = correct_frame_range
        auto_frame_range = self.get_frame_range(action)
        if correct_frame_range != auto_frame_range:
            self.manual_frame_range = True

        self.trans_divisor = header.trans_divisor

        if isinstance(header.flags, int):
            int_flags = header.flags
            self.custom_flags = hex(header.flags)
            if int_flags >> 6:  # If any non supported bit is active
                self.set_custom_flags = True
        else:
            self.custom_flags = header.flags
            int_flags = 0

            flags = header.flags.replace(" ", "").lstrip("(").rstrip(")").split(" | ")
            try:
                int_flags = eval_num_from_str(header.flags)
            except Exception:
                for flag in flags:
                    index = next((index for index, flag_tuple in enumerate(C_FLAGS) if flag in flag_tuple), None)
                    if index is not None:
                        int_flags |= 1 << index
                    else:
                        self.set_custom_flags = True  # Unknown flag
        self.custom_int_flags = hex(int_flags)
        for index, prop in enumerate(FLAG_PROPS):
            setattr(self, prop, is_bit_active(int_flags, index))

    # UI
    def draw_flag_props(self, layout: UILayout, use_int_flags: bool = False):
        col = layout.column()

        col.prop(self, "set_custom_flags")

        if self.set_custom_flags:
            if use_int_flags:
                col.prop(self, "custom_int_flags")
            else:
                col.prop(self, "custom_flags")
            return

        row = col.row()
        row.prop(self, "no_loop")
        row.prop(self, "no_acceleration")
        row.prop(self, "backwards")
        if self.no_acceleration and self.backwards:
            col.label(text="Backwards has no porpuse without acceleration (read description).", icon="INFO")

        row = col.row()
        hor_col = row.column()
        hor_col.enabled = not self.only_horizontal_trans and not self.no_trans
        hor_col.prop(self, "only_vertical_trans")

        no_col = row.column()
        no_col.enabled = not self.only_horizontal_trans and not self.only_vertical_trans
        no_col.prop(self, "no_trans")

        row = col.row()
        vert_col = row.column()
        vert_col.enabled = not self.only_vertical_trans and not self.no_trans
        vert_col.prop(self, "only_horizontal_trans")

        disabled_col = row.column()
        disabled_col.enabled = not self.only_vertical_trans and not self.no_trans
        disabled_col.prop(self, "disabled")

    def draw_frame_range(self, layout: UILayout):
        col = layout.column()

        col.prop(self, "manual_frame_range")
        if self.manual_frame_range:
            row = col.row()
            prop_split(row, self, "loop_start", "Loop Start")
            prop_split(row, self, "loop_end", "Loop End")
            prop_split(col, self, "start_frame", "Start")

    def draw_names(self, layout: UILayout, action: Action, actor_name: str, generate_enums: bool):
        col = layout.column()

        name_split = col.split(factor=0.4)
        name_split.prop(self, "override_name")
        if self.override_name:
            name_split.prop(self, "custom_name", text="")
        else:
            auto_name_box = name_split.row().box()
            auto_name_box.scale_y = 0.5
            auto_name_box.label(text=self.get_anim_name(actor_name, action))

        if generate_enums:
            enum_split = col.split(factor=0.4)
            enum_split.prop(self, "override_enum")
            if self.override_enum:
                enum_split.prop(self, "custom_enum", text="")
            else:
                auto_enum_box = enum_split.row().box()
                auto_enum_box.scale_y = 0.5
                auto_enum_box.label(text=self.get_anim_enum(actor_name, action))

    def draw_props(
        self,
        layout: UILayout,
        action: Action,
        draw_table_operations: bool = True,
        draw_names: bool = True,
        draw_int_flags: bool = False,
        export_type: str = "C",
        actor_name: str = "mario",
        generate_enums: bool = False,
        draw_table_index: bool = True,
    ):
        col = layout.column()

        preview_op = col.operator(SM64_PreviewAnimOperator.bl_idname, icon="PLAY")
        preview_op.played_header = self.header_variant
        preview_op.played_action = action.name

        if draw_table_operations:
            add_op = col.row().operator(SM64_TableOperations.bl_idname, text="Add to Table", icon="ADD")
            add_op.type = "ADD"
            add_op.action_name, add_op.header_variant = action.name, self.header_variant

        if export_type == "Binary" and draw_table_index:
            prop_split(col, self, "table_index", "Table Index")
        if draw_names:
            self.draw_names(col, action, actor_name, generate_enums)
        col.separator()
        prop_split(col, self, "trans_divisor", "Translation Divisor")
        col.separator()
        self.draw_frame_range(col)
        col.separator()
        self.draw_flag_props(col, draw_int_flags)


class SM64_ActionProps(PropertyGroup):
    override_file_name: BoolProperty(name="Override File Name")
    custom_file_name: StringProperty(name="File Name", default="anim_00.inc.c")

    override_max_frame: BoolProperty(name="Override Max Frame")
    custom_max_frame: IntProperty(name="Max Frame", min=1, max=MAX_U16, default=1)

    reference_tables: BoolProperty(name="Reference Tables")
    indices_table: StringProperty(name="Indices Table", default="anim_00_indices")
    values_table: StringProperty(name="Value Table", default="anim_00_values")
    indices_address: StringProperty(name="Indices Table")  # TODO: Toad example
    values_address: StringProperty(name="Value Table")

    start_address: StringProperty(name="Start Address", default=hex(18712880))
    end_address: StringProperty(name="End Address", default=hex(18874112))

    header: PointerProperty(type=SM64_AnimHeaderProps)
    variants_tab: BoolProperty(name="Header Variants")
    header_variants: CollectionProperty(type=SM64_AnimHeaderProps)

    @property
    def headers(self) -> list[SM64_AnimHeaderProps]:
        return [self.header] + list(self.header_variants)

    def header_from_index(self, header_variant=0) -> SM64_AnimHeaderProps:
        try:
            return self.headers[header_variant]
        except IndexError as exc:
            raise ValueError("Header variant does not exist.") from exc

    def update_header_variant_numbers(self):
        for i, variant in enumerate(self.headers):
            variant.header_variant = i

    def get_anim_file_name(self, action: Action):
        if self.override_file_name:
            name = self.custom_file_name
        else:
            name = f"anim_{action.name}.inc.c"

        # Replace any invalid characters with an underscore
        # TODO: Could this be an issue anywhere else in fast64?
        name = re.sub(r'[/\\?%*:|"<>]', " ", name)

        return name

    def get_max_frame(self, action: Action) -> int:
        if self.override_max_frame:
            return self.custom_max_frame

        loop_ends: list[int] = [getFrameInterval(action)[1]]
        for header in self.headers:
            loop_end = header.get_frame_range(action)[2]
            loop_ends.append(loop_end)

        return max(loop_ends)

    def get_enum_and_header_names(self, action: Action, actor_name: str):
        return [
            (header.get_anim_enum(actor_name, action), header.get_anim_name(actor_name, action))
            for header in self.headers
        ]

    def to_data_class(
        self,
        action: Action,
        armature_obj: Object,
        blender_to_sm64_scale: float,
        quick_read: bool,
        file_name: str = "anim_00.inc.c",
    ):
        data = SM64_AnimData()
        pairs = get_animation_pairs(
            blender_to_sm64_scale, action.fast64.sm64.get_max_frame(action), action, armature_obj, quick_read
        )
        data_name: str = toAlnum(f"anim_{action.name}")
        values_reference = f"{data_name}_values"
        indice_reference = f"{data_name}_indices"
        data.pairs = pairs
        data.values_reference, data.indice_reference = values_reference, indice_reference
        data.values_file_name, data.indices_file_name = file_name, file_name
        return data

    def to_animation_class(
        self,
        action: Action,
        armature_obj: Object,
        blender_to_sm64_scale: float,
        quick_read: bool,
        can_use_references: bool,
        use_int_flags: bool,
        actor_name: str = "mario",
        generate_enums: bool = False,
    ):
        animation = SM64_Anim()
        animation.file_name = self.get_anim_file_name(action)

        if can_use_references and self.reference_tables:
            values_reference = self.values_table
            indice_reference = self.indices_table
        else:
            animation.data = self.to_data_class(
                action, armature_obj, blender_to_sm64_scale, quick_read, animation.file_name
            )
            values_reference = animation.data.values_reference
            indice_reference = animation.data.indice_reference
        bone_count = len(get_anim_pose_bones(armature_obj))
        for header_props in self.headers:
            animation.headers.append(
                header_props.to_header_class(
                    bone_count,
                    animation.data,
                    action,
                    use_int_flags,
                    values_reference,
                    indice_reference,
                    actor_name,
                    generate_enums,
                    animation.file_name,
                )
            )

        return animation

    def from_anim_class(
        self,
        animation: SM64_Anim,
        action: Action,
        actor_name: str,
        remove_name_footer: bool = True,
        use_custom_name: bool = True,
    ):
        main_header = animation.headers[0]
        is_from_binary = isinstance(main_header.reference, int)

        if main_header.file_name:
            action_name = main_header.file_name.rstrip(".c").rstrip(".inc")
        elif is_from_binary:
            action_name = hex(main_header.reference)
        else:
            action_name = main_header.reference

        if remove_name_footer:
            index = action_name.find("anim_")
            if index != -1:
                action_name = action_name[index + 5 :]
        action.name = action_name

        indice_reference = main_header.indice_reference
        values_reference = main_header.values_reference
        if is_from_binary:
            all_references = [x.reference for x in animation.headers] + [indice_reference, values_reference]
            self.start_address = hex(min(all_references))
            self.end_address = hex(
                max(all_references)
            )  # TODO: This is gonna require keeping track of all start and ends
            indice_reference = hex(indice_reference)
            values_reference = hex(values_reference)

        self.indices_table, self.indices_address = indice_reference, indice_reference
        self.values_table, self.values_address = values_reference, values_reference

        if animation.data:
            animation.data.action = action  # Used in table class to prop
            self.custom_file_name = animation.data.indices_file_name
            self.custom_max_frame = max([1] + [len(x.values) for x in animation.data.pairs])
        else:
            self.custom_file_name = main_header.file_name
            self.reference_tables = True

        if self.custom_file_name and self.get_anim_file_name(action) != self.custom_file_name:
            self.override_file_name = True

        for i in range(len(animation.headers) - 1):
            self.header_variants.add()
        for header, header_props in zip(animation.headers, self.headers):
            header_props.from_header_class(header, action, actor_name, use_custom_name)

        self.update_header_variant_numbers()

    # UI
    def draw_variant(
        self,
        layout: UILayout,
        action: Action,
        header: SM64_AnimHeaderProps,
        array_index: int,
        draw_table_operations: bool = True,
        draw_names: bool = True,
        draw_int_flags: bool = False,
        export_type: str = "C",
        actor_name: str = "mario",
        generate_enums: bool = False,
        draw_table_index: bool = False,
    ):
        col = layout.column()

        row = col.row()
        remove_op = row.operator(SM64_AnimVariantOperations.bl_idname, icon="REMOVE")
        remove_op.array_index, remove_op.type, remove_op.action_name = (
            array_index,
            "REMOVE",
            action.name,
        )

        add_op = row.operator(SM64_AnimVariantOperations.bl_idname, icon="ADD")
        add_op.array_index, add_op.type, add_op.action_name = array_index, "ADD", action.name

        move_up_col = row.column()
        move_up_col.enabled = array_index != 0
        move_up_op = move_up_col.operator(SM64_AnimVariantOperations.bl_idname, icon="TRIA_UP")
        move_up_op.array_index, move_up_op.type, move_up_op.action_name = (
            array_index,
            "MOVE_UP",
            action.name,
        )

        move_down_col = row.column()
        move_down_col.enabled = array_index != len(self.header_variants) - 1
        move_down_op = move_down_col.operator(
            SM64_AnimVariantOperations.bl_idname,
            icon="TRIA_DOWN",
        )
        move_down_op.array_index, move_down_op.type, move_down_op.action_name = (
            array_index,
            "MOVE_DOWN",
            action.name,
        )

        row.prop(
            header,
            "expand_tab_in_action",
            text=f"Variant {array_index + 1}",
            icon="TRIA_DOWN" if header.expand_tab_in_action else "TRIA_RIGHT",
        )
        if not header.expand_tab_in_action:
            return

        header.draw_props(
            col,
            action,
            draw_table_operations,
            draw_names,
            draw_int_flags,
            export_type,
            actor_name,
            generate_enums,
            draw_table_index,
        )

    def draw_variants(
        self,
        layout: UILayout,
        action: Action,
        draw_table_operations: bool = True,
        draw_names: bool = True,
        draw_int_flags: bool = False,
        export_type: str = "C",
        actor_name: str = "mario",
        generate_enums: bool = False,
        draw_table_index: bool = False,
    ):
        col = layout.column()

        col.prop(
            self.header,
            "expand_tab_in_action",
            text="Main Variant",
            icon="TRIA_DOWN" if self.header.expand_tab_in_action else "TRIA_RIGHT",
        )
        if self.header.expand_tab_in_action:
            self.header.draw_props(
                col,
                action,
                draw_table_operations,
                draw_names,
                draw_int_flags,
                export_type,
                actor_name,
                generate_enums,
                draw_table_index,
            )

        col.prop(
            self,
            "variants_tab",
            icon="TRIA_DOWN" if self.variants_tab else "TRIA_RIGHT",
        )
        if not self.variants_tab:
            return

        op_row = col.row()
        add_op = op_row.operator(SM64_AnimVariantOperations.bl_idname, icon="ADD")
        add_op.array_index, add_op.type, add_op.action_name = -1, "ADD", action.name

        if self.header_variants:
            clear_op = op_row.operator(SM64_AnimVariantOperations.bl_idname, icon="TRASH")
            clear_op.type, clear_op.action_name = "CLEAR", action.name

            box = col.box().column()

        for i, variant in enumerate(self.header_variants):
            if i != 0:
                box.separator(factor=2.0)
            self.draw_variant(
                box,
                action,
                variant,
                i,
                draw_table_operations,
                draw_names,
                draw_int_flags,
                export_type,
                actor_name,
                generate_enums,
                draw_table_index,
            )

    def draw_references(self, layout: UILayout, is_dma: bool = False):
        col = layout.column()
        col.prop(self, "reference_tables")
        if not self.reference_tables:
            return
        if is_dma:
            prop_split(col, self, "indices_address", "Indices Table")
            prop_split(col, self, "values_address", "Value Table")
        else:
            prop_split(col, self, "indices_table", "Indices Table")
            prop_split(col, self, "values_table", "Value Table")

    def draw_props(
        self,
        layout: UILayout,
        action: Action,
        specific_variant: int | None = None,
        draw_export_operation: bool = True,
        draw_table_operations: bool = True,
        draw_names: bool = True,
        draw_references: bool = True,
        draw_file_name: bool = True,
        export_type: str = "C",
        actor_name: str = "mario",
        generate_enums: bool = False,
        is_dma: bool = False,
        draw_table_index: bool = False,
    ):
        col = layout.column()
        draw_int_flags = is_dma or export_type != "C"

        if draw_export_operation:
            col.operator(SM64_ExportAnim.bl_idname, icon="EXPORT")

        if draw_table_operations:
            add_op = col.operator(SM64_TableOperations.bl_idname, text="Add All Variants to Table", icon="ADD")
            add_op.type = "ADD_ALL"
            add_op.action_name = action.name

        if export_type == "Binary":
            if not is_dma:
                prop_split(col, self, "start_address", "Start Address")
                prop_split(col, self, "end_address", "End Address")
        elif draw_file_name:
            name_split = col.split(factor=0.5)
            name_split.prop(self, "override_file_name")
            if self.override_file_name:
                name_split.prop(self, "custom_file_name", text="")
            else:
                box = name_split.box()
                box.scale_y = 0.5
                box.label(text=self.get_anim_file_name(action))

        if draw_references:
            self.draw_references(col)

        if not self.reference_tables:
            max_frame_split = col.split(factor=0.5)
            max_frame_split.prop(self, "override_max_frame")
            if self.override_max_frame:
                max_frame_split.prop(self, "custom_max_frame", text="")
            else:
                box = max_frame_split.box()
                box.scale_y = 0.4
                box.label(text=f"{action.fast64.sm64.get_max_frame(action)}")
        col.separator()

        if specific_variant is not None:
            self.headers[specific_variant].draw_props(
                col,
                action,
                draw_table_operations,
                draw_names,
                draw_int_flags,
                export_type,
                actor_name,
                generate_enums,
                draw_table_index,
            )
        else:
            self.draw_variants(
                col,
                action,
                draw_table_operations,
                draw_names,
                draw_int_flags,
                export_type,
                actor_name,
                generate_enums,
                draw_table_index,
            )


class SM64_TableElementProps(PropertyGroup):
    expand_tab: BoolProperty()
    action_prop: PointerProperty(name="Action", type=Action)
    use_main_variant: BoolProperty(name="Use Main Variant", default=True)
    variant: IntProperty(name="Variant", min=1, default=1)

    reference: BoolProperty(name="Reference")
    header_name: StringProperty(name="Header Reference", default="toad_seg6_anim_0600B66C")
    header_address: StringProperty(name="Header Reference", default=hex(0x0600B75C))  # Toad animation 0
    enum_name: StringProperty(name="Enum Name")

    @property
    def header(self) -> SM64_AnimHeaderProps:
        if self.reference:
            return None
        elif not self.action:
            return None
        if self.use_main_variant:
            return self.action.fast64.sm64.header
        return self.action.fast64.sm64.headers[self.variant]

    @property
    def action(self) -> Action:
        if self.reference:
            return None
        return self.action_prop

    def set_variant(self, action: Action, variant: int):
        self.action_prop = action
        if variant == 0:
            self.use_main_variant = True
        else:
            self.use_main_variant = False
            self.variant = variant

    def from_table_element_class(self, element: SM64_AnimTableElement):
        if element.data:
            self.set_variant(element.data.action, element.header.header_variant)
        else:
            self.reference = True
        if isinstance(element.reference, int):
            self.header_name = hex(element.reference)
            self.header_address = hex(element.reference)
        else:
            self.header_name = element.reference
            self.header_address = "0x00000000"
        if element.enum_name:
            self.enum_name = element.enum_name

    # UI
    def draw_reference(self, layout: UILayout, export_type: str = "C", generate_enums: bool = False):
        col = layout.column()
        if export_type in {"C"}:
            prop_split(col, self, "header_name", "Header Reference")
            if generate_enums:
                prop_split(col, self, "enum_name", "Enum Name")
        else:
            prop_split(col, self, "header_address", "Header Reference")

    def draw_props(
        self,
        layout: UILayout,
        is_dma: bool = False,
        export_seperately: bool = True,
        export_type: str = "C",
        generate_enums: bool = False,
        actor_name: str = "mario",
    ):
        col = layout.column()

        row = col.row()
        if not is_dma:
            row.prop(self, "reference")
            if self.reference:
                self.draw_reference(col, export_type, generate_enums)
                return

        row.prop(self, "action_prop", text="")
        if not self.action_prop:
            col.box().label(text="Header´s action does not exist. Use references for NULLs", icon="ERROR")
            return
        action_props: SM64_ActionProps = self.action_prop.fast64.sm64

        row = col.row(align=True)
        row.prop(self, "use_main_variant")
        variant = 0
        if not self.use_main_variant:
            row.prop(self, "variant")
            # Usually I'd use a column for enabled, but it was breaking the UI
            remove_split = row.split()
            remove_op = remove_split.operator(SM64_AnimVariantOperations.bl_idname, icon="REMOVE")
            remove_op.array_index, remove_op.type, remove_op.action_name = (
                self.variant - 1,
                "REMOVE",
                self.action_prop.name,
            )
            remove_split.enabled = len(action_props.headers) > 1

            add_op = row.operator(SM64_AnimVariantOperations.bl_idname, icon="ADD")
            add_op.array_index, add_op.type, add_op.action_name = (
                self.variant - 1,
                "ADD",
                self.action_prop.name,
            )

            if not 0 <= self.variant < len(action_props.headers):
                col.box().label(text="Header variant does not exist.", icon="ERROR")
                return
            variant = self.variant

        prop_box = col.box().column()
        prop_box.prop(
            self,
            "expand_tab",
            icon="TRIA_DOWN" if self.expand_tab else "TRIA_RIGHT",
            text=f"{self.header.get_anim_name(actor_name, self.action_prop)} Properties",
        )
        c_not_dma = export_type == "C" and not is_dma
        if self.expand_tab:
            action_props.draw_props(
                layout=prop_box,
                action=self.action_prop,
                export_type=export_type,
                specific_variant=variant,
                draw_export_operation=False,
                draw_table_operations=False,
                draw_names=c_not_dma,
                draw_references=not is_dma,
                draw_file_name=c_not_dma and export_seperately,
                actor_name=actor_name,
                generate_enums=generate_enums,
                is_dma=is_dma,
            )


class SM64_AnimTableProps(PropertyGroup):
    update_table: BoolProperty(
        name="Update Table On Action Export",
        description="Update table outside of table exports",
        default=True,
    )

    export_seperately: BoolProperty(name="Export All Seperately")
    override_files_prop: BoolProperty(name="Override Table and Data Files")
    elements: CollectionProperty(type=SM64_TableElementProps)

    generate_enums: BoolProperty(name="Generate Enums", default=True)
    override_table_name: BoolProperty(name="Override Table Name")
    custom_table_name: StringProperty(name="Table Name", default="mario_anims")

    insertable_file_name: StringProperty(name="Insertable File Name", default="toad.insertable")

    address: StringProperty(name="Table Address", default=hex(0x0600FC48))  # Toad animation table
    # TODO: 0xa3fa60 is where the data starts, maybe this should default to that
    # ends after the table at 0x600FC68
    end_address: StringProperty(name="End Address", default=hex(0x600FC68))

    update_load_command: BoolProperty(name="Update Table Load Command")
    load_command_address: StringProperty(
        name="Table Load Command Address", default="0x21CD08"
    )  # TODO: Change this to castle toad's, use quad64
    dma_address: StringProperty(name="DMA Table Address", default=hex(0x4EC000))
    dma_end_address: StringProperty(name="DMA Table End", default=hex(0x4EC000 + 0x8DC20))

    @property
    def override_files(self):
        return self.export_seperately and self.override_files_prop

    @property
    def actions(self) -> list[Action]:
        actions = []
        for table_element in self.elements:
            if table_element.action and table_element.action not in actions:
                actions.append(table_element.action)

        return actions

    @property
    def headers(self) -> list[SM64_AnimHeaderProps]:
        headers = []
        for table_element in self.elements:
            if table_element.header and table_element.header not in headers:
                headers.append(table_element.header)
        return headers

    def get_anim_table_name(self, actor_name: str) -> str:
        if self.override_table_name:
            return self.custom_table_name
        return f"{actor_name}_anims"

    def get_enum_list_name(self, actor_name: str):
        return f"{actor_name}Anims".title()

    def from_anim_table_class(self, table: SM64_AnimTable, clear_table: bool = False):
        if clear_table:
            self.elements.clear()
        for element in table.elements:
            self.elements.add()
            self.elements[-1].from_table_element_class(element)

    def to_table_class(
        self,
        armature_obj: Object,
        blender_to_sm64_scale: float,
        quick_read: bool,
        use_int_flags: bool = False,
        can_use_references: bool = True,
        actor_name: str = "mario",
        generate_enums: bool = False,
        use_addresses_for_references: bool = False,
    ):
        table = SM64_AnimTable()
        table.reference = self.get_anim_table_name(actor_name)
        table.enum_list_reference = self.get_enum_list_name(actor_name)
        table.file_name = "table_animations.inc.c"
        table.values_reference = toAlnum(f"anim_{actor_name}_values")

        bone_count = len(get_anim_pose_bones(armature_obj))

        existing_data: dict[Action, SM64_AnimData] = {}
        existing_headers: dict[SM64_AnimHeaderProps, SM64_AnimHeader] = {}

        element: SM64_TableElementProps
        for i, element in enumerate(self.elements):
            reference = SM64_AnimTableElement()
            if can_use_references and element.reference:
                header = (
                    eval_num_from_str(element.header_address) if use_addresses_for_references else element.header_name
                )
                assert header, f"Reference in table element {i} is not set."
                reference.reference = header
                if generate_enums:
                    assert element.enum_name, f"Enum name in table element {i} is not set."
                    reference.enum_name = element.enum_name
                table.elements.append(reference)
                continue

            if not element.header:
                raise PluginError(f"No header in table element {i}.")

            action: Action = element.action
            action_props: SM64_ActionProps = action.fast64.sm64
            if can_use_references and action_props.reference_tables:
                values_reference, indice_reference = action_props.values_table, action_props.indices_table
                data = None
            else:
                if not action in existing_data:
                    existing_data[action] = action_props.to_data_class(
                        action, armature_obj, blender_to_sm64_scale, quick_read
                    )
                data = existing_data[action]
                values_reference, indice_reference = data.values_reference, data.indice_reference

            reference.header = existing_headers.get(
                element.header,
                element.header.to_header_class(
                    bone_count,
                    data,
                    action,
                    use_int_flags,
                    values_reference,
                    indice_reference,
                    actor_name,
                    generate_enums,
                    action_props.get_anim_file_name(action),
                ),
            )
            reference.reference = reference.header.reference
            reference.enum_name = reference.header.enum_reference
            table.elements.append(reference)

        return table

    # UI
    def draw_element(
        self,
        layout: UILayout,
        table_index: int,
        table_element: SM64_TableElementProps,
        is_dma: bool,
        duplicate_index: int | None = 0,
        export_type: str = "c",
        actor_name: str = "mario",
    ):
        col = layout.column()

        row = col.row()

        info_row = row.row()
        info_row.scale_x = 999  # HACK: Allow the left row to use as much available space as it can
        info_row.alignment = "LEFT"
        info_col = info_row.column()

        op_row = row.row()
        op_row.alignment = "RIGHT"
        op_row.label(text=str(table_index))

        add_op = op_row.operator(SM64_TableOperations.bl_idname, icon="ADD")
        add_op.array_index, add_op.type = table_index, "ADD"

        remove_op = op_row.operator(SM64_TableOperations.bl_idname, icon="REMOVE")
        remove_op.array_index, remove_op.type = table_index, "REMOVE"

        move_up_col = op_row.column()
        move_up_col.enabled = table_index != 0
        move_up_op = move_up_col.operator(SM64_TableOperations.bl_idname, icon="TRIA_UP")
        move_up_op.array_index, move_up_op.type = table_index, "MOVE_UP"

        move_down_col = op_row.column()
        move_down_col.enabled = table_index != len(self.elements) - 1
        move_down_op = move_down_col.operator(SM64_TableOperations.bl_idname, icon="TRIA_DOWN")
        move_down_op.array_index, move_down_op.type = table_index, "MOVE_DOWN"

        table_element.draw_props(
            info_col.box(),
            is_dma,
            self.export_seperately,
            export_type,
            self.generate_enums,
            actor_name,
        )

        if is_dma and not duplicate_index is None:
            multilineLabel(
                info_col.box(),
                "In DMA tables, headers for each action must be \nin one sequence or the data will be duplicated.\n"
                f"Data duplicate at index {duplicate_index}",
                "INFO",
            )

    def draw_non_exclusive_settings(self, layout: UILayout, export_type: str = "C", actor_name: str = "mario"):
        col = layout.column()
        if export_type == "C":
            col.prop(self, "generate_enums")

            name_split = col.split()
            name_split.prop(self, "override_table_name")
            if self.override_table_name:
                name_split.prop(self, "custom_table_name", text="")
            else:
                box = name_split.row().box()
                box.scale_y = 0.5
                box.label(text=self.get_anim_table_name(actor_name))
        elif export_type == "Binary":
            prop_split(col, self, "address", "Table Address")
            col.prop(self, "update_load_command")
            if self.update_load_command:
                prop_split(col, self, "load_command_address", "Command Address")

    def draw_props(
        self,
        layout: UILayout,
        is_dma: bool,
        export_type: str,
        draw_non_exclusive_settings: bool,
        actor_name: str,
    ):
        col = layout.column()

        if draw_non_exclusive_settings:
            self.draw_non_exclusive_settings(col, export_type, actor_name)

        if export_type == "Insertable Binary":
            prop_split(col, self, "insertable_file_name", "File Name")
        elif export_type == "C" and not is_dma:
            col.prop(self, "export_seperately")
            if self.export_seperately:
                col.prop(self, "override_files_prop")

        if self.elements:
            col.operator(SM64_ExportAnimTable.bl_idname, icon="EXPORT")
        else:
            col.label(icon="INFO", text="Empty table, add headers to do a table export.")

        if is_dma and export_type == "C":
            multilineLabel(
                col,
                "The export will follow the vanilla DMA naming\nconventions (anim_xx.inc.c, anim_xx, anim_xx_values, etc).",
                icon="INFO",
            )

        col.separator()

        row = col.row()
        add_op = row.operator(SM64_TableOperations.bl_idname, icon="ADD")
        add_op.type = "ADD"

        clear_op_col = col.column()
        clear_op_col.enabled = len(self.elements) > 0
        clear_op = row.operator(SM64_TableOperations.bl_idname, icon="TRASH")
        clear_op.type = "CLEAR"

        elements_col = col.column()
        elements_col.scale_y = 0.8
        actions = []
        for table_index, table_element in enumerate(self.elements):
            if table_element.action in actions and actions[-1] != table_element.action:
                duplicate_index = actions.index(table_element.action)
            else:
                duplicate_index = None
            self.draw_element(
                elements_col,
                table_index,
                table_element,
                is_dma,
                duplicate_index,
                export_type,
                actor_name,
            )
            elements_col.separator()
            actions.append(table_element.action)


class SM64_AnimImportProps(PropertyGroup):
    import_type: EnumProperty(items=enumAnimImportTypes, name="Type", default="C")

    clear_table: BoolProperty(name="Clear Table On Import", default=True)
    binary_import_type: EnumProperty(
        items=enumAnimBinaryImportTypes,
        name="Type",
        default="Animation",
    )
    assume_bone_count: BoolProperty(
        name="Assume Bone Count",
        default=True,
        description="When enabled, the selected armature's bone count will be used instead of the header's, "
        "as old fast64 binary exports did no export this value",
    )

    rom: StringProperty(name="Import ROM", subtype="FILE_PATH")
    read_entire_table: BoolProperty(
        name="Read All Animations",
    )
    table_index: IntProperty(name="Table Index", min=0)
    ignore_null: BoolProperty(name="Ignore NULL Delimiter")
    table_address: StringProperty(name="Address", default=hex(0x0600FC48))  # Toad animation table
    animation_address: StringProperty(name="Address", default=hex(0x0600B75C))  # Toad animation 0
    is_segmented_address: BoolProperty(name="Is Segmented Address", default=True)
    level: EnumProperty(items=level_enums, name="Level", default="IC")
    dma_table_address: StringProperty(name="DMA Table Address", default="0x4EC000")
    mario_animation: IntProperty(name="Selected Preset Mario Animation")

    insertable_read_from_rom: BoolProperty(
        name="Read From Import ROM",
        description="When enabled, the importer will read from the import ROM given a non defined address",
    )

    path: StringProperty(
        name="Path",
        subtype="FILE_PATH",
        default="anims/",
    )
    remove_name_footer: BoolProperty(
        name="Remove Name Footers",
        description='Remove "anim_" from imported animations',
        default=True,
    )
    use_custom_name: BoolProperty(
        name="Use Custom Name",
        default=True,
    )

    @property
    def mario_or_table_index(self):
        return (
            self.mario_animation
            if self.binary_import_type == "DMA" and self.mario_animation != -1
            else self.table_index
        )

    @property
    def address(self):
        return eval_num_from_str(
            self.dma_table_address
            if self.binary_import_type == "DMA"
            else (self.table_address if self.binary_import_type == "Table" else self.animation_address)
        )

    def draw_c(self, layout: UILayout):
        col = layout.column()

        col.prop(self, "remove_name_footer")
        col.prop(self, "use_custom_name")

    def draw_binary(self, layout: UILayout, import_rom: os.PathLike | None = None):
        col = layout.column()

        col.prop(self, "rom")
        col.label(text="Uses scene import ROM by default", icon="INFO")
        try:
            if self.rom or import_rom is None:
                import_rom_checks(abspath(self.rom))
        except Exception as exc:
            multilineLabel(col.box(), str(exc), "ERROR")
            col = col.column()
            col.enabled = False

        prop_split(col, self, "binary_import_type", "Binary Type")

        if self.binary_import_type == "DMA":
            prop_split(col, self, "dma_table_address", "DMA Table Address")

            col.prop(self, "read_entire_table")
            if not self.read_entire_table:
                col.operator(SM64_SearchMarioAnimEnum.bl_idname, icon="VIEWZOOM")
                if self.mario_animation == -1:
                    prop_split(col, self, "table_index", "Entry")
                else:
                    col.box().label(text=f"{marioAnimationNames[self.mario_animation + 1][1]}")
        else:
            prop_split(col, self, "level", "Level")
            col.prop(self, "is_segmented_address")

        if self.binary_import_type == "Table":
            prop_split(col, self, "table_address", "Address")
            col.prop(self, "read_entire_table")
            if not self.read_entire_table:
                prop_split(col, self, "table_index", "List Index")
                col.prop(self, "ignore_null")
        elif self.binary_import_type == "Animation":
            prop_split(col, self, "animation_address", "Address")

    def draw_insertable_binary(self, layout: UILayout, import_rom: os.PathLike | None = None):
        col = layout.column()

        col.label(text="Type will be read from the data type of the files")
        col.separator()

        from_rom_box = col.box().column()
        from_rom_box.prop(self, "insertable_read_from_rom")
        if self.insertable_read_from_rom:
            col.label(text="Uses scene import ROM by default", icon="INFO")
            try:
                if self.rom or import_rom is None:
                    import_rom_checks(abspath(self.rom))
            except Exception as exc:
                multilineLabel(from_rom_box.box(), str(exc), "ERROR")
                from_rom_box = from_rom_box.column()
                from_rom_box.enabled = False

            prop_split(from_rom_box, self, "level", "Level")
            from_rom_box.prop(self, "is_segmented_address")
            prop_split(from_rom_box, self, "address", "Address")

        table_box = col.box().column()
        table_box.label(text="Table Imports")
        table_box.prop(self, "read_entire_table")
        if not self.read_entire_table:
            prop_split(table_box, self, "table_index", "List Index")
            table_box.prop(self, "ignore_null")

    def draw_props(self, layout: UILayout, import_rom: os.PathLike | None = None):
        col = layout.column()

        prop_split(col, self, "import_type", "Type")
        col.separator()

        if self.import_type in {"C", "Insertable Binary"}:
            prop_split(col, self, "path", "Path")
            col.label(text="Folders and individual files are supported as the path", icon="INFO")
            path_ui_warnings(col, abspath(self.path))

        if self.import_type == "C":
            self.draw_c(col)
        else:
            if self.import_type == "Binary":
                self.draw_binary(col, import_rom)
            elif self.import_type == "Insertable Binary":
                self.draw_insertable_binary(col, import_rom)
            col.prop(self, "assume_bone_count")
        col.prop(self, "clear_table")
        col.separator()

        col.operator(SM64_ImportAnim.bl_idname, icon="IMPORT")
        if self.import_type in {"C", "Binary"}:
            layout.operator(SM64_ImportAllMarioAnims.bl_idname, icon="IMPORT")


class SM64_AnimProps(PropertyGroup):
    version: bpy.props.IntProperty(name="SM64_AnimProps Version", default=0)
    cur_version = 1  # version after property migration

    played_header: IntProperty(min=0)
    played_action: PointerProperty(name="Action", type=Action)

    table_tab: BoolProperty(name="Table")
    table: PointerProperty(type=SM64_AnimTableProps)
    importing_tab: BoolProperty(name="Importing")
    importing: PointerProperty(type=SM64_AnimImportProps)

    action_tab: BoolProperty(name="Action", default=True)
    selected_action: PointerProperty(name="Action", type=Action)

    directory_path: StringProperty(name="Directory Path", subtype="FILE_PATH")
    dma_folder: StringProperty(name="DMA Folder", default="assets/anims/")
    use_dma_structure: BoolProperty(
        name="Use DMA Structure",
        description="When enabled, the Mario animation converter order is used (headers, indicies, values)",
    )
    actor_name_prop: StringProperty(name="Name", default="mario")
    group_name: StringProperty(
        name="Group Name",
        default="group0",
    )  # TODO: Ideally, this pr will be merged after combined exports, so this should be updated to use the group enum there
    header_type: EnumProperty(items=enumAnimExportTypes, name="Header Export", default="Actor")
    level_name: StringProperty(name="Level", default="bob")
    level_option: EnumProperty(items=enumLevelNames, name="Level", default="bob")

    # Binary
    binary_level: EnumProperty(items=level_enums, name="Level", default="IC")
    is_binary_dma: BoolProperty(name="Is DMA", default=True)

    # Insertable
    insertable_directory_path: StringProperty(name="Directory Path", subtype="FILE_PATH")

    quick_read: BoolProperty(
        name="Quick Data Read", default=True, description="Read fcurves directly, should work with the majority of rigs"
    )

    def update_version_0(self, scene: Scene):
        importing: SM64_AnimImportProps = self.importing

        importing.animation_address = scene.get("animStartImport", importing.animation_address)
        importing.is_segmented_address = scene.get("animIsSegPtr", importing.is_segmented_address)
        importing.level = scene.get("levelAnimImport", importing.level)
        importing.table_index = scene.get("animListIndexImport", importing.table_index)
        if importing.get("isDMAImport", False):
            importing.binary_import_type = "DMA"
        elif importing.get("animIsAnimList", True):
            importing.binary_import_type = "Table"

        # Export
        for action in bpy.data.actions:
            action_props: SM64_ActionProps = action.fast64.sm64
            action_props.header.no_loop = not scene.get("loopAnimation", not action_props.header.no_loop)
            action_props.start_address = scene.get("animExportStart", action_props.start_address)
            action_props.end_address = scene.get("animExportEnd", action_props.end_address)
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
        self.level_name = scene.get("animLevelName", self.level_name)
        self.is_binary_dma = scene.get("isDMAExport", self.is_binary_dma)

        insertable_directory_path = scene.get("animInsertableBinaryPath", "")
        if insertable_directory_path:
            # Ignores file name
            self.insertable_directory_path = os.path.split(insertable_directory_path)[0]

        table: SM64_AnimTableProps = self.table
        table.update_table = scene.get("setAnimListIndex", table.update_table)
        table.address = scene.get("addr_0x27", table.address)
        table.update_load_command = scene.get("overwrite_0x28", table.update_load_command)
        table.load_command_address = scene.get("addr_0x28", table.load_command_address)
        self.binary_level = scene.get("levelAnimExport", self.binary_level)

        self.version = 1
        print("Upgraded global SM64 settings to version 1")

    @staticmethod
    def upgrade_changed_props():
        for scene in bpy.data.scenes:
            anim_props: SM64_AnimProps = scene.fast64.sm64.animation
            if anim_props.version == 0:
                anim_props.update_version_0(scene)

    @property
    def actor_name(self):
        return self.actor_name_prop if self.header_type != "DMA" else None

    @property
    def is_c_dma_structure(self):
        if self.header_type == "DMA":
            return True
        if self.header_type == "Custom":
            return self.use_dma_structure
        return False

    def get_animation_paths(self, create_directories: bool = False):
        custom_export = self.header_type == "Custom"

        export_path, level_name = getPathAndLevel(
            custom_export,
            self.directory_path,
            self.level_option,
            self.level_name,
        )

        dir_name = toAlnum(self.actor_name)

        if self.header_type == "DMA":
            anim_dir_path = os.path.join(export_path, self.dma_folder)
            dir_path = ""
            geo_dir_path = ""
        else:
            dir_path = getExportDir(
                custom_export,
                export_path,
                self.header_type,
                level_name,
                "",
                dir_name,
            )[0]
            geo_dir_path = os.path.join(dir_path, dir_name)
            anim_dir_path = os.path.join(geo_dir_path, "anims")
            if create_directories:
                if not os.path.exists(dir_path):
                    os.mkdir(dir_path)
                if not os.path.exists(geo_dir_path):
                    os.mkdir(geo_dir_path)

        if create_directories and not os.path.exists(anim_dir_path):
            os.mkdir(anim_dir_path)

        return (
            abspath(anim_dir_path),
            abspath(dir_path),
            abspath(geo_dir_path),
            level_name,
        )

    def draw_action_properties(self, layout: UILayout, is_dma: bool, export_type: str):
        col = layout.column()

        col.prop(self, "action_tab", icon="TRIA_DOWN" if self.action_tab else "TRIA_RIGHT")
        if not self.action_tab:
            return

        col.prop(self, "selected_action")
        if self.selected_action:
            action_props: SM64_ActionProps = self.selected_action.fast64.sm64
            action_props.draw_props(
                layout=col,
                action=self.selected_action,
                draw_references=export_type in {"C"} or not is_dma,
                export_type=export_type,
                actor_name=self.actor_name,
                generate_enums=self.table.generate_enums,
                draw_table_index=self.table.update_table,
                draw_names=export_type in {"C"},
                is_dma=is_dma,
            )

    def draw_table_properties(self, layout: UILayout, is_dma: bool, export_type: str):
        col = layout.column()
        col.prop(self, "table_tab", icon="TRIA_DOWN" if self.table_tab else "TRIA_RIGHT")
        if self.table_tab:
            self.table.draw_props(
                col,
                is_dma,
                export_type,
                not self.table.update_table and not is_dma,
                self.actor_name,
            )

    def draw_importing_properties(self, layout: UILayout, import_rom: os.PathLike | None = None):
        col = layout.column()
        col.prop(self, "importing_tab", icon="TRIA_DOWN" if self.importing_tab else "TRIA_RIGHT")
        if self.importing_tab:
            self.importing.draw_props(col, import_rom)

    def draw_binary_settings(self, layout: UILayout, export_type: str):
        col = layout.column()
        col.prop(self, "is_binary_dma")

        if export_type == "Binary":
            if self.is_binary_dma:
                col.prop(self, "binary_overwrite_dma_entry")
            else:
                col.prop(self, "binary_level")

        if export_type == "Insertable Binary":
            prop_split(col, self, "directory_path", "Directory")
            directory_ui_warnings(col, abspath(self.directory_path))

    def draw_c_settings(self, layout: UILayout):
        col = layout.column()

        prop_split(col, self, "header_type", "Export Type")

        if self.header_type != "DMA":
            prop_split(col, self, "actor_name_prop", "Name")

        if self.header_type == "Custom":
            col.prop(self, "use_dma_structure")
            col.prop(self, "directory_path")
            if directory_ui_warnings(col, abspath(self.directory_path)):
                customExportWarning(col)
        elif self.header_type == "DMA":
            col.prop(self, "dma_folder")
            decompFolderMessage(col)
        else:
            if self.header_type == "Actor":
                prop_split(col, self, "group_name", "Group Name")
            elif self.header_type == "Level":
                prop_split(col, self, "level_option", "Level")
                if self.level_option == "custom":
                    prop_split(col, self, "level_name", "Level Name")

            decompFolderMessage(col)
            write_box = makeWriteInfoBox(col).column()
            writeBoxExportType(
                write_box,
                self.header_type,
                self.actor_name,
                self.level_name,
                self.level_option,
            )

    def draw_props(
        self,
        layout: UILayout,
        export_type: str = "C",
        show_importing: bool = True,
        import_rom: os.PathLike | None = None,
    ):
        col = layout.column()

        is_dma = (export_type != "C" and self.is_binary_dma) or self.header_type == "DMA"

        if export_type == "C":
            self.draw_c_settings(col)
        else:
            self.draw_binary_settings(col, export_type)
        col.separator()

        box = col.box().column()
        if (export_type == "C" or export_type == "Binary") and not is_dma:
            box.prop(self.table, "update_table")
            if self.table.update_table:
                self.table.draw_non_exclusive_settings(box, export_type, self.actor_name)
        elif export_type == "Binary":
            prop_split(box, self.table, "dma_address", "DMA Table Address")
            prop_split(box, self.table, "dma_end_address", "DMA Table End")
        box.prop(self, "quick_read")
        col.separator()

        self.draw_action_properties(col.box(), is_dma, export_type)
        self.draw_table_properties(col.box(), is_dma, export_type)
        if show_importing:
            self.draw_importing_properties(col.box(), import_rom)


properties = (
    SM64_AnimHeaderProps,
    SM64_TableElementProps,
    SM64_ActionProps,
    SM64_AnimTableProps,
    SM64_AnimImportProps,
    SM64_AnimProps,
)


def anim_props_register():
    for cls in properties:
        register_class(cls)


def anim_props_unregister():
    for cls in reversed(properties):
        unregister_class(cls)
