# TODO: Get rid of this

from collections import OrderedDict
from dataclasses import dataclass, field
import dataclasses
import re
from typing import List, Union

from ...utility import PluginError


@dataclass
class IfDefMacro:
    type: str = ""
    value: str = ""


@dataclass
class ParsedValue:
    value: Union[str, int, float] = 0
    if_defs: list[IfDefMacro] = dataclasses.field(default_factory=list)

    def set_or_add(self, value):
        if isinstance(self.value, list):
            self.value.append(value)
        else:
            self.value = value


@dataclass
class MacroCall(ParsedValue):
    name: str = ""


@dataclass
class IndexedValue(ParsedValue):
    name: str = ""


@dataclass
class DesignatedValue(IndexedValue):
    name: str = ""


@dataclass
class EnumIndexedValue(DesignatedValue):
    pass


@dataclass
class Include:
    path: str = ""


@dataclass
class Initialization(ParsedValue):
    keywords: List[str] = field(default_factory=list)
    name: str = ""

    is_extern: bool = False
    is_static: bool = False
    is_const: bool = False
    is_enum: bool = False
    is_struct: bool = False
    pointer_depth: int = 0

    origin_path: str = ""

    def set_attributes_from_struct(self, obj, struct_definition: OrderedDict[str, str]):
        if not isinstance(self.value, ParsedValue) or not isinstance(self.value.value, list):
            raise PluginError("Assumed struct is not a list.")

        for i, element in enumerate(self.value.value):
            if isinstance(element, DesignatedValue):
                if element.name in struct_definition:
                    setattr(obj, struct_definition[element.name], element.value)
            else:
                setattr(obj, list(struct_definition.values())[i], element.value)


delimiters = (
    "->",
    ">>",
    "<<",
    "/*",
    "\n",
    "=",
    ";",
    "{",
    "}",
    "(",
    ")",
    "[",
    "]",
    ",",
    "&",
    "^",
    "#",
    ":",
    '"',
    "'",
    "|",
    "\\",
    "/",
    "%",
    "*",
    ".",
    "+",
    "-",
    ">",
    "<",
)

DELIMITERS_PATTERN = "|".join(map(re.escape, delimiters))

token_pattern = re.compile(
    rf"""
    (?:                      # Non-capturing group for alternatives
        [^{DELIMITERS_PATTERN}\s"']+  # Match characters that are not delimiters or whitespace or quotes
        |
        "[^"]*"               # Match double-quoted strings
        |
        '[^']*'               # Match single-quoted strings
    )
    |
    [{DELIMITERS_PATTERN}]   # Match any of the delimiters
    """,
    re.VERBOSE,
)

comment_pattern = re.compile(r"/\*.*?\*/|//.*?$", re.DOTALL | re.MULTILINE)


