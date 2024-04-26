import os

import bpy
from bpy.utils import register_class, unregister_class
from bpy.types import Context, Object, Scene, Operator, Action
from bpy.path import abspath
from bpy.props import (
    EnumProperty,
    StringProperty,
    IntProperty,
)

import os

from ...utility import (
    PluginError,
    applyBasicTweaks,
    copyPropertyGroup,
    path_checks,
    filepath_checks,
    toAlnum,
    raisePluginError,
    get_mode_set_from_context_mode,
    writeInsertableFile,
    decodeSegmentedAddr,
)
from ...utility_anim import stashActionInArmature
from ..sm64_utility import import_rom_checks
from ..sm64_level_parser import parseLevelAtPointer
from ..sm64_constants import level_pointers, insertableBinaryTypes

from .classes import SM64_DMATable, DMATableEntrie, SM64_Anim, SM64_AnimTable, RomReading
from .importing import (
    import_binary_animations,
    import_binary_dma_animation,
    animation_import_to_blender,
    import_binary_header,
    import_c_animations,
    import_insertable_binary_animations,
)
from .exporting import (
    update_data_file,
    update_includes,
    update_table_file,
    write_anim_header,
)
from .utility import animation_operator_checks, eval_num_from_str, get_action, get_anim_pose_bones
from .constants import marioAnimationNames

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..settings.properties import SM64_Properties
    from .properties import (
        SM64_AnimProps,
        SM64_AnimImportProps,
        SM64_AnimTableProps,
        SM64_ActionProps,
    )


def emulate_no_loop(scene: Scene):
    animation_props: SM64_AnimProps = scene.fast64.sm64.animation
    played_action: Action = animation_props.played_action

    if (
        not played_action
        or animation_props.played_header >= len(played_action.fast64.sm64.headers)
        or not bpy.context.screen.is_animation_playing
    ):
        played_action = None
        return
    frame = scene.frame_current

    header = played_action.fast64.sm64.headers[animation_props.played_header]
    loop_start, loop_end = header.get_frame_range(played_action)[1:3]
    if header.backwards:
        if frame < loop_start:
            if header.no_loop:
                scene.frame_set(loop_start)
            else:
                scene.frame_set(loop_end - 1)
    elif frame >= loop_end:
        if header.no_loop:
            scene.frame_set(loop_end - 1)
        else:
            scene.frame_set(loop_start)


class SM64_PreviewAnimOperator(Operator):
    bl_idname = "scene.sm64_preview_animation"
    bl_label = "Preview Animation"
    bl_options = {"REGISTER", "UNDO", "PRESET"}

    played_header: IntProperty(name="Header", min=0, default=0)
    played_action: StringProperty(name="Action")

    def execute_operator(self, context: Context):
        animation_operator_checks(context)

        scene = context.scene
        scene_anim_props = scene.fast64.sm64.animation
        if context.space_data.type != "VIEW_3D" and context.space_data.context == "OBJECT":
            animation_props: SM64_AnimProps = context.object.fast64.sm64.animation
        else:
            animation_props: SM64_AnimProps = scene_anim_props

        if self.played_action:
            played_action = get_action(self.played_action)
        else:
            played_action = animation_props.selected_action
        header = played_action.fast64.sm64.header_from_index(self.played_header)

        start_frame = header.get_frame_range(played_action)[0]

        scene.frame_set(start_frame)
        scene.render.fps = 30

        context.selected_objects[0].animation_data.action = played_action

        if bpy.context.screen.is_animation_playing:
            bpy.ops.screen.animation_play()

        bpy.ops.screen.animation_play()

        scene_anim_props.played_header = self.played_header
        scene_anim_props.played_action = played_action

        return {"FINISHED"}

    def execute(self, context: Context):
        starting_context_mode = context.mode
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        try:
            self.execute_operator(context)
            return {"FINISHED"}
        except Exception as exc:
            raisePluginError(self, exc)
            return {"CANCELLED"}
        finally:
            bpy.ops.object.mode_set(mode=get_mode_set_from_context_mode(starting_context_mode))


