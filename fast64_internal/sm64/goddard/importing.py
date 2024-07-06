import re
import struct

from ...utility import PluginError
from ..sm64_utility import int_from_str
from ..sm64_classes import RomReader

from .classes import *
from .constants import DYNLIST_CMD_SIZE


comment_pattern = re.compile(r'//.*?$|/\*.*?\*/|\'(?:\\.|[^\\\'])*\'|"(?:\\.|[^\\"])*"', re.DOTALL | re.MULTILINE)
dynlist_pattern = re.compile(r"struct DynList\s+(\w+)\[\]\s*=\s*{\s*(.*?)\s*};", re.DOTALL)
macro_pattern = re.compile(r"(\w+)\s*\((.*?)\)", re.DOTALL)
enum_pattern = re.compile(r"enum\s+\w*\s*{\s*([^}]*)\s*};", re.DOTALL)


def remove_unneeded(text):
    def replacer(match):  # without this, a legal expression int/**/x=5; would become intx=5;
        s = match.group(0)
        if s.startswith("/"):
            return " "  # note: a space and not an empty string
        else:
            return s

    return re.sub(comment_pattern, replacer, text).replace("\n", " ").replace("\t", " ")


def process_dyn_cmd_macro(macro: str, str_args: list[str], dyn_context: DynContext):
    if macro not in dynlist_cmds_by_name:
        print(f"Unknown dynlist macro: {macro}")
        return
    cmd_cls = dynlist_cmds_by_name[macro]
    cmd_fields = cmd_cls.arg_fields()
    if len(cmd_fields) != len(str_args):
        raise ValueError(
            f"Wrong number of arguments for {cmd_cls.__name__}: {len(cmd_fields)} "
            f"expected, but {len(str_args)} found"
        )
    cmd = cmd_cls()
    for field, arg in zip(cmd_fields, str_args):
        try:
            if field.type == DynObjName:
                if dyn_context.use_integer_names and not cmd_cls == SetParamPtr:
                    setattr(cmd, field.name, dyn_context.int_or_enum(arg))
                else:
                    setattr(cmd, field.name, arg if arg != "NULL" else None)
            elif field.type == int:
                setattr(cmd, field.name, dyn_context.int_or_enum(arg))
            elif field.type == float:
                setattr(cmd, field.name, float(arg))
            elif field.type == bool:
                setattr(cmd, field.name, {"true": True, "false": False}.get(arg.lower(), False))
            elif field.type == str:
                setattr(cmd, field.name, arg)
            elif field.type in DynListEnum.__subclasses__():
                setattr(cmd, field.name, field.type[arg])
            elif field.type == list[DynListCmd]:
                setattr(cmd, field.name, dyn_context.lists.setdefault(arg, []))
            elif field.type == ObjShape:
                setattr(cmd, field.name, dyn_context.shapes.setdefault(arg, ObjShape()))
            elif field.type == object:
                setattr(cmd, field.name, dyn_context.objs.setdefault(arg, GdObj()))
            else:
                raise NotImplementedError(f"{field.type} not implemented")
        except ValueError as exc:
            raise ValueError(f"Invalid argument for {cmd_cls.__name__}.{field.name}: {arg}") from exc
    if isinstance(cmd, UseIntegerNames):
        dyn_context.use_integer_names = cmd.enable
    elif isinstance(cmd, SetParamPtr):
        cmd.value = cmd.value if cmd.param == DParmPtr.PARM_PTR_CHAR else int_from_str(cmd.value)

    return cmd


