ootEnumRoomShapeType = [
    # ("Custom", "Custom", "Custom"),
    ("ROOM_SHAPE_TYPE_NORMAL", "Normal", "Normal"),
    ("ROOM_SHAPE_TYPE_IMAGE", "Image", "Image"),
    ("ROOM_SHAPE_TYPE_CULLABLE", "Cullable", "Cullable"),
]

ootEnumHeaderMenu = [
    ("Child Night", "Child Night", "Child Night"),
    ("Adult Day", "Adult Day", "Adult Day"),
    ("Adult Night", "Adult Night", "Adult Night"),
    ("Cutscene", "Cutscene", "Cutscene"),
]
ootEnumHeaderMenuComplete = [
    ("Child Day", "Child Day", "Child Day"),
] + ootEnumHeaderMenu

ootEnumCameraMode = [
    ("Custom", "Custom", "Custom"),
    ("0x00", "Default", "Default"),
    ("0x10", "Two Views, No C-Up", "Two Views, No C-Up"),
    ("0x20", "Rotating Background, Bird's Eye C-Up", "Rotating Background, Bird's Eye C-Up"),
    ("0x30", "Fixed Background, No C-Up", "Fixed Background, No C-Up"),
    ("0x40", "Rotating Background, No C-Up", "Rotating Background, No C-Up"),
    ("0x50", "Shooting Gallery", "Shooting Gallery"),
]

ootEnumMapLocation = [
    ("Custom", "Custom", "Custom"),
    ("0x00", "Hyrule Field", "Hyrule Field"),
    ("0x01", "Kakariko Village", "Kakariko Village"),
    ("0x02", "Graveyard", "Graveyard"),
    ("0x03", "Zora's River", "Zora's River"),
    ("0x04", "Kokiri Forest", "Kokiri Forest"),
    ("0x05", "Sacred Forest Meadow", "Sacred Forest Meadow"),
    ("0x06", "Lake Hylia", "Lake Hylia"),
    ("0x07", "Zora's Domain", "Zora's Domain"),
    ("0x08", "Zora's Fountain", "Zora's Fountain"),
    ("0x09", "Gerudo Valley", "Gerudo Valley"),
    ("0x0A", "Lost Woods", "Lost Woods"),
    ("0x0B", "Desert Colossus", "Desert Colossus"),
    ("0x0C", "Gerudo's Fortress", "Gerudo's Fortress"),
    ("0x0D", "Haunted Wasteland", "Haunted Wasteland"),
    ("0x0E", "Market", "Market"),
    ("0x0F", "Hyrule Castle", "Hyrule Castle"),
    ("0x10", "Death Mountain Trail", "Death Mountain Trail"),
    ("0x11", "Death Mountain Crater", "Death Mountain Crater"),
    ("0x12", "Goron City", "Goron City"),
    ("0x13", "Lon Lon Ranch", "Lon Lon Ranch"),
    ("0x14", "Dampe's Grave & Windmill", "Dampe's Grave & Windmill"),
    ("0x15", "Ganon's Castle", "Ganon's Castle"),
    ("0x16", "Grottos & Fairy Fountains", "Grottos & Fairy Fountains"),
]

ootEnumSkyboxLighting = [
    # see ``LightMode`` enum in ``z64environment.h``
    ("Custom", "Custom", "Custom"),
    ("LIGHT_MODE_TIME", "Time Of Day", "Time Of Day"),
    ("LIGHT_MODE_SETTINGS", "Indoor", "Indoor"),
]

ootEnumAudioSessionPreset = [
    ("Custom", "Custom", "Custom"),
    ("0x00", "0x00", "0x00"),
]