class SM64_TableOperations(Operator):
    bl_idname = "scene.sm64_table_operations"
    bl_label = ""
    bl_options = {"UNDO"}

    array_index: IntProperty()
    type: StringProperty()
    action_name: StringProperty(name="Action")
    header_variant: IntProperty()

    def execute_operator(self, context: Context):
        if context.space_data.type != "VIEW_3D" and context.space_data.context == "OBJECT":
            animation_props: SM64_AnimProps = context.object.fast64.sm64.animation
        else:
            animation_props: SM64_AnimProps = context.scene.fast64.sm64.animation
        table_elements = animation_props.table.elements

        if self.array_index < len(table_elements):
            table_element = table_elements[self.array_index]
        else:
            table_element = None

        if self.type == "MOVE_UP":
            table_elements.move(self.array_index, self.array_index - 1)
        elif self.type == "MOVE_DOWN":
            table_elements.move(self.array_index, self.array_index + 1)
        elif self.type == "ADD":
            table_elements.add()
            if self.action_name and self.header_variant:
                table_elements[-1].set_variant(bpy.data.actions[self.action_name], self.header_variant)
            elif table_element:
                table_elements[-1].set_variant(table_element.action, self.header_variant)
                table_elements.move(len(table_elements) - 1, self.array_index + 1)
        elif self.type == "ADD_ALL":
            action = bpy.data.actions[self.action_name]
            for header_variant in range(len(action.fast64.sm64.headers)):
                table_elements.add()
                table_elements[-1].set_variant(action, header_variant)
        elif self.type == "REMOVE":
            table_elements.remove(self.array_index)
        if self.type == "CLEAR":
            table_elements.clear()

        return {"FINISHED"}

    def execute(self, context: Context):
        try:
            self.execute_operator(context)
            return {"FINISHED"}
        except Exception as exc:
            raisePluginError(self, exc)
            return {"CANCELLED"}


class SM64_AnimVariantOperations(Operator):
    bl_idname = "scene.sm64_header_variant_operations"
    bl_label = ""
    bl_options = {"UNDO"}

    array_index: IntProperty()
    type: StringProperty()
    action_name: StringProperty(name="Action")

    def execute_operator(self, context):
        action = bpy.data.actions[self.action_name]
        action_props = action.fast64.sm64

        variants = action_props.header_variants

        if self.type == "MOVE_UP":
            variants.move(self.array_index, self.array_index - 1)
        elif self.type == "MOVE_DOWN":
            variants.move(self.array_index, self.array_index + 1)
        elif self.type == "ADD":
            variants.add()
            added_variant = variants[-1]
            added_variant.action = action

            copyPropertyGroup(action_props.headers[self.array_index + 1], added_variant)

            variants.move(len(variants) - 1, self.array_index + 1)
            action_props.update_header_variant_numbers()

            added_variant.expand_tab = True
            added_variant.override_name = False
            added_variant.override_enum = False
            added_variant.custom_name = added_variant.get_anim_name(
                context.scene.fast64.sm64.animation.actor_name, action
            )
        elif self.type == "REMOVE":
            variants.remove(self.array_index)
        if self.type == "CLEAR":
            variants.clear()

        action_props.update_header_variant_numbers()

        return {"FINISHED"}

    def execute(self, context):
        try:
            self.execute_operator(context)
            return {"FINISHED"}
        except Exception as exc:
            raisePluginError(self, exc)
            return {"CANCELLED"}


