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
enumAnimationTables = [("Custom", "Custom Table", "Custom")]
for actor_name, preset_info in ACTOR_PRESET_INFO.items():
    behaviours = ActorPresetInfo.get_member_dict(actor_name, preset_info.animated_behaviours)
    enumAnimatedBehaviours.extend(
        [
            (
                intToHex(address),
                name,
                f"{name} ({intToHex(address)})",
            )
            for name, address in behaviours.items()
        ],
    )
    tables = ActorPresetInfo.get_member_dict(actor_name, preset_info.animation_table)
    enumAnimationTables.extend(
        [
            (
                name,
                name,
                f"{name} ({intToHex(address)}), {preset_info.level}",
            )
            for name, address in tables.items()
        ],
    )

marioAnimationNames = [
    ("Custom", "Custom", "Custom"),
    ("0", "Slow ledge climb up", "0"),
    ("1", "Fall over backwards", "1"),
    ("2", "Backward air kb", "2"),
    ("3", "Dying on back", "3"),
    ("4", "Backflip", "4"),
    ("5", "Climbing up pole", "5"),
    ("6", "Grab pole short", "6"),
    ("7", "Grab pole swing part 1", "7"),
    ("8", "Grab pole swing part 2", "8"),
    ("9", "Handstand idle", "9"),
    ("10", "Handstand jump", "10"),
    ("11", "Start handstand", "11"),
    ("12", "Return from handstand", "12"),
    ("13", "Idle on pole", "13"),
    ("14", "A pose", "14"),
    ("15", "Skid on ground", "15"),
    ("16", "Stop skid", "16"),
    ("17", "Crouch from fast longjump", "17"),
    ("18", "Crouch from a slow longjump", "18"),
    ("19", "Fast longjump", "19"),
    ("20", "Slow longjump", "20"),
    ("21", "Airborne on stomach", "21"),
    ("22", "Walk with light object", "22"),
    ("23", "Run with light object", "23"),
    ("24", "Slow walk with light object", "24"),
    ("25", "Shivering and warming hands", "25"),
    ("26", "Shivering return to idle ", "26"),
    ("27", "Shivering", "27"),
    ("28", "Climb down on ledge", "28"),
    ("29", "Credits - Waving", "29"),
    ("30", "Credits - Look up", "30"),
    ("31", "Credits - Return from look up", "31"),
    ("32", "Credits - Raising hand", "32"),
    ("33", "Credits - Lowering hand", "33"),
    ("34", "Credits - Taking off cap", "34"),
    ("35", "Credits - Start walking and look up", "35"),
    ("36", "Credits - Look back then run", "36"),
    ("37", "Final Bowser - Raise hand and spin", "37"),
    ("38", "Final Bowser - Wing cap take off", "38"),
    ("39", "Credits - Peach sign", "39"),
    ("40", "Stand up from lava boost", "40"),
    ("41", "Fire/Lava burn", "41"),
    ("42", "Wing cap flying", "42"),
    ("43", "Hang on owl", "43"),
    ("44", "Land on stomach", "44"),
    ("45", "Air forward kb", "45"),
    ("46", "Dying on stomach", "46"),
    ("47", "Suffocating", "47"),
    ("48", "Coughing", "48"),
    ("49", "Throw catch key", "49"),
    ("50", "Dying fall over", "50"),
    ("51", "Idle on ledge", "51"),
    ("52", "Fast ledge grab", "52"),
    ("53", "Hang on ceiling", "53"),
    ("54", "Put cap on", "54"),
    ("55", "Take cap off then on", "55"),
    ("56", "Quickly put cap on", "56"),
    ("57", "Head stuck in ground", "57"),
    ("58", "Ground pound landing", "58"),
    ("59", "Triple jump ground-pound", "59"),
    ("60", "Start ground-pound", "60"),
    ("61", "Ground-pound", "61"),
    ("62", "Bottom stuck in ground", "62"),
    ("63", "Idle with light object", "63"),
    ("64", "Jump land with light object", "64"),
    ("65", "Jump with light object", "65"),
    ("66", "Fall land with light object", "66"),
    ("67", "Fall with light object", "67"),
    ("68", "Fall from sliding with light object", "68"),
    ("69", "Sliding on bottom with light object", "69"),
    ("70", "Stand up from sliding with light object", "70"),
    ("71", "Riding shell", "71"),
    ("72", "Walking", "72"),
    ("73", "Forward flip", "73"),
    ("74", "Jump riding shell", "74"),
    ("75", "Land from double jump", "75"),
    ("76", "Double jump fall", "76"),
    ("77", "Single jump", "77"),
    ("78", "Land from single jump", "78"),
    ("79", "Air kick", "79"),
    ("80", "Double jump rise", "80"),
    ("81", "Start forward spinning", "81"),
    ("82", "Throw light object", "82"),
    ("83", "Fall from slide kick", "83"),
    ("84", "Bend kness riding shell", "84"),
    ("85", "Legs stuck in ground", "85"),
    ("86", "General fall", "86"),
    ("87", "General land", "87"),
    ("88", "Being grabbed", "88"),
    ("89", "Grab heavy object", "89"),
    ("90", "Slow land from dive", "90"),
    ("91", "Fly from cannon", "91"),
    ("92", "Moving right while hanging", "92"),
    ("93", "Moving left while hanging", "93"),
    ("94", "Missing cap", "94"),
    ("95", "Pull door walk in", "95"),
    ("96", "Push door walk in", "96"),
    ("97", "Unlock door", "97"),
    ("98", "Start reach pocket", "98"),
    ("99", "Reach pocket", "99"),
    ("100", "Stop reach pocket", "100"),
    ("101", "Ground throw", "101"),
    ("102", "Ground kick", "102"),
    ("103", "First punch", "103"),
    ("104", "Second punch", "104"),
    ("105", "First punch fast", "105"),
    ("106", "Second punch fast", "106"),
    ("107", "Pick up light object", "107"),
    ("108", "Pushing", "108"),
    ("109", "Start riding shell", "109"),
    ("110", "Place light object", "110"),
    ("111", "Forward spinning", "111"),
    ("112", "Backward spinning", "112"),
    ("113", "Breakdance", "113"),
    ("114", "Running", "114"),
    ("115", "Running (unused)", "115"),
    ("116", "Soft back kb", "116"),
    ("117", "Soft front kb", "117"),
    ("118", "Dying in quicksand", "118"),
    ("119", "Idle in quicksand", "119"),
    ("120", "Move in quicksand", "120"),
    ("121", "Electrocution", "121"),
    ("122", "Shocked", "122"),
    ("123", "Backward kb", "123"),
    ("124", "Forward kb", "124"),
    ("125", "Idle heavy object", "125"),
    ("126", "Stand against wall", "126"),
    ("127", "Side step left", "127"),
    ("128", "Side step right", "128"),
    ("129", "Start sleep idle", "129"),
    ("130", "Start sleep scratch", "130"),
    ("131", "Start sleep yawn", "131"),
    ("132", "Start sleep sitting", "132"),
    ("133", "Sleep idle", "133"),
    ("134", "Sleep start laying", "134"),
    ("135", "Sleep laying", "135"),
    ("136", "Dive", "136"),
    ("137", "Slide dive", "137"),
    ("138", "Ground bonk", "138"),
    ("139", "Stop slide light object", "139"),
    ("140", "Slide kick", "140"),
    ("141", "Crouch from slide kick", "141"),
    ("142", "Slide motionless", "142"),
    ("143", "Stop slide", "143"),
    ("144", "Fall from slide", "144"),
    ("145", "Slide", "145"),
    ("146", "Tiptoe", "146"),
    ("147", "Twirl land", "147"),
    ("148", "Twirl", "148"),
    ("149", "Start twirl", "149"),
    ("150", "Stop crouching", "150"),
    ("151", "Start crouching", "151"),
    ("152", "Crouching", "152"),
    ("153", "Crawling", "153"),
    ("154", "Stop crawling", "154"),
    ("155", "Start crawling", "155"),
    ("156", "Summon star", "156"),
    ("157", "Return star approach door", "157"),
    ("158", "Backwards water kb", "158"),
    ("159", "Swim with object part 1", "159"),
    ("160", "Swim with object part 2", "160"),
    ("161", "Flutter kick with object", "161"),
    ("162", "Action end with object in water", "162"),
    ("163", "Stop holding object in water", "163"),
    ("164", "Holding object in water", "164"),
    ("165", "Drowning part 1", "165"),
    ("166", "Drowning part 2", "166"),
    ("167", "Dying in water", "167"),
    ("168", "Forward kb in water", "168"),
    ("169", "Falling from water", "169"),
    ("170", "Swimming part 1", "170"),
    ("171", "Swimming part 2", "171"),
    ("172", "Flutter kick", "172"),
    ("173", "Action end in water", "173"),
    ("174", "Pick up object in water", "174"),
    ("175", "Grab object in water part 2", "175"),
    ("176", "Grab object in water part 1", "176"),
    ("177", "Throw object in water", "177"),
    ("178", "Idle in water", "178"),
    ("179", "Star dance in water", "179"),
    ("180", "Return from in water star dance", "180"),
    ("181", "Grab bowser", "181"),
    ("182", "Swing bowser", "182"),
    ("183", "Release bowser", "183"),
    ("184", "Holding bowser", "184"),
    ("185", "Heavy throw", "185"),
    ("186", "Walk panting", "186"),
    ("187", "Walk with heavy object", "187"),
    ("188", "Turning part 1", "188"),
    ("189", "Turning part 2", "189"),
    ("190", "Side flip land", "190"),
    ("191", "Side flip", "191"),
    ("192", "Triple jump land", "192"),
    ("193", "Triple jump", "193"),
    ("194", "First person", "194"),
    ("195", "Idle head left", "195"),
    ("196", "Idle head right", "196"),
    ("197", "Idle head center", "197"),
    ("198", "Handstand left", "198"),
    ("199", "Handstand right", "199"),
    ("200", "Wake up from sleeping", "200"),
    ("201", "Wake up from laying", "201"),
    ("202", "Start tiptoeing", "202"),
    ("203", "Slide jump", "203"),
    ("204", "Start wallkick", "204"),
    ("205", "Star dance", "205"),
    ("206", "Return from star dance", "206"),
    ("207", "Forwards spinning flip", "207"),
    ("208", "Triple jump fly", "208"),
]