ootEnumMusicSeq = [
    # see https://github.com/zeldaret/oot/blob/9f09505d34619883748a7dab05071883281c14fd/include/sequence.h#L4-L118
    ("Custom", "Custom", "Custom"),
    ("NA_BGM_GENERAL_SFX", "General Sound Effects", "General Sound Effects"),
    ("NA_BGM_NATURE_AMBIENCE", "Nature Ambiance", "Nature Ambiance"),
    ("NA_BGM_FIELD_LOGIC", "Hyrule Field", "Hyrule Field"),
    (
        "NA_BGM_FIELD_INIT",
        "Hyrule Field (Initial Segment From Loading Area)",
        "Hyrule Field (Initial Segment From Loading Area)",
    ),
    ("NA_BGM_FIELD_DEFAULT_1", "Hyrule Field (Moving Segment 1)", "Hyrule Field (Moving Segment 1)"),
    ("NA_BGM_FIELD_DEFAULT_2", "Hyrule Field (Moving Segment 2)", "Hyrule Field (Moving Segment 2)"),
    ("NA_BGM_FIELD_DEFAULT_3", "Hyrule Field (Moving Segment 3)", "Hyrule Field (Moving Segment 3)"),
    ("NA_BGM_FIELD_DEFAULT_4", "Hyrule Field (Moving Segment 4)", "Hyrule Field (Moving Segment 4)"),
    ("NA_BGM_FIELD_DEFAULT_5", "Hyrule Field (Moving Segment 5)", "Hyrule Field (Moving Segment 5)"),
    ("NA_BGM_FIELD_DEFAULT_6", "Hyrule Field (Moving Segment 6)", "Hyrule Field (Moving Segment 6)"),
    ("NA_BGM_FIELD_DEFAULT_7", "Hyrule Field (Moving Segment 7)", "Hyrule Field (Moving Segment 7)"),
    ("NA_BGM_FIELD_DEFAULT_8", "Hyrule Field (Moving Segment 8)", "Hyrule Field (Moving Segment 8)"),
    ("NA_BGM_FIELD_DEFAULT_9", "Hyrule Field (Moving Segment 9)", "Hyrule Field (Moving Segment 9)"),
    ("NA_BGM_FIELD_DEFAULT_A", "Hyrule Field (Moving Segment 10)", "Hyrule Field (Moving Segment 10)"),
    ("NA_BGM_FIELD_DEFAULT_B", "Hyrule Field (Moving Segment 11)", "Hyrule Field (Moving Segment 11)"),
    ("NA_BGM_FIELD_ENEMY_INIT", "Hyrule Field (Enemy Approaches)", "Hyrule Field (Enemy Approaches)"),
    ("NA_BGM_FIELD_ENEMY_1", "Hyrule Field (Enemy Near Segment 1)", "Hyrule Field (Enemy Near Segment 1)"),
    ("NA_BGM_FIELD_ENEMY_2", "Hyrule Field (Enemy Near Segment 2)", "Hyrule Field (Enemy Near Segment 2)"),
    ("NA_BGM_FIELD_ENEMY_3", "Hyrule Field (Enemy Near Segment 3)", "Hyrule Field (Enemy Near Segment 3)"),
    ("NA_BGM_FIELD_ENEMY_4", "Hyrule Field (Enemy Near Segment 4)", "Hyrule Field (Enemy Near Segment 4)"),
    ("NA_BGM_FIELD_STILL_1", "Hyrule Field (Standing Still Segment 1)", "Hyrule Field (Standing Still Segment 1)"),
    ("NA_BGM_FIELD_STILL_2", "Hyrule Field (Standing Still Segment 2)", "Hyrule Field (Standing Still Segment 2)"),
    ("NA_BGM_FIELD_STILL_3", "Hyrule Field (Standing Still Segment 3)", "Hyrule Field (Standing Still Segment 3)"),
    ("NA_BGM_FIELD_STILL_4", "Hyrule Field (Standing Still Segment 4)", "Hyrule Field (Standing Still Segment 4)"),
    ("NA_BGM_DUNGEON", "Dodongo's Cavern", "Dodongo's Cavern"),
    ("NA_BGM_KAKARIKO_ADULT", "Kakariko Village (Adult)", "Kakariko Village (Adult)"),
    ("NA_BGM_ENEMY", "Enemy Battle", "Enemy Battle"),
    ("NA_BGM_BOSS", "Boss Battle 00", "Boss Battle 00"),
    ("NA_BGM_INSIDE_DEKU_TREE", "Inside the Deku Tree", "Inside the Deku Tree"),
    ("NA_BGM_MARKET", "Market", "Market"),
    ("NA_BGM_TITLE", "Title Theme", "Title Theme"),
    ("NA_BGM_LINK_HOUSE", "Link's House", "Link's House"),
    ("NA_BGM_GAME_OVER", "Game Over", "Game Over"),
    ("NA_BGM_BOSS_CLEAR", "Boss Clear", "Boss Clear"),
    ("NA_BGM_ITEM_GET", "Item Get", "Item Get"),
    ("NA_BGM_OPENING_GANON", "Opening Ganon", "Opening Ganon"),
    ("NA_BGM_HEART_GET", "Heart Get", "Heart Get"),
    ("NA_BGM_OCA_LIGHT", "Prelude Of Light", "Prelude Of Light"),
    ("NA_BGM_JABU_JABU", "Inside Jabu-Jabu's Belly", "Inside Jabu-Jabu's Belly"),
    ("NA_BGM_KAKARIKO_KID", "Kakariko Village (Child)", "Kakariko Village (Child)"),
    ("NA_BGM_GREAT_FAIRY", "Great Fairy's Fountain", "Great Fairy's Fountain"),
    ("NA_BGM_ZELDA_THEME", "Zelda's Theme", "Zelda's Theme"),
    ("NA_BGM_FIRE_TEMPLE", "Fire Temple", "Fire Temple"),
    ("NA_BGM_OPEN_TRE_BOX", "Open Treasure Chest", "Open Treasure Chest"),
    ("NA_BGM_FOREST_TEMPLE", "Forest Temple", "Forest Temple"),
    ("NA_BGM_COURTYARD", "Hyrule Castle Courtyard", "Hyrule Castle Courtyard"),
    ("NA_BGM_GANON_TOWER", "Ganondorf's Theme", "Ganondorf's Theme"),
    ("NA_BGM_LONLON", "Lon Lon Ranch", "Lon Lon Ranch"),
    ("NA_BGM_GORON_CITY", "Goron City", "Goron City"),
    ("NA_BGM_FIELD_MORNING", "Hyrule Field Morning Theme", "Hyrule Field Morning Theme"),
    ("NA_BGM_SPIRITUAL_STONE", "Spiritual Stone Get", "Spiritual Stone Get"),
    ("NA_BGM_OCA_BOLERO", "Bolero of Fire", "Bolero of Fire"),
    ("NA_BGM_OCA_MINUET", "Minuet of Woods", "Minuet of Woods"),
    ("NA_BGM_OCA_SERENADE", "Serenade of Water", "Serenade of Water"),
    ("NA_BGM_OCA_REQUIEM", "Requiem of Spirit", "Requiem of Spirit"),
    ("NA_BGM_OCA_NOCTURNE", "Nocturne of Shadow", "Nocturne of Shadow"),
    ("NA_BGM_MINI_BOSS", "Mini-Boss Battle", "Mini-Boss Battle"),
    ("NA_BGM_SMALL_ITEM_GET", "Obtain Small Item", "Obtain Small Item"),
    ("NA_BGM_TEMPLE_OF_TIME", "Temple of Time", "Temple of Time"),
    ("NA_BGM_EVENT_CLEAR", "Escape from Lon Lon Ranch", "Escape from Lon Lon Ranch"),
    ("NA_BGM_KOKIRI", "Kokiri Forest", "Kokiri Forest"),
    ("NA_BGM_OCA_FAIRY_GET", "Obtain Fairy Ocarina", "Obtain Fairy Ocarina"),
    ("NA_BGM_SARIA_THEME", "Lost Woods", "Lost Woods"),
    ("NA_BGM_SPIRIT_TEMPLE", "Spirit Temple", "Spirit Temple"),
    ("NA_BGM_HORSE", "Horse Race", "Horse Race"),
    ("NA_BGM_HORSE_GOAL", "Horse Race Goal", "Horse Race Goal"),
    ("NA_BGM_INGO", "Ingo's Theme", "Ingo's Theme"),
    ("NA_BGM_MEDALLION_GET", "Obtain Medallion", "Obtain Medallion"),
    ("NA_BGM_OCA_SARIA", "Ocarina Saria's Song", "Ocarina Saria's Song"),
    ("NA_BGM_OCA_EPONA", "Ocarina Epona's Song", "Ocarina Epona's Song"),
    ("NA_BGM_OCA_ZELDA", "Ocarina Zelda's Lullaby", "Ocarina Zelda's Lullaby"),
    ("NA_BGM_OCA_SUNS", "Sun's Song", "Sun's Song"),
    ("NA_BGM_OCA_TIME", "Song of Time", "Song of Time"),
    ("NA_BGM_OCA_STORM", "Song of Storms", "Song of Storms"),
    ("NA_BGM_NAVI_OPENING", "Fairy Flying", "Fairy Flying"),
    ("NA_BGM_DEKU_TREE_CS", "Deku Tree", "Deku Tree"),
    ("NA_BGM_WINDMILL", "Windmill Hut", "Windmill Hut"),
    ("NA_BGM_HYRULE_CS", "Legend of Hyrule", "Legend of Hyrule"),
    ("NA_BGM_MINI_GAME", "Shooting Gallery", "Shooting Gallery"),
    ("NA_BGM_SHEIK", "Sheik's Theme", "Sheik's Theme"),
    ("NA_BGM_ZORA_DOMAIN", "Zora's Domain", "Zora's Domain"),
    ("NA_BGM_APPEAR", "Enter Zelda", "Enter Zelda"),
    ("NA_BGM_ADULT_LINK", "Goodbye to Zelda", "Goodbye to Zelda"),
    ("NA_BGM_MASTER_SWORD", "Master Sword", "Master Sword"),
    ("NA_BGM_INTRO_GANON", "Ganon Intro", "Ganon Intro"),
    ("NA_BGM_SHOP", "Shop", "Shop"),
    ("NA_BGM_CHAMBER_OF_SAGES", "Chamber of the Sages", "Chamber of the Sages"),
    ("NA_BGM_FILE_SELECT", "File Select", "File Select"),
    ("NA_BGM_ICE_CAVERN", "Ice Cavern", "Ice Cavern"),
    ("NA_BGM_DOOR_OF_TIME", "Open Door of Temple of Time", "Open Door of Temple of Time"),
    ("NA_BGM_OWL", "Kaepora Gaebora's Theme", "Kaepora Gaebora's Theme"),
    ("NA_BGM_SHADOW_TEMPLE", "Shadow Temple", "Shadow Temple"),
    ("NA_BGM_WATER_TEMPLE", "Water Temple", "Water Temple"),
    ("NA_BGM_BRIDGE_TO_GANONS", "Ganon's Castle Bridge", "Ganon's Castle Bridge"),
    ("NA_BGM_OCARINA_OF_TIME", "Ocarina of Time", "Ocarina of Time"),
    ("NA_BGM_GERUDO_VALLEY", "Gerudo Valley", "Gerudo Valley"),
    ("NA_BGM_POTION_SHOP", "Potion Shop", "Potion Shop"),
    ("NA_BGM_KOTAKE_KOUME", "Kotake & Koume's Theme", "Kotake & Koume's Theme"),
    ("NA_BGM_ESCAPE", "Escape from Ganon's Castle", "Escape from Ganon's Castle"),
    ("NA_BGM_UNDERGROUND", "Ganon's Castle Under Ground", "Ganon's Castle Under Ground"),
    ("NA_BGM_GANONDORF_BOSS", "Ganondorf Battle", "Ganondorf Battle"),
    ("NA_BGM_GANON_BOSS", "Ganon Battle", "Ganon Battle"),
    ("NA_BGM_END_DEMO", "Seal of Six Sages", "Seal of Six Sages"),
    ("NA_BGM_STAFF_1", "End Credits I", "End Credits I"),
    ("NA_BGM_STAFF_2", "End Credits II", "End Credits II"),
    ("NA_BGM_STAFF_3", "End Credits III", "End Credits III"),
    ("NA_BGM_STAFF_4", "End Credits IV", "End Credits IV"),
    ("NA_BGM_FIRE_BOSS", "King Dodongo & Volvagia Boss Battle", "King Dodongo & Volvagia Boss Battle"),
    ("NA_BGM_TIMED_MINI_GAME", "Mini-Game", "Mini-Game"),
    ("NA_BGM_CUTSCENE_EFFECTS", "Various Cutscene Sounds", "Various Cutscene Sounds"),
    ("NA_BGM_NO_MUSIC", "No Music", "No Music"),
    ("NA_BGM_NATURE_SFX_RAIN", "Nature Ambiance: Rain", "Nature Ambiance: Rain"),
]