class SM64_ExportAnimTable(Operator):
    bl_idname = "scene.sm64_export_anim_table"
    bl_label = "Export"
    bl_description = "Select an armature with animation data to use"
    bl_options = {"REGISTER", "UNDO", "PRESET"}

    def execute_operator(self, context: Context):
        # TODO: This got a bit gross, revisit eventually
        bpy.ops.object.mode_set(mode="OBJECT")
        animation_operator_checks(context)

        scene = context.scene
        sm64_props: SM64_Properties = scene.fast64.sm64
        armature_obj: Object = context.selected_objects[0]
        if context.space_data.type != "VIEW_3D" and context.space_data.context == "OBJECT":
            animation_props: SM64_AnimProps = armature_obj.fast64.sm64.animation
        else:
            animation_props: SM64_AnimProps = sm64_props.animation
        table_props: SM64_AnimTableProps = animation_props.table

        actions = table_props.actions

        print("Stashing all actions in table")

        for action in actions:
            stashActionInArmature(armature_obj, action)

        actor_name = animation_props.actor_name

        print("Reading table data")

        table: SM64_AnimTable = table_props.to_table_class(
            armature_obj,
            sm64_props.blender_to_sm64_scale,
            sm64_props.export_type != "C" or animation_props.header_type == "DMA",
            sm64_props.export_type == "C" or not animation_props.is_binary_dma,
            animation_props.quick_read,
            actor_name,
        )

        print("Exporting table data")

        if sm64_props.export_type == "C":
            header_type = animation_props.header_type

            anim_dir_path, dir_path, geo_dir_path, level_name = animation_props.get_animation_paths(True)

            if header_type != "Custom":
                applyBasicTweaks(abspath(sm64_props.decomp_path))

            if header_type == "DMA" or table_props.export_seperately:
                if header_type == "DMA":
                    table.prepare_for_dma()
                files_data = table.data_and_headers_to_c(header_type == "DMA")

                print("Saving all generated files")
                for file_name, file_data in files_data.items():
                    with open(os.path.join(anim_dir_path, file_name), "w", newline="\n") as file:
                        file.write(file_data)
                    if header_type != "DMA":
                        update_data_file(os.path.join(anim_dir_path, "data.inc.c"), [file_name])
            else:
                with open(os.path.join(anim_dir_path, "data.inc.c"), "w", newline="\n") as file:
                    file.write(table.data_and_headers_to_c_combined())

            if header_type != "DMA":
                write_anim_header(
                    os.path.join(geo_dir_path, "anim_header.h"), table.reference, table_props.generate_enums
                )
                if table_props.override_files:
                    with open(os.path.join(anim_dir_path, "table.inc.c"), "w", newline="\n") as file:
                        file.write(table.table_to_c(table_props.generate_enums))
                    if table_props.generate_enums:
                        with open(os.path.join(anim_dir_path, "table_enum.h"), "w", newline="\n") as file:
                            file.write(table.enum_list_to_c())
                else:
                    update_table_file(
                        os.path.join(anim_dir_path, "table.inc.c"),
                        table_props.get_enum_and_header_names(actor_name),
                        table.reference,
                        table_props.generate_enums,
                        False,
                        os.path.join(anim_dir_path, "table_enum.h"),
                        table.enum_list_reference,
                    )

            if not header_type in {"Custom", "DMA"}:
                update_includes(
                    level_name,
                    animation_props.group_name,
                    toAlnum(actor_name),
                    dir_path,
                    header_type,
                    True,
                )
        elif sm64_props.export_type == "Insertable Binary":
            data, ptrs = table.to_binary_combined(animation_props.is_binary_dma, 0)
            path = abspath(os.path.join(animation_props.directory_path, table_props.insertable_file_name))
            writeInsertableFile(path, insertableBinaryTypes["Animation Table"], ptrs, 0, data)
        else:
            raise PluginError(f"Unimplemented export type ({sm64_props.export_type})")

        self.report({"INFO"}, "Animation table exported successfully.")

    def execute(self, context: Context):
        starting_context_mode = context.mode
        try:
            self.execute_operator(context)
            return {"FINISHED"}
        except Exception as exc:
            raisePluginError(self, exc)
            return {"CANCELLED"}
        finally:
            bpy.ops.object.mode_set(mode=get_mode_set_from_context_mode(starting_context_mode))