def dynlist_from_c(text: str, dyn_context: DynContext):
    clean_c = remove_unneeded(text)

    for enum_list in enum_pattern.findall(clean_c):
        i = 0
        for enum in enum_list.strip().split(","):
            enum = enum.strip().split("=")
            if len(enum) == 1:
                name, value = enum[0].strip(), i
                i += 1
            else:
                name = enum[0].strip()
                value = i = int_from_str(enum[1])
            dyn_context.enums[name] = UserEnum(name, value)

    for name, content in dynlist_pattern.findall(clean_c):
        cmd_list: list[DynListCmd] = []
        dyn_context.lists[name] = cmd_list
        macro_matches = macro_pattern.findall(content)
        for macro, args in macro_matches:
            macro, args = macro.strip(), args.strip()
            str_args = [arg.strip().lstrip("&") for arg in args.split(",") if arg.strip()]
            cmd_list.append(process_dyn_cmd_macro(macro, str_args, dyn_context))


def dynlist_from_binary(reader: RomReader, dyn_context: DynContext):
    cmd_list = []
    dyn_context.lists[reader.start_address] = cmd_list
    while True:
        cmd_num = reader.read_int(signed=True)
        cmd_cls = dynlist_cmds_by_num[cmd_num]
        field_vars = {}
        fields = cmd_cls.arg_fields()
        for field in fields:
            field_vars[field.metadata.get("var")] = field

        cmd = cmd_cls()
        cmd_list.append(cmd)

        for var_name in ("w1", "w2", "vec.x", "vec.y", "vec.z"):
            if var_name not in field_vars:
                reader.skip(4)
                continue
            field = field_vars[var_name]
            try:
                if field.type == DynObjName:
                    if dyn_context.use_integer_names or cmd_cls == SetParamPtr:
                        setattr(cmd, field.name, reader.read_int(signed=True))
                    else:
                        setattr(cmd, field.name, reader.read_str())
                elif field.type == int:
                    setattr(cmd, field.name, reader.read_int(signed=True))
                elif field.type == float:
                    setattr(cmd, field.name, reader.read_float())
                elif field.type == bool:
                    setattr(cmd, field.name, bool(reader.read_int()))
                elif field.type == str:
                    setattr(cmd, field.name, reader.read_str())
                elif field.type in DynListEnum.__subclasses__():
                    setattr(cmd, field.name, field.type(reader.read_int(signed=True)))
                elif field.type == list[DynListCmd]:
                    ptr = reader.read_ptr()
                    if ptr not in dyn_context.lists:
                        dynlist_from_binary(reader.branch(ptr), dyn_context)
                    setattr(cmd, field.name, dyn_context.lists[ptr])
                elif field.type == ObjShape:
                    try:
                        if field.metadata.get("is_dptr"):
                            ptr = reader.read_ptr(reader.read_ptr())
                        else:
                            ptr = reader.read_ptr()
                        if ptr not in dyn_context.shapes:
                            dyn_context.shapes[ptr] = ObjShape()
                        setattr(cmd, field.name, dyn_context.shapes[ptr])
                    except PluginError as exc:  # Probably outside of the segmnet
                        reader.skip(-4)
                        ptr_val = reader.read_int()
                        setattr(cmd, field.name, ptr_val)
                elif (
                    field.type == object
                ):  # TODO: Data that can be attatched to an object, usually a data group that then gets attatched to an animator
                    reader.read_int()
                    # setattr(cmd, field.name, dyn_context.objs.setdefault(reader.read_ptr(), GdObj()))
                else:
                    raise NotImplementedError(f"{field.type} not implemented")
            except ValueError as exc:
                raise ValueError(f"Failed to read {cmd_cls.__name__}.{field.name}") from exc
        if isinstance(cmd, UseIntegerNames):
            dyn_context.use_integer_names = cmd.enable
        elif isinstance(cmd, SetParamPtr):
            cmd.value = cmd.value if cmd.param == DParmPtr.PARM_PTR_OBJ_VTX else reader.read_str(cmd.value)
        elif cmd_cls == EndList:
            break
    return cmd_list

def dynlist_to_bpy(main_list: list[DynListCmd], dyn_context: DynContext):
    for name, cmd_list in dyn_context.lists.items():
        for cmd in cmd_list:
            pass