ootEnumGlobalObject = [
    ("Custom", "Custom", "Custom"),
    ("OBJECT_INVALID", "None", "None"),
    ("OBJECT_GAMEPLAY_FIELD_KEEP", "Overworld", "gameplay_field_keep"),
    ("OBJECT_GAMEPLAY_DANGEON_KEEP", "Dungeon", "gameplay_dangeon_keep"),
]

ootEnumNaviHints = [
    ("Custom", "Custom", "Custom"),
    ("0x00", "None", "None"),
    ("0x01", "Overworld", "elf_message_field"),
    ("0x02", "Dungeon", "elf_message_ydan"),
]

# The order of this list matters (normal OoT scene order as defined by ``scene_table.h``)
ootEnumSceneID = [
    ("Custom", "Custom", "Custom"),
    ("SCENE_DEKU_TREE", "Inside the Deku Tree (Ydan)", "Ydan"),
    ("SCENE_DODONGOS_CAVERN", "Dodongo's Cavern (Ddan)", "Ddan"),
    ("SCENE_JABU_JABU", "Inside Jabu Jabu's Belly (Bdan)", "Bdan"),
    ("SCENE_FOREST_TEMPLE", "Forest Temple (Bmori1)", "Bmori1"),
    ("SCENE_FIRE_TEMPLE", "Fire Temple (Hidan)", "Hidan"),
    ("SCENE_WATER_TEMPLE", "Water Temple (Mizusin)", "Mizusin"),
    ("SCENE_SPIRIT_TEMPLE", "Spirit Temple (Jyasinzou)", "Jyasinzou"),
    ("SCENE_SHADOW_TEMPLE", "Shadow Temple (Hakadan)", "Hakadan"),
    ("SCENE_BOTTOM_OF_THE_WELL", "Bottom of the Well (Hakadanch)", "Hakadanch"),
    ("SCENE_ICE_CAVERN", "Ice Cavern (Ice Doukuto)", "Ice Doukuto"),
    ("SCENE_GANONS_TOWER", "Ganon's Tower (Ganon)", "Ganon"),
    ("SCENE_GERUDO_TRAINING_GROUND", "Gerudo Training Ground (Men)", "Men"),
    ("SCENE_THIEVES_HIDEOUT", "Thieves' Hideout (Gerudoway)", "Gerudoway"),
    ("SCENE_INSIDE_GANONS_CASTLE", "Inside Ganon's Castle (Ganontika)", "Ganontika"),
    ("SCENE_GANONS_TOWER_COLLAPSE_INTERIOR", "Ganon's Tower (Collapsing) (Ganon Sonogo)", "Ganon Sonogo"),
    (
        "SCENE_INSIDE_GANONS_CASTLE_COLLAPSE",
        "Inside Ganon's Castle (Collapsing) (Ganontika Sonogo)",
        "Ganontika Sonogo",
    ),
    ("SCENE_TREASURE_BOX_SHOP", "Treasure Chest Shop (Takaraya)", "Takaraya"),
    ("SCENE_DEKU_TREE_BOSS", "Gohma's Lair (Ydan Boss)", "Ydan Boss"),
    ("SCENE_DODONGOS_CAVERN_BOSS", "King Dodongo's Lair (Ddan Boss)", "Ddan Boss"),
    ("SCENE_JABU_JABU_BOSS", "Barinade's Lair (Bdan Boss)", "Bdan Boss"),
    ("SCENE_FOREST_TEMPLE_BOSS", "Phantom Ganon's Lair (Moribossroom)", "Moribossroom"),
    ("SCENE_FIRE_TEMPLE_BOSS", "Volvagia's Lair (Fire Bs)", "Fire Bs"),
    ("SCENE_WATER_TEMPLE_BOSS", "Morpha's Lair (Mizusin Bs)", "Mizusin Bs"),
    ("SCENE_SPIRIT_TEMPLE_BOSS", "Twinrova's Lair & Iron Knuckle Mini-Boss Room (Jyasinboss)", "Jyasinboss"),
    ("SCENE_SHADOW_TEMPLE_BOSS", "Bongo Bongo's Lair (Hakadan Bs)", "Hakadan Bs"),
    ("SCENE_GANONDORF_BOSS", "Ganondorf's Lair (Ganon Boss)", "Ganon Boss"),
    (
        "SCENE_GANONS_TOWER_COLLAPSE_EXTERIOR",
        "Ganondorf's Death Scene (Tower Escape Exterior) (Ganon Final)",
        "Ganon Final",
    ),
    ("SCENE_MARKET_ENTRANCE_DAY", "Market Entrance (Child - Day) (Entra)", "Entra"),
    ("SCENE_MARKET_ENTRANCE_NIGHT", "Market Entrance (Child - Night) (Entra N)", "Entra N"),
    ("SCENE_MARKET_ENTRANCE_RUINS", "Market Entrance (Ruins) (Enrui)", "Enrui"),
    ("SCENE_BACK_ALLEY_DAY", "Back Alley (Day) (Market Alley)", "Market Alley"),
    ("SCENE_BACK_ALLEY_NIGHT", "Back Alley (Night) (Market Alley N)", "Market Alley N"),
    ("SCENE_MARKET_DAY", "Market (Child - Day) (Market Day)", "Market Day"),
    ("SCENE_MARKET_NIGHT", "Market (Child - Night) (Market Night)", "Market Night"),
    ("SCENE_MARKET_RUINS", "Market (Ruins) (Market Ruins)", "Market Ruins"),
    ("SCENE_TEMPLE_OF_TIME_EXTERIOR_DAY", "Temple of Time Exterior (Day) (Shrine)", "Shrine"),
    ("SCENE_TEMPLE_OF_TIME_EXTERIOR_NIGHT", "Temple of Time Exterior (Night) (Shrine N)", "Shrine N"),
    ("SCENE_TEMPLE_OF_TIME_EXTERIOR_RUINS", "Temple of Time Exterior (Ruins) (Shrine R)", "Shrine R"),
    ("SCENE_KNOW_IT_ALL_BROS_HOUSE", "Know-It-All Brothers' House (Kokiri Home)", "Kokiri Home"),
    ("SCENE_TWINS_HOUSE", "Twins' House (Kokiri Home3)", "Kokiri Home3"),
    ("SCENE_MIDOS_HOUSE", "Mido's House (Kokiri Home4)", "Kokiri Home4"),
    ("SCENE_SARIAS_HOUSE", "Saria's House (Kokiri Home5)", "Kokiri Home5"),
    ("SCENE_KAKARIKO_CENTER_GUEST_HOUSE", "Carpenter Boss's House (Kakariko)", "Kakariko"),
    ("SCENE_BACK_ALLEY_HOUSE", "Back Alley House (Man in Green) (Kakariko3)", "Kakariko3"),
    ("SCENE_BAZAAR", "Bazaar (Shop1)", "Shop1"),
    ("SCENE_KOKIRI_SHOP", "Kokiri Shop (Kokiri Shop)", "Kokiri Shop"),
    ("SCENE_GORON_SHOP", "Goron Shop (Golon)", "Golon"),
    ("SCENE_ZORA_SHOP", "Zora Shop (Zoora)", "Zoora"),
    ("SCENE_POTION_SHOP_KAKARIKO", "Kakariko Potion Shop (Drag)", "Drag"),
    ("SCENE_POTION_SHOP_MARKET", "Market Potion Shop (Alley Shop)", "Alley Shop"),
    ("SCENE_BOMBCHU_SHOP", "Bombchu Shop (Night Shop)", "Night Shop"),
    ("SCENE_HAPPY_MASK_SHOP", "Happy Mask Shop (Face Shop)", "Face Shop"),
    ("SCENE_LINKS_HOUSE", "Link's House (Link Home)", "Link Home"),
    ("SCENE_DOG_LADY_HOUSE", "Back Alley House (Dog Lady) (Impa)", "Impa"),
    ("SCENE_STABLE", "Stable (Malon Stable)", "Malon Stable"),
    ("SCENE_IMPAS_HOUSE", "Impa's House (Labo)", "Labo"),
    ("SCENE_LAKESIDE_LABORATORY", "Lakeside Laboratory (Hylia Labo)", "Hylia Labo"),
    ("SCENE_CARPENTERS_TENT", "Carpenters' Tent (Tent)", "Tent"),
    ("SCENE_GRAVEKEEPERS_HUT", "Gravekeeper's Hut (Hut)", "Hut"),
    ("SCENE_GREAT_FAIRYS_FOUNTAIN_MAGIC", "Great Fairy's Fountain (Upgrades) (Daiyousei Izumi)", "Daiyousei Izumi"),
    ("SCENE_FAIRYS_FOUNTAIN", "Fairy's Fountain (Healing Fairies) (Yousei Izumi Tate)", "Yousei Izumi Tate"),
    ("SCENE_GREAT_FAIRYS_FOUNTAIN_SPELLS", "Great Fairy's Fountain (Spells) (Yousei Izumi Yoko)", "Yousei Izumi Yoko"),
    ("SCENE_GROTTOS", "Grottos (Kakusiana)", "Kakusiana"),
    ("SCENE_REDEAD_GRAVE", "Grave (Redead) (Hakaana)", "Hakaana"),
    ("SCENE_GRAVE_WITH_FAIRYS_FOUNTAIN", "Grave (Fairy's Fountain) (Hakaana2)", "Hakaana2"),
    ("SCENE_ROYAL_FAMILYS_TOMB", "Royal Family's Tomb (Hakaana Ouke)", "Hakaana Ouke"),
    ("SCENE_SHOOTING_GALLERY", "Shooting Gallery (Syatekijyou)", "Syatekijyou"),
    ("SCENE_TEMPLE_OF_TIME", "Temple of Time (Tokinoma)", "Tokinoma"),
    ("SCENE_CHAMBER_OF_THE_SAGES", "Chamber of the Sages (Kenjyanoma)", "Kenjyanoma"),
    ("SCENE_CASTLE_COURTYARD_GUARDS_DAY", "Castle Hedge Maze (Day) (Hairal Niwa)", "Hairal Niwa"),
    ("SCENE_CASTLE_COURTYARD_GUARDS_NIGHT", "Castle Hedge Maze (Night) (Hairal Niwa N)", "Hairal Niwa N"),
    ("SCENE_CUTSCENE_MAP", "Cutscene Map (Hiral Demo)", "Hiral Demo"),
    ("SCENE_WINDMILL_AND_DAMPES_GRAVE", "Dampé's Grave & Windmill (Hakasitarelay)", "Hakasitarelay"),
    ("SCENE_FISHING_POND", "Fishing Pond (Turibori)", "Turibori"),
    ("SCENE_CASTLE_COURTYARD_ZELDA", "Castle Courtyard (Nakaniwa)", "Nakaniwa"),
    ("SCENE_BOMBCHU_BOWLING_ALLEY", "Bombchu Bowling Alley (Bowling)", "Bowling"),
    ("SCENE_LON_LON_BUILDINGS", "Lon Lon Ranch House & Tower (Souko)", "Souko"),
    ("SCENE_MARKET_GUARD_HOUSE", "Guard House (Miharigoya)", "Miharigoya"),
    ("SCENE_POTION_SHOP_GRANNY", "Granny's Potion Shop (Mahouya)", "Mahouya"),
    ("SCENE_GANON_BOSS", "Ganon's Tower Collapse & Battle Arena (Ganon Demo)", "Ganon Demo"),
    ("SCENE_HOUSE_OF_SKULLTULA", "House of Skulltula (Kinsuta)", "Kinsuta"),
    ("SCENE_HYRULE_FIELD", "Hyrule Field (Spot00)", "Spot00"),
    ("SCENE_KAKARIKO_VILLAGE", "Kakariko Village (Spot01)", "Spot01"),
    ("SCENE_GRAVEYARD", "Graveyard (Spot02)", "Spot02"),
    ("SCENE_ZORAS_RIVER", "Zora's River (Spot03)", "Spot03"),
    ("SCENE_KOKIRI_FOREST", "Kokiri Forest (Spot04)", "Spot04"),
    ("SCENE_SACRED_FOREST_MEADOW", "Sacred Forest Meadow (Spot05)", "Spot05"),
    ("SCENE_LAKE_HYLIA", "Lake Hylia (Spot06)", "Spot06"),
    ("SCENE_ZORAS_DOMAIN", "Zora's Domain (Spot07)", "Spot07"),
    ("SCENE_ZORAS_FOUNTAIN", "Zora's Fountain (Spot08)", "Spot08"),
    ("SCENE_GERUDO_VALLEY", "Gerudo Valley (Spot09)", "Spot09"),
    ("SCENE_LOST_WOODS", "Lost Woods (Spot10)", "Spot10"),
    ("SCENE_DESERT_COLOSSUS", "Desert Colossus (Spot11)", "Spot11"),
    ("SCENE_GERUDOS_FORTRESS", "Gerudo's Fortress (Spot12)", "Spot12"),
    ("SCENE_HAUNTED_WASTELAND", "Haunted Wasteland (Spot13)", "Spot13"),
    ("SCENE_HYRULE_CASTLE", "Hyrule Castle (Spot15)", "Spot15"),
    ("SCENE_DEATH_MOUNTAIN_TRAIL", "Death Mountain Trail (Spot16)", "Spot16"),
    ("SCENE_DEATH_MOUNTAIN_CRATER", "Death Mountain Crater (Spot17)", "Spot17"),
    ("SCENE_GORON_CITY", "Goron City (Spot18)", "Spot18"),
    ("SCENE_LON_LON_RANCH", "Lon Lon Ranch (Spot20)", "Spot20"),
    ("SCENE_OUTSIDE_GANONS_CASTLE", "Ganon's Castle Exterior (Ganon Tou)", "Ganon Tou"),
    ("SCENE_TEST01", "Jungle Gym (Test01)", "Test01"),
    ("SCENE_BESITU", "Ganondorf Test Room (Besitu)", "Besitu"),
    ("SCENE_DEPTH_TEST", "Depth Test (Depth Test)", "Depth Test"),
    ("SCENE_SYOTES", "Stalfos Mini-Boss Room (Syotes)", "Syotes"),
    ("SCENE_SYOTES2", "Stalfos Boss ROom (Syotes2)", "Syotes2"),
    ("SCENE_SUTARU", "Sutaru (Sutaru)", "Sutaru"),
    ("SCENE_HAIRAL_NIWA2", "Castle Hedge Maze (Early) (Hairal Niwa2)", "Hairal Niwa2"),
    ("SCENE_SASATEST", "Sasatest (Sasatest)", "Sasatest"),
    ("SCENE_TESTROOM", "Treasure Chest Room (Testroom)", "Testroom"),
]