class SM64_ExportAnim(Operator):
    bl_idname = "scene.sm64_export_anim"
    bl_label = "Export"
    bl_description = "Exports the selected action, select an armature with animation data to use"
    bl_options = {"REGISTER", "UNDO", "PRESET"}

    def execute_operator(self, context: Context):
        bpy.ops.object.mode_set(mode="OBJECT")
        animation_operator_checks(context)

        scene = context.scene
        sm64_props: SM64_Properties = scene.fast64.sm64

        armature_obj: Object = context.selected_objects[0]
        if context.space_data.type != "VIEW_3D" and context.space_data.context == "OBJECT":
            animation_props: SM64_AnimProps = armature_obj.fast64.sm64.animation
        else:
            animation_props: SM64_AnimProps = sm64_props.animation
        table_props: SM64_AnimTableProps = animation_props.table

        action = animation_props.selected_action
        action_props = action.fast64.sm64
        stashActionInArmature(armature_obj, action)

        actor_name = animation_props.actor_name
        animation: SM64_Anim = action_props.to_animation_class(
            action,
            armature_obj,
            sm64_props.blender_to_sm64_scale,
            sm64_props.export_type != "C" or animation_props.header_type == "DMA",
            sm64_props.export_type == "C" or not animation_props.is_binary_dma,
            animation_props.quick_read,
            actor_name,
        )
        if sm64_props.export_type == "C":
            header_type = animation_props.header_type

            anim_dir_path, dir_path, geo_dir_path, level_name = animation_props.get_animation_paths(
                create_directories=True
            )
            anim_file_name = action_props.get_anim_file_name(action)
            anim_path = os.path.join(anim_dir_path, anim_file_name)

            if header_type != "Custom":
                applyBasicTweaks(abspath(sm64_props.decomp_path))

            with open(anim_path, "w", newline="\n") as file:
                file.write(animation.to_c(animation_props.is_c_dma_structure))

            if header_type != "DMA":
                table_name = table_props.get_anim_table_name(actor_name)
                enum_list_name = table_props.get_enum_list_name(actor_name)

                if table_props.update_table:
                    write_anim_header(
                        os.path.join(geo_dir_path, "anim_header.h"),
                        table_name,
                        table_props.generate_enums,
                    )
                    update_table_file(
                        os.path.join(anim_dir_path, "table.inc.c"),
                        action_props.get_enum_and_header_names(action, actor_name),
                        table_name,
                        table_props.generate_enums,
                        False,
                        os.path.join(anim_dir_path, "table_enum.h"),
                        enum_list_name,
                    )
                update_data_file(os.path.join(anim_dir_path, "data.inc.c"), [anim_file_name])

            if not header_type in {"Custom", "DMA"}:
                update_includes(
                    level_name,
                    animation_props.group_name,
                    toAlnum(actor_name),
                    dir_path,
                    header_type,
                    table_props.update_table,
                )
        elif sm64_props.export_type == "Insertable Binary":
            # data, ptrs = animation.to_binary(export_props.is_binary_dma, 0)
            # path = abspath(export_props.insertable_path)
            # writeInsertableFile(path, 2, ptrs, 0, data)
            pass
        else:
            raise PluginError(f"Unimplemented export type ({sm64_props.export_type})")
        self.report({"INFO"}, "Animation exported successfully.")

    def execute(self, context: Context):
        starting_context_mode = context.mode
        try:
            self.execute_operator(context)
            return {"FINISHED"}
        except Exception as exc:
            raisePluginError(self, exc)
            return {"CANCELLED"}
        finally:
            bpy.ops.object.mode_set(mode=get_mode_set_from_context_mode(starting_context_mode))


