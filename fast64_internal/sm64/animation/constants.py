import re
import struct

from ...utility import intToHex, COMMENT_PATTERN
from ..sm64_constants import ACTOR_PRESET_INFO, ActorPresetInfo

HEADER_STRUCT = struct.Struct(">h h h h h h I I I")
HEADER_SIZE = HEADER_STRUCT.size

TABLE_ELEMENT_PATTERN = re.compile(  # strict but only in the sense that it requires valid c code
    r"""
    (?:COMMENT_PATTERN)|
    (?:\[\s*(?P<enum>\w+)\s*\]\s*=\s*)? # Don´t capture brackets or equal, works with nums
    (?:(?:&\s*(?P<element>\w+))|(?:NULL)) # Capture element or null, element requires &
    (?:\s*,|) # allow no comma, techinically not correct but no other method works
    """.replace(
        "COMMENT_PATTERN", COMMENT_PATTERN.pattern
    ),
    re.DOTALL | re.VERBOSE | re.MULTILINE,
)


TABLE_PATTERN = re.compile(
    r"""
    SKIP_COMMENT # CURRENTLY DOESNT WORK, FIX
    const\s+struct\s*Animation\s*\*const\s*(?P<name>\w+)
    (?:\[.*?\])? # Optional size, don´t capture
    \s*=\s*\{
        (?P<content>(?:COMMENT_PATTERN|[\s\S])*) # Capture any character including new lines
    (?=\}\s*;) # Look ahead for the end
    """.replace(
        "SKIP_COMMENT", f"(?:^(?:{COMMENT_PATTERN}))*"
    ).replace(
        "COMMENT_PATTERN", COMMENT_PATTERN.pattern
    ),
    re.DOTALL | re.VERBOSE | re.MULTILINE,
)


TABLE_ENUM_PATTERN = re.compile(  # strict but only in the sense that it requires valid c code
    r"""
    SKIP_COMMENT
    (?P<name>\w+)\s*
    (?:\s*=\s*(?P<num>\w+)\s*)?
    (?=,|) # lookahead, allow no comma, techinically not correct but no other method works
    """.replace(
        "SKIP_COMMENT", f"(?:^(?:{COMMENT_PATTERN.pattern}))*?"
    ),
    re.DOTALL | re.VERBOSE | re.MULTILINE,
)


TABLE_ENUM_LIST_PATTERN = re.compile(
    r"""
    SKIP_COMMENT
    enum\s*(?P<name>\w+)\s*\{
        (?P<content>(?:COMMENT_PATTERN|[\s\S])*) # Capture any character including new lines, lazy
    (?=\}\s*;)
    """.replace(
        "SKIP_COMMENT", f"(?:^(?:{COMMENT_PATTERN.pattern}))*?"
    ).replace(
        "COMMENT_PATTERN", COMMENT_PATTERN.pattern
    ),
    re.DOTALL | re.VERBOSE | re.MULTILINE,
)


enumAnimExportTypes = [
    ("Actor", "Actor Data", "Includes are added to a group in actors/"),
    ("Level", "Level Data", "Includes are added to a specific level in levels/"),
    (
        "DMA",
        "DMA (Mario)",
        "No headers or includes are genarated. Mario animation converter order is used (headers, indicies, values)",
    ),
    ("Custom", "Custom Path", "Exports to a specific path"),
]

enum_anim_import_types = [
    ("C", "C", "Import a decomp folder or a specific animation"),
    ("Binary", "Binary", "Import from ROM"),
    ("Insertable Binary", "Insertable Binary", "Import from an insertable binary file"),
]

enum_anim_binary_import_types = [
    ("DMA", "DMA (Mario)", "Import a DMA animation from a DMA table from a ROM"),
    ("Table", "Table", "Import animations from an animation table from a ROM"),
    ("Animation", "Animation", "Import one animation from a ROM"),
]


enum_animated_behaviours = [("Custom", "Custom Behavior", "Custom"), ("", "Presets", "")]
enum_anim_tables = [("Custom", "Custom", "Custom"), ("", "Presets", "")]
for actor_name, preset_info in ACTOR_PRESET_INFO.items():
    if not preset_info.animation:
        continue
    behaviours = ActorPresetInfo.get_member_as_dict(actor_name, preset_info.animation.behaviours)
    enum_animated_behaviours.extend(
        [(intToHex(address), name, intToHex(address)) for name, address in behaviours.items()]
    )
    tables = ActorPresetInfo.get_member_as_dict(actor_name, preset_info.animation.address)
    enum_anim_tables.extend(
        [(name, name, f"{intToHex(address)}, {preset_info.level}") for name, address in tables.items()]
    )