ootSceneIDToName = {
    "SCENE_DEKU_TREE": "ydan",
    "SCENE_DODONGOS_CAVERN": "ddan",
    "SCENE_JABU_JABU": "bdan",
    "SCENE_FOREST_TEMPLE": "Bmori1",
    "SCENE_FIRE_TEMPLE": "HIDAN",
    "SCENE_WATER_TEMPLE": "MIZUsin",
    "SCENE_SPIRIT_TEMPLE": "jyasinzou",
    "SCENE_SHADOW_TEMPLE": "HAKAdan",
    "SCENE_BOTTOM_OF_THE_WELL": "HAKAdanCH",
    "SCENE_ICE_CAVERN": "ice_doukutu",
    "SCENE_GANONS_TOWER": "ganon",
    "SCENE_GERUDO_TRAINING_GROUND": "men",
    "SCENE_THIEVES_HIDEOUT": "gerudoway",
    "SCENE_INSIDE_GANONS_CASTLE": "ganontika",
    "SCENE_GANONS_TOWER_COLLAPSE_INTERIOR": "ganon_sonogo",
    "SCENE_INSIDE_GANONS_CASTLE_COLLAPSE": "ganontikasonogo",
    "SCENE_TREASURE_BOX_SHOP": "takaraya",
    "SCENE_DEKU_TREE_BOSS": "ydan_boss",
    "SCENE_DODONGOS_CAVERN_BOSS": "ddan_boss",
    "SCENE_JABU_JABU_BOSS": "bdan_boss",
    "SCENE_FOREST_TEMPLE_BOSS": "moribossroom",
    "SCENE_FIRE_TEMPLE_BOSS": "FIRE_bs",
    "SCENE_WATER_TEMPLE_BOSS": "MIZUsin_bs",
    "SCENE_SPIRIT_TEMPLE_BOSS": "jyasinboss",
    "SCENE_SHADOW_TEMPLE_BOSS": "HAKAdan_bs",
    "SCENE_GANONDORF_BOSS": "ganon_boss",
    "SCENE_GANONS_TOWER_COLLAPSE_EXTERIOR": "ganon_final",
    "SCENE_MARKET_ENTRANCE_DAY": "entra",
    "SCENE_MARKET_ENTRANCE_NIGHT": "entra_n",
    "SCENE_MARKET_ENTRANCE_RUINS": "enrui",
    "SCENE_BACK_ALLEY_DAY": "market_alley",
    "SCENE_BACK_ALLEY_NIGHT": "market_alley_n",
    "SCENE_MARKET_DAY": "market_day",
    "SCENE_MARKET_NIGHT": "market_night",
    "SCENE_MARKET_RUINS": "market_ruins",
    "SCENE_TEMPLE_OF_TIME_EXTERIOR_DAY": "shrine",
    "SCENE_TEMPLE_OF_TIME_EXTERIOR_NIGHT": "shrine_n",
    "SCENE_TEMPLE_OF_TIME_EXTERIOR_RUINS": "shrine_r",
    "SCENE_KNOW_IT_ALL_BROS_HOUSE": "kokiri_home",
    "SCENE_TWINS_HOUSE": "kokiri_home3",
    "SCENE_MIDOS_HOUSE": "kokiri_home4",
    "SCENE_SARIAS_HOUSE": "kokiri_home5",
    "SCENE_KAKARIKO_CENTER_GUEST_HOUSE": "kakariko",
    "SCENE_BACK_ALLEY_HOUSE": "kakariko3",
    "SCENE_BAZAAR": "shop1",
    "SCENE_KOKIRI_SHOP": "kokiri_shop",
    "SCENE_GORON_SHOP": "golon",
    "SCENE_ZORA_SHOP": "zoora",
    "SCENE_POTION_SHOP_KAKARIKO": "drag",
    "SCENE_POTION_SHOP_MARKET": "alley_shop",
    "SCENE_BOMBCHU_SHOP": "night_shop",
    "SCENE_HAPPY_MASK_SHOP": "face_shop",
    "SCENE_LINKS_HOUSE": "link_home",
    "SCENE_DOG_LADY_HOUSE": "impa",
    "SCENE_STABLE": "malon_stable",
    "SCENE_IMPAS_HOUSE": "labo",
    "SCENE_LAKESIDE_LABORATORY": "hylia_labo",
    "SCENE_CARPENTERS_TENT": "tent",
    "SCENE_GRAVEKEEPERS_HUT": "hut",
    "SCENE_GREAT_FAIRYS_FOUNTAIN_MAGIC": "daiyousei_izumi",
    "SCENE_FAIRYS_FOUNTAIN": "yousei_izumi_tate",
    "SCENE_GREAT_FAIRYS_FOUNTAIN_SPELLS": "yousei_izumi_yoko",
    "SCENE_GROTTOS": "kakusiana",
    "SCENE_REDEAD_GRAVE": "hakaana",
    "SCENE_GRAVE_WITH_FAIRYS_FOUNTAIN": "hakaana2",
    "SCENE_ROYAL_FAMILYS_TOMB": "hakaana_ouke",
    "SCENE_SHOOTING_GALLERY": "syatekijyou",
    "SCENE_TEMPLE_OF_TIME": "tokinoma",
    "SCENE_CHAMBER_OF_THE_SAGES": "kenjyanoma",
    "SCENE_CASTLE_COURTYARD_GUARDS_DAY": "hairal_niwa",
    "SCENE_CASTLE_COURTYARD_GUARDS_NIGHT": "hairal_niwa_n",
    "SCENE_CUTSCENE_MAP": "hiral_demo",
    "SCENE_WINDMILL_AND_DAMPES_GRAVE": "hakasitarelay",
    "SCENE_FISHING_POND": "turibori",
    "SCENE_CASTLE_COURTYARD_ZELDA": "nakaniwa",
    "SCENE_BOMBCHU_BOWLING_ALLEY": "bowling",
    "SCENE_LON_LON_BUILDINGS": "souko",
    "SCENE_MARKET_GUARD_HOUSE": "miharigoya",
    "SCENE_POTION_SHOP_GRANNY": "mahouya",
    "SCENE_GANON_BOSS": "ganon_demo",
    "SCENE_HOUSE_OF_SKULLTULA": "kinsuta",
    "SCENE_HYRULE_FIELD": "spot00",
    "SCENE_KAKARIKO_VILLAGE": "spot01",
    "SCENE_GRAVEYARD": "spot02",
    "SCENE_ZORAS_RIVER": "spot03",
    "SCENE_KOKIRI_FOREST": "spot04",
    "SCENE_SACRED_FOREST_MEADOW": "spot05",
    "SCENE_LAKE_HYLIA": "spot06",
    "SCENE_ZORAS_DOMAIN": "spot07",
    "SCENE_ZORAS_FOUNTAIN": "spot08",
    "SCENE_GERUDO_VALLEY": "spot09",
    "SCENE_LOST_WOODS": "spot10",
    "SCENE_DESERT_COLOSSUS": "spot11",
    "SCENE_GERUDOS_FORTRESS": "spot12",
    "SCENE_HAUNTED_WASTELAND": "spot13",
    "SCENE_HYRULE_CASTLE": "spot15",
    "SCENE_DEATH_MOUNTAIN_TRAIL": "spot16",
    "SCENE_DEATH_MOUNTAIN_CRATER": "spot17",
    "SCENE_GORON_CITY": "spot18",
    "SCENE_LON_LON_RANCH": "spot20",
    "SCENE_OUTSIDE_GANONS_CASTLE": "ganon_tou",
    "SCENE_TEST01": "test01",
    "SCENE_BESITU": "besitu",
    "SCENE_DEPTH_TEST": "depth_test",
    "SCENE_SYOTES": "syotes",
    "SCENE_SYOTES2": "syotes2",
    "SCENE_SUTARU": "sutaru",
    "SCENE_HAIRAL_NIWA2": "hairal_niwa2",
    "SCENE_SASATEST": "sasatest",
    "SCENE_TESTROOM": "testroom",
}
ootSceneNameToID = {val: key for key, val in ootSceneIDToName.items()}

