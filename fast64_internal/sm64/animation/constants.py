from ...utility import intToHex
from ..sm64_constants import ACTOR_PRESET_INFO, ActorPresetInfo


HEADER_SIZE = 0x18
C_FLAGS = [
    ("ANIM_FLAG_NOLOOP",),
    ("ANIM_FLAG_FORWARD", "ANIM_FLAG_BACKWARD"),
    ("ANIM_FLAG_NO_ACCEL", "ANIM_FLAG_2"),
    ("ANIM_FLAG_HOR_TRANS",),
    ("ANIM_FLAG_VERT_TRANS",),
    ("ANIM_FLAG_DISABLED", "ANIM_FLAG_5"),
    ("ANIM_FLAG_NO_TRANS", "ANIM_FLAG_6"),
    # Not used anywhere and has no functionality, let it be picked up as custom
    # ("ANIM_FLAG_UNUSED", "ANIM_FLAG_7"),
]

FLAG_PROPS = [
    "no_loop",
    "backwards",
    "no_acceleration",
    "only_horizontal_trans",
    "only_vertical_trans",
    "disabled",
    "no_trans",
]

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

enumAnimImportTypes = [
    ("C", "C", "Import a decomp folder or a specific animation"),
    ("Binary", "Binary", "Import from ROM"),
    ("Insertable Binary", "Insertable Binary", "Import from an insertable binary file"),
]

enumAnimBinaryImportTypes = [
    ("DMA", "DMA (Mario)", "Import a DMA animation from a DMA table from a ROM"),
    ("Table", "Table", "Import animations from an animation table from a ROM"),
    ("Animation", "Animation", "Import one animation from a ROM"),
]


enumAnimatedBehaviours = [("Custom", "Custom Behavior", "Custom")]
enumAnimationTables = [("Custom", "Custom", "Custom")]
for actor_name, preset_info in ACTOR_PRESET_INFO.items():
    if not preset_info.animation:
        continue
    behaviours = ActorPresetInfo.get_member_as_dict(actor_name, preset_info.animation.behaviours)
    enumAnimatedBehaviours.extend(
        [
            (
                intToHex(address),
                name,
                intToHex(address),
            )
            for name, address in behaviours.items()
        ]
    )
    tables = ActorPresetInfo.get_member_as_dict(actor_name, preset_info.animation.address)
    enumAnimationTables.extend(
        [
            (
                name,
                name,
                f"{intToHex(address)}, {preset_info.level}",
            )
            for name, address in tables.items()
        ]
    )