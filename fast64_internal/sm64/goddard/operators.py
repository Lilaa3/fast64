from io import StringIO
import os
import pprint

from bpy.utils import register_class, unregister_class
from bpy.types import Context
from bpy.path import abspath

from ...operators import OperatorBase
from ..sm64_utility import import_rom_checks, int_from_str
from ..sm64_classes import RomReader

from .importing import dynlist_from_c, dynlist_from_binary, dynlist_to_bpy
from .classes import DynContext


class SM64_ImportDynList(OperatorBase):
    bl_idname = "sm64.import_dynlist"
    bl_label = "Import DynList"
    icon = "IMPORT"

    def execute_operator(self, context: Context):
        sm64_props = context.scene.fast64.sm64
        importing_props = sm64_props.goddard.importing

        dyn_context = DynContext()

        if importing_props.import_type == "Binary":
            import_rom_checks(abspath(sm64_props.import_rom))
            segment_data = {
                4: (0x2739A0, 0x2A6120),  # Dynlist segment
                # 128: (0x21F4C0, 0x269EA0),  # Goddard segment
                # 1: (0x269EA0, 0x269EA0),  # Goddard bss data segment
            }
            address = int_from_str(importing_props.address)
            with open(abspath(sm64_props.import_rom), "rb") as f:
                reader = RomReader(f, start_address=address, segment_data=segment_data)
                DynContext.main_list = dynlist_from_binary(reader, dyn_context)
        else:
            # TODO: Update this to let the user type in a dynlist name
            # file_path = importing_props.get_file_path(sm64_props.decomp_path)
            text = StringIO()
            for root, _, files in os.walk(importing_props.get_path(sm64_props.decomp_path)):
                for file_name in files:
                    with open(os.path.join(root, file_name), "r", encoding="utf-8") as f:
                        text.write(f.read())
            DynContext.main_list = dynlist_from_c(text.getvalue(), dyn_context)
        pprint.pprint(dyn_context.main_list)
        dynlist_to_bpy(dyn_context.main_list, dyn_context)
        return {"FINISHED"}


classes = (SM64_ImportDynList,)


def goddard_operators_register():
    for cls in classes:
        register_class(cls)


def goddard_operators_unregister():
    for cls in classes:
        unregister_class(cls)