ootEnumCamTransition = [
    ("Custom", "Custom", "Custom"),
    ("0x00", "0x00", "0x00"),
    # ("0x0F", "0x0F", "0x0F"),
    # ("0xFF", "0xFF", "0xFF"),
]

ootEnumDrawConfig = [
    ("Custom", "Custom", "Custom"),
    ("SDC_DEFAULT", "Default", "Default"),
    ("SDC_HYRULE_FIELD", "Hyrule Field (Spot00)", "Spot00"),
    ("SDC_KAKARIKO_VILLAGE", "Kakariko Village (Spot01)", "Spot01"),
    ("SDC_ZORAS_RIVER", "Zora's River (Spot03)", "Spot03"),
    ("SDC_KOKIRI_FOREST", "Kokiri Forest (Spot04)", "Spot04"),
    ("SDC_LAKE_HYLIA", "Lake Hylia (Spot06)", "Spot06"),
    ("SDC_ZORAS_DOMAIN", "Zora's Domain (Spot07)", "Spot07"),
    ("SDC_ZORAS_FOUNTAIN", "Zora's Fountain (Spot08)", "Spot08"),
    ("SDC_GERUDO_VALLEY", "Gerudo Valley (Spot09)", "Spot09"),
    ("SDC_LOST_WOODS", "Lost Woods (Spot10)", "Spot10"),
    ("SDC_DESERT_COLOSSUS", "Desert Colossus (Spot11)", "Spot11"),
    ("SDC_GERUDOS_FORTRESS", "Gerudo's Fortress (Spot12)", "Spot12"),
    ("SDC_HAUNTED_WASTELAND", "Haunted Wasteland (Spot13)", "Spot13"),
    ("SDC_HYRULE_CASTLE", "Hyrule Castle (Spot15)", "Spot15"),
    ("SDC_DEATH_MOUNTAIN_TRAIL", "Death Mountain Trail (Spot16)", "Spot16"),
    ("SDC_DEATH_MOUNTAIN_CRATER", "Death Mountain Crater (Spot17)", "Spot17"),
    ("SDC_GORON_CITY", "Goron City (Spot18)", "Spot18"),
    ("SDC_LON_LON_RANCH", "Lon Lon Ranch (Spot20)", "Spot20"),
    ("SDC_FIRE_TEMPLE", "Fire Temple (Hidan)", "Hidan"),
    ("SDC_DEKU_TREE", "Inside the Deku Tree (Ydan)", "Ydan"),
    ("SDC_DODONGOS_CAVERN", "Dodongo's Cavern (Ddan)", "Ddan"),
    ("SDC_JABU_JABU", "Inside Jabu Jabu's Belly (Bdan)", "Bdan"),
    ("SDC_FOREST_TEMPLE", "Forest Temple (Bmori1)", "Bmori1"),
    ("SDC_WATER_TEMPLE", "Water Temple (Mizusin)", "Mizusin"),
    ("SDC_SHADOW_TEMPLE_AND_WELL", "Shadow Temple (Hakadan)", "Hakadan"),
    ("SDC_SPIRIT_TEMPLE", "Spirit Temple (Jyasinzou)", "Jyasinzou"),
    ("SDC_INSIDE_GANONS_CASTLE", "Inside Ganon's Castle (Ganontika)", "Ganontika"),
    ("SDC_GERUDO_TRAINING_GROUND", "Gerudo Training Ground (Men)", "Men"),
    ("SDC_DEKU_TREE_BOSS", "Gohma's Lair (Ydan Boss)", "Ydan Boss"),
    ("SDC_WATER_TEMPLE_BOSS", "Morpha's Lair (Mizusin Bs)", "Mizusin Bs"),
    ("SDC_TEMPLE_OF_TIME", "Temple of Time (Tokinoma)", "Tokinoma"),
    ("SDC_GROTTOS", "Grottos (Kakusiana)", "Kakusiana"),
    ("SDC_CHAMBER_OF_THE_SAGES", "Chamber of the Sages (Kenjyanoma)", "Kenjyanoma"),
    ("SDC_GREAT_FAIRYS_FOUNTAIN", "Great Fairy Fountain", "Great Fairy Fountain"),
    ("SDC_SHOOTING_GALLERY", "Shooting Gallery (Syatekijyou)", "Syatekijyou"),
    ("SDC_CASTLE_COURTYARD_GUARDS", "Castle Hedge Maze (Day) (Hairal Niwa)", "Hairal Niwa"),
    ("SDC_OUTSIDE_GANONS_CASTLE", "Ganon's Castle Exterior (Ganon Tou)", "Ganon Tou"),
    ("SDC_ICE_CAVERN", "Ice Cavern (Ice Doukuto)", "Ice Doukuto"),
    (
        "SDC_GANONS_TOWER_COLLAPSE_EXTERIOR",
        "Ganondorf's Death Scene (Tower Escape Exterior) (Ganon Final)",
        "Ganon Final",
    ),
    ("SDC_FAIRYS_FOUNTAIN", "Fairy Fountain", "Fairy Fountain"),
    ("SDC_THIEVES_HIDEOUT", "Thieves' Hideout (Gerudoway)", "Gerudoway"),
    ("SDC_BOMBCHU_BOWLING_ALLEY", "Bombchu Bowling Alley (Bowling)", "Bowling"),
    ("SDC_ROYAL_FAMILYS_TOMB", "Royal Family's Tomb (Hakaana Ouke)", "Hakaana Ouke"),
    ("SDC_LAKESIDE_LABORATORY", "Lakeside Laboratory (Hylia Labo)", "Hylia Labo"),
    ("SDC_LON_LON_BUILDINGS", "Lon Lon Ranch House & Tower (Souko)", "Souko"),
    ("SDC_MARKET_GUARD_HOUSE", "Guard House (Miharigoya)", "Miharigoya"),
    ("SDC_POTION_SHOP_GRANNY", "Granny's Potion Shop (Mahouya)", "Mahouya"),
    ("SDC_CALM_WATER", "Calm Water", "Calm Water"),
    ("SDC_GRAVE_EXIT_LIGHT_SHINING", "Grave Exit Light Shining", "Grave Exit Light Shining"),
    ("SDC_BESITU", "Ganondorf Test Room (Besitu)", "Besitu"),
    ("SDC_FISHING_POND", "Fishing Pond (Turibori)", "Turibori"),
    ("SDC_GANONS_TOWER_COLLAPSE_INTERIOR", "Ganon's Tower (Collapsing) (Ganon Sonogo)", "Ganon Sonogo"),
    ("SDC_INSIDE_GANONS_CASTLE_COLLAPSE", "Inside Ganon's Castle (Collapsing) (Ganontika Sonogo)", "Ganontika Sonogo"),
]

oot_world_defaults = {
    "geometryMode": {
        "zBuffer": True,
        "shade": True,
        "cullBack": True,
        "lighting": True,
        "shadeSmooth": True,
    },
    "otherModeH": {
        "alphaDither": "G_AD_NOISE",
        "textureFilter": "G_TF_BILERP",
        "perspectiveCorrection": "G_TP_PERSP",
        "textureConvert": "G_TC_FILT",
        "cycleType": "G_CYC_2CYCLE",
    },
}