# Importing
class SM64_ImportAllMarioAnims(Operator):
    bl_idname = "scene.sm64_import_mario_anims"
    bl_label = "Import All Mario Animations"
    bl_options = {"REGISTER", "UNDO", "PRESET"}

    def execute_operator(self, context):
        bpy.ops.object.mode_set(mode="OBJECT")
        animation_operator_checks(context, False)

        scene = context.scene
        sm64_props: SM64_Properties = scene.fast64.sm64

        armature_obj: Object = context.selected_objects[0]
        if context.space_data.type != "VIEW_3D" and context.space_data.context == "OBJECT":
            animation_props: SM64_AnimProps = armature_obj.fast64.sm64.animation
        else:
            animation_props: SM64_AnimProps = sm64_props.animation
        import_props: SM64_AnimImportProps = animation_props.importing

        animations: dict[str, SM64_Anim] = {}
        table: SM64_AnimTable = SM64_AnimTable()

        mario_dma_table_address = 0x4EC000

        if import_props.import_type == "Binary":
            rom_path = abspath(import_props.rom if import_props.rom else sm64_props.import_rom)
            import_rom_checks(rom_path)
            with open(rom_path, "rb") as rom:
                rom_data = rom.read()
                for entrie_str, name, _ in marioAnimationNames[1:]:
                    entrie_num = int(entrie_str)
                    dma_table = DMATable()
                    dma_table.read_binary(rom_data, mario_dma_table_address)
                    if entrie_num < 0 or entrie_num >= len(dma_table.entries):
                        raise PluginError(
                            f"Index {entrie_num} outside of defined table ({len(dma_table.entries)} entries)."
                        )

                    entrie: DMATableEntrie = dma_table.entries[entrie_num]
                    header = import_binary_header(rom_data, entrie.address, True, animations, None)
                    table.elements.append(header)
                    header.reference = toAlnum(name)
                    header.data.action_name = name
        else:
            raise PluginError("Unimplemented import type.")

        for _, data in animations.items():
            animation_import_to_blender(armature_obj, sm64_props.blender_to_sm64_scale, data)
        sm64_props.animation.table.from_anim_table_class(table)

        self.report({"INFO"}, "Success!")
        return {"FINISHED"}

    def execute(self, context: Context):
        starting_context_mode = context.mode
        try:
            self.execute_operator(context)
            return {"FINISHED"}
        except Exception as exc:
            raisePluginError(self, exc)
            return {"CANCELLED"}
        finally:
            bpy.ops.object.mode_set(mode=get_mode_set_from_context_mode(starting_context_mode))