@dataclass
class CParser:
    values: list[Initialization] = dataclasses.field(default_factory=list)
    values_by_name: dict[str, Initialization] = dataclasses.field(default_factory=dict)

    cur_initializer: Initialization = dataclasses.field(default_factory=Initialization)
    reading_array_size: bool = False
    reading_keywords: bool = True
    reading_function: bool = False  # Used for stack stuff, functions are not supported
    reading_macro: bool = False

    stack: list[ParsedValue] = dataclasses.field(default_factory=list)
    accumulated_tokens: list[str] = dataclasses.field(default_factory=list)
    accumulated_macro_tokens: list[str] = dataclasses.field(default_factory=list)
    if_defs: list[IfDefMacro] = dataclasses.field(default_factory=list)
    origin_path: str = ""

    def get_tabs(self):
        return "\t" * len(self.stack)

    def handle_accumulated_tokens(self):
        if not self.accumulated_tokens:
            return
        joined = " ".join(self.accumulated_tokens)
        joined_stripped = joined.replace(" ", "").replace("\n", "").replace("\t", "")
        if not joined_stripped:
            return

        if joined_stripped.startswith(('"', "'")):
            value = joined
        elif joined_stripped.startswith("0x"):
            value = int(joined_stripped, 16)
        else:
            try:
                value = float(joined_stripped)
                if value.is_integer():
                    value = int(value)
            except ValueError:
                value = joined_stripped

        self.stack[-1].set_or_add(ParsedValue(value, self.if_defs.copy()))
        if isinstance(self.stack[-1], IndexedValue):
            self.stack.pop()

        self.accumulated_tokens.clear()

    def read_macro(self, prev_token: str, cur_token: str):
        if cur_token == "\n" and not prev_token == "\\":
            macro_type = self.accumulated_macro_tokens[0]
            if macro_type == "include":
                if self.stack:
                    self.stack[-1].set_or_add(Include(self.accumulated_macro_tokens[1]))
            elif macro_type in {"ifdef", "if", "ifndef"}:
                self.if_defs.append(IfDefMacro(macro_type, " ".join(self.accumulated_macro_tokens[1:])))
            elif macro_type in {"elif", "else"}:
                self.if_defs.pop()
                self.if_defs.append(IfDefMacro(macro_type, " ".join(self.accumulated_macro_tokens[1:])))
            elif macro_type == "endif":
                self.if_defs.pop()
            else:
                raise PluginError(f"Unimplemented macro. {macro_type}")

            self.accumulated_macro_tokens.clear()
            self.reading_macro = False
            return

        self.accumulated_macro_tokens.append(cur_token)

    def read_values(self, cur_token: str):
        if cur_token == "=":
            joined = "".join(self.accumulated_tokens).strip()
            if joined.startswith("."):
                indexed_value = DesignatedValue(None, self.if_defs.copy(), joined[1:])
            elif joined.startswith("[") and joined.endswith("]"):
                indexed_value = EnumIndexedValue(None, self.if_defs.copy(), joined[1:-1])
            else:
                indexed_value = IndexedValue(None, self.if_defs.copy(), joined)
            self.accumulated_tokens.clear()

            self.stack[-1].set_or_add(indexed_value)
            self.stack.append(indexed_value)
        elif cur_token == "(":
            macro = MacroCall([], self.if_defs.copy(), "".join(self.accumulated_tokens).strip())
            self.accumulated_tokens.clear()
            self.stack[-1].set_or_add(macro)
            self.stack.append(macro)
        elif cur_token == "{":
            self.handle_accumulated_tokens()

            array = ParsedValue([], self.if_defs.copy())

            self.stack[-1].set_or_add(array)
            self.stack.append(array)
        elif cur_token in {"}", ")"} or (cur_token == ";" and not self.reading_function):
            self.handle_accumulated_tokens()

            self.stack.pop()
            if len(self.stack) == 1 and self.reading_function:
                # Exiting stack because of function
                self.stack.pop()
            if len(self.stack) == 0:
                self.reading_function = False
                self.reading_keywords = True
                self.cur_initializer = Initialization()
            elif isinstance(self.stack[-1], IndexedValue):
                self.stack.pop()
        elif cur_token in {";", ","}:
            self.handle_accumulated_tokens()
        else:
            self.accumulated_tokens.append(cur_token)

    def read_keywords(self, prev_token: str, cur_token: str):
        if self.reading_array_size:
            if cur_token == "]":
                self.reading_array_size = False
            return
        if cur_token == "[":
            self.reading_array_size = True
            return

        if cur_token == "static":
            self.cur_initializer.is_static = True
        elif cur_token == "const":
            self.cur_initializer.is_const = True
        elif cur_token == "extern":
            self.cur_initializer.is_extern = True
        elif cur_token == "enum":
            self.cur_initializer.is_enum = True
        elif cur_token == "struct":
            self.cur_initializer.is_struct = True
        elif cur_token == "*":
            self.cur_initializer.pointer_depth += 1

        elif cur_token in {"=", "{", ";"}:
            self.values.append(self.cur_initializer)
            if prev_token == ")" and cur_token == "{":
                self.reading_function = True

            self.stack.append(self.cur_initializer)

            self.cur_initializer.name = self.cur_initializer.keywords[-1]
            self.values_by_name[self.cur_initializer.name] = self.cur_initializer
            self.cur_initializer.origin_path = self.origin_path
            self.cur_initializer.if_def = self.if_defs.copy()
            self.reading_keywords = False

        elif not cur_token == "\n":
            self.cur_initializer.keywords.append(cur_token)

    def read_c_text(self, text: str, origin_path: str = ""):
        self.cur_initializer = Initialization()
        self.reading_array_size, self.reading_keywords, self.reading_function, self.reading_macro = (
            False,
            True,
            False,
            False,
        )
        self.stack.clear()
        self.accumulated_tokens.clear()
        self.accumulated_macro_tokens.clear()
        self.if_defs.clear()

        self.origin_path = origin_path

        tokens = re.findall(token_pattern, re.sub(comment_pattern, "", text))

        prev_token = ""
        for i, cur_token in enumerate(tokens):
            prev_token = tokens[i - 1] if i > 0 else ""
            # next_token = tokens[i + 1]
            if cur_token == "#":
                self.reading_macro = True
                continue
            if self.reading_macro:
                self.read_macro(prev_token, cur_token)
                continue

            if self.reading_keywords:
                self.read_keywords(prev_token, cur_token)
                if cur_token == "=":
                    continue  # HACK!!!
            if not self.reading_keywords:
                self.read_values(cur_token)