class SM64_ImportAnim(Operator):
    bl_idname = "scene.sm64_import_anim"
    bl_label = "Import Animation(s)"
    bl_options = {"REGISTER", "UNDO", "PRESET"}

    def execute_operator(self, context):
        bpy.ops.object.mode_set(mode="OBJECT")
        animation_operator_checks(context, False)

        scene = context.scene
        sm64_props: SM64_Properties = scene.fast64.sm64
        armature_obj: Object = context.selected_objects[0]
        if context.space_data.type != "VIEW_3D" and context.space_data.context == "OBJECT":
            animation_props: SM64_AnimProps = armature_obj.fast64.sm64.animation
        else:
            animation_props: SM64_AnimProps = sm64_props.animation

        import_props: SM64_AnimImportProps = animation_props.importing
        table_props: SM64_AnimTableProps = animation_props.table

        animations: dict[str, SM64_Anim] = {}
        table = SM64_AnimTable()

        if import_props.import_type == "Binary" or (
            import_props.import_type == "Insertable Binary" and import_props.insertable_read_from_rom
        ):
            rom_path = abspath(import_props.rom if import_props.rom else sm64_props.import_rom)
            import_rom_checks(rom_path)
            with open(rom_path, "rb") as rom_file:
                rom_data = rom_file.read()
                segment_data = parseLevelAtPointer(rom_file, level_pointers[import_props.level]).segmentData
        else:
            rom_data, segment_data = None, None

        anim_bones = get_anim_pose_bones(armature_obj)
        assumed_bone_count = len(anim_bones) if import_props.assume_bone_count else None

        if import_props.import_type == "Binary":
            address = import_props.address
            if import_props.binary_import_type != "DMA" and import_props.is_segmented_address:
                address = decodeSegmentedAddr(address.to_bytes(4, "big"), segment_data)
            import_binary_animations(
                data_reader=RomReading(
                    data=rom_data, start_address=address, rom_data=rom_data, segment_data=segment_data
                ),
                import_type=import_props.binary_import_type,
                animations=animations,
                table_index=None if import_props.read_entire_table else import_props.mario_or_table_index,
                ignore_null=import_props.ignore_null,
                table=table,
                assumed_bone_count=assumed_bone_count,
            )
        elif import_props.import_type == "Insertable Binary":
            path = abspath(import_props.path)
            filepath_checks(path)

            with open(path, "rb") as insertable_file:
                import_insertable_binary_animations(
                    insertable_data_reader=RomReading(insertable_file.read(), 0, None, rom_data, segment_data),
                    animations=animations,
                    table=table,
                    table_index=None if import_props.read_entire_table else import_props.mario_or_table_index,
                    ignore_null=import_props.ignore_null,
                    assumed_bone_count=assumed_bone_count,
                )
        elif import_props.import_type == "C":
            path = abspath(import_props.path)
            path_checks(path)
            import_c_animations(path, animations, table)

        for data in animations.values():
            animation_import_to_blender(
                context.selected_objects[0],
                sm64_props.blender_to_sm64_scale,
                data,
                animation_props.actor_name,
                import_props.remove_name_footer,
                import_props.use_custom_name,
            )
        table_props.from_anim_table_class(table, import_props.clear_table)

        self.report({"INFO"}, "Success!")
        return {"FINISHED"}

    def execute(self, context):
        starting_context_mode = context.mode
        try:
            self.execute_operator(context)
            return {"FINISHED"}
        except Exception as exc:
            raisePluginError(self, exc)
            return {"CANCELLED"}
        finally:
            bpy.ops.object.mode_set(mode=get_mode_set_from_context_mode(starting_context_mode))


class SM64_SearchMarioAnimEnum(Operator):
    bl_idname = "scene.search_mario_anim_enum_operator"
    bl_label = "Search Mario Animations"
    bl_description = "Search Mario Animations"
    bl_property = "mario_animations"
    bl_options = {"UNDO"}

    mario_animations: EnumProperty(items=marioAnimationNames)

    def execute(self, context):
        scene = context.scene
        sm64_props: SM64_Properties = scene.fast64.sm64
        armature_obj: Object = context.selected_objects[0]
        if context.space_data.type != "VIEW_3D" and context.space_data.context == "OBJECT":
            import_props: SM64_AnimImportProps = armature_obj.fast64.sm64.animation.importing
        else:
            import_props: SM64_AnimImportProps = sm64_props.animation.anim_import.importing

        context.region.tag_redraw()
        import_props.mario_animation = int(self.mario_animations)
        self.report({"INFO"}, "Selected: " + self.mario_animations)
        return {"FINISHED"}

    def invoke(self, context, event):
        context.window_manager.invoke_search_popup(self)
        return {"RUNNING_MODAL"}


operators = (
    # Exporting
    SM64_ExportAnimTable,
    SM64_ExportAnim,
    SM64_PreviewAnimOperator,
    SM64_TableOperations,
    SM64_AnimVariantOperations,
    # Importing
    SM64_SearchMarioAnimEnum,
    SM64_ImportAnim,
    SM64_ImportAllMarioAnims,
)


def anim_operator_register():
    for cls in operators:
        register_class(cls)

    bpy.app.handlers.frame_change_pre.append(emulate_no_loop)


def anim_operator_unregister():
    for cls in reversed(operators):
        unregister_class(cls)

    if emulate_no_loop in bpy.app.handlers.frame_change_pre:
        bpy.app.handlers.frame_change_pre.remove(emulate_no_loop)
