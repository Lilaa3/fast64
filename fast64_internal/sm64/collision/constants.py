import dataclasses
from enum import Enum

enumSM64CollisionFormat = [
    ("SM64", "SM64", "SM64´s collision format (enum)"),
    ("HackerSM64", "HackerSM64 3.0", "HackerSM64´s collision format (32 bit bitfield struct)"),
]

enumObjectType = [
    ("None", "None", "None"),
    ("Special", "Special", "Special"),
    ("Water Box", "Water Box", "Water Box"),
]

enumCollisionTypeOptions = [
    ("SIMPLE", "Simple", "Simple"),
    ("ALL", "All", "All"),
    ("CUSTOM", "Custom", "Custom"),
]

enumCollisionTypeSimple = [
    ("", "Non-Force Based", ""),  # Non-Force based collumn
    ("SURFACE_DEFAULT", "Default", "Default"),
    ("SURFACE_BURNING", "Burning", "Burning"),
    ("SURFACE_HANGABLE", "Hangable", "Hangable"),
    ("SURFACE_DEATH_PLANE", "Death Plane", "Death Plane"),
    ("SURFACE_VERY_SLIPPERY", "Very Slippery", "Very Slippery"),
    ("SURFACE_SLIPPERY", "Slippery", "Slippery"),
    ("SURFACE_NOT_SLIPPERY", "Not Slippery", "Not Slippery"),
    ("SURFACE_NOISE_DEFAULT", "Noise Default", "Noise Default"),
    ("SURFACE_NOISE_SLIPPERY", "Noise Slippery", "Noise Slippery"),
    ("SURFACE_ICE", "Ice", "Ice"),
    ("SURFACE_HARD", "Hard", "Hard"),
    ("SURFACE_HARD_SLIPPERY", "Hard Slippery", "Hard Slippery"),
    ("", "", ""),
    ("SURFACE_HARD_VERY_SLIPPERY", "Hard Very Slippery", "Hard Very Slippery"),
    ("SURFACE_HARD_NOT_SLIPPERY", "Hard Not Slippery", "Hard Not Slippery"),
    ("SURFACE_WALL_MISC", "Wall Misc", "Wall Misc"),
    ("SURFACE_SLOW", "Slow", "Slow"),
    ("SURFACE_SWITCH", "Switch", "Switch"),
    ("SURFACE_VANISH_CAP_WALLS", "Vanish Cap Walls", "Vanish Cap Walls"),
    ("SURFACE_INTANGIBLE", "Intangible", "Intangible"),
    ("", "Force Based", ""),  # Force based collumn
    ("SURFACE_FLOWING_WATER", "Flowing Water", "Flowing Water"),
    ("SURFACE_HORIZONTAL_WIND", "Horizontal Wind", "Horizontal Wind"),
    ("SURFACE_VERTICAL_WIND", "Vertical Wind", "Vertical Wind"),
    ("SURFACE_SHALLOW_QUICKSAND", "Shallow Quicksand", "Shallow Quicksand"),
    ("SURFACE_DEEP_QUICKSAND", "Deep Quicksand", "Deep Quicksand"),
    ("SURFACE_INSTANT_QUICKSAND", "Instant Quicksand", "Instant Quicksand"),
    ("SURFACE_DEEP_MOVING_QUICKSAND", "Deep Moving Quicksand", "Deep Moving Quicksand"),
    ("SURFACE_SHALLOW_MOVING_QUICKSAND", "Shallow Moving Quicksand", "Shallow Moving Quicksand"),
    ("SURFACE_QUICKSAND", "Quicksand", "Quicksand"),
    ("SURFACE_MOVING_QUICKSAND", "Moving Quicksand", "Moving Quicksand"),
    ("SURFACE_INSTANT_MOVING_QUICKSAND", "Instant Moving Quicksand", "Instant Moving Quicksand"),
]

enumCollisionType = [
    ("SURFACE_DEFAULT", "Default", "Environment default"),
    ("SURFACE_BURNING", "Burning", "Lava / Frostbite (in SL), but is used mostly for Lava"),
    ("SURFACE_0004", "Unused", "Unused, has no function and has parameters"),
    ("SURFACE_HANGABLE", "Hangable", "Ceiling that Mario can climb on"),
    ("SURFACE_SLOW", "Slow", "Slow down Mario, unused"),
    ("SURFACE_DEATH_PLANE", "Death Plane", "Death floor"),
    ("SURFACE_CLOSE_CAMERA", "Close Camera", "Close camera"),
    ("SURFACE_WATER", "Water", "Water, has no action, used on some waterboxes below"),
    ("SURFACE_FLOWING_WATER", "Flowing Water", "Water (flowing), has parameters"),
    ("SURFACE_INTANGIBLE", "Intangible", "Intangible (Separates BBH mansion from merry-go-round, for room usage)"),
    ("SURFACE_VERY_SLIPPERY", "Very Slippery", "Very slippery, mostly used for slides"),
    ("SURFACE_SLIPPERY", "Slippery", "Slippery"),
    ("SURFACE_NOT_SLIPPERY", "Not Slippery", "Non-slippery, climbable"),
    ("SURFACE_TTM_VINES", "TTM Vines", "TTM vines, has no action defined"),
    (
        "SURFACE_MGR_MUSIC",
        "Mgr Music",
        "Plays the Merry go round music, see handle_merry_go_round_music in bbh_merry_go_round.inc.c for more details",
    ),
    (
        "SURFACE_INSTANT_WARP_1B",
        "Instant Warp 1B",
        "Instant warp to another area, used to warp between areas in WDW and the endless stairs to warp back",
    ),
    ("SURFACE_INSTANT_WARP_1C", "Instant Warp 1C", "Instant warp to another area, used to warp between areas in WDW"),
    (
        "SURFACE_INSTANT_WARP_1D",
        "Instant Warp 1D",
        "Instant warp to another area, used to warp between areas in DDD, SSL and TTM",
    ),
    (
        "SURFACE_INSTANT_WARP_1E",
        "Instant Warp 1E",
        "Instant warp to another area, used to warp between areas in DDD, SSL and TTM",
    ),
    ("SURFACE_SHALLOW_QUICKSAND", "Shallow Quicksand", "Shallow Quicksand (depth of 10 units)"),
    ("SURFACE_DEEP_QUICKSAND", "Deep Quicksand", "Quicksand (lethal, slow, depth of 160 units)"),
    ("SURFACE_INSTANT_QUICKSAND", "Instant Quicksand", "Quicksand (lethal, instant)"),
    ("SURFACE_DEEP_MOVING_QUICKSAND", "Deep Moving Quicksand", "Moving quicksand (flowing, depth of 160 units)"),
    ("SURFACE_SHALLOW_MOVING_QUICKSAND", "Shallow Moving Quicksand", "Moving quicksand (flowing, depth of 25 units)"),
    ("SURFACE_QUICKSAND", "Quicksand", "Moving quicksand (60 units)"),
    ("SURFACE_MOVING_QUICKSAND", "Moving Quicksand", "Moving quicksand (flowing, depth of 60 units)"),
    (
        "SURFACE_WALL_MISC",
        "Wall Misc",
        "Used for some walls, Cannon to adjust the camera, and some objects like Warp Pipe",
    ),
    ("SURFACE_NOISE_DEFAULT", "Noise Default", "Default floor with noise"),
    ("SURFACE_NOISE_SLIPPERY", "Noise Slippery", "Slippery floor with noise"),
    ("SURFACE_HORIZONTAL_WIND", "Horizontal Wind", "Horizontal wind, has parameters"),
    ("SURFACE_INSTANT_MOVING_QUICKSAND", "Instant Moving Quicksand", "Quicksand (lethal, flowing)"),
    ("SURFACE_ICE", "Ice", "Slippery Ice, in snow levels and THI's water floor"),
    ("SURFACE_LOOK_UP_WARP", "Look Up Warp", "Look up and warp (Wing cap entrance)"),
    ("SURFACE_HARD", "Hard", "Hard floor (Always has fall damage)"),
    ("SURFACE_WARP", "Warp", "Surface warp"),
    ("SURFACE_TIMER_START", "Timer Start", "Timer start (Peach's secret slide)"),
    ("SURFACE_TIMER_END", "Timer End", "Timer stop (Peach's secret slide)"),
    ("SURFACE_HARD_SLIPPERY", "Hard Slippery", "Hard and slippery (Always has fall damage)"),
    ("SURFACE_HARD_VERY_SLIPPERY", "Hard Very Slippery", "Hard and very slippery (Always has fall damage)"),
    ("SURFACE_HARD_NOT_SLIPPERY", "Hard Not Slippery", "Hard and Non-slippery (Always has fall damage)"),
    ("SURFACE_VERTICAL_WIND", "Vertical Wind", "Death at bottom with vertical wind"),
    ("SURFACE_BOSS_FIGHT_CAMERA", "Boss Fight Camera", "Wide camera for BoB and WF bosses"),
    ("SURFACE_CAMERA_FREE_ROAM", "Camera Free Roam", "Free roam camera for THI and TTC"),
    (
        "SURFACE_THI3_WALLKICK",
        "THI3 Wallkick",
        "Surface where there's a wall kick section in THI 3rd area, has no action defined",
    ),
    ("SURFACE_CAMERA_8_DIR", "Camera 8 Dir", "Surface that enables far camera for platforms, used in THI"),
    (
        "SURFACE_CAMERA_MIDDLE",
        "Camera Middle",
        "Surface camera that returns to the middle, used on the 4 pillars of SSL",
    ),
    ("SURFACE_CAMERA_ROTATE_RIGHT", "Camera Rotate Right", "Surface camera that rotates to the right (Bowser 1 & THI)"),
    ("SURFACE_CAMERA_ROTATE_LEFT", "Camera Rotate Left", "Surface camera that rotates to the left (BoB & TTM)"),
    ("SURFACE_CAMERA_BOUNDARY", "Camera Boundary", "Intangible Area, only used to restrict camera movement"),
    ("SURFACE_NOISE_VERY_SLIPPERY_73", "Noise Very Slippery 73", "Very slippery floor with noise, unused"),
    ("SURFACE_NOISE_VERY_SLIPPERY_74", "Noise Very Slippery 74", "Very slippery floor with noise, unused"),
    ("SURFACE_NOISE_VERY_SLIPPERY", "Noise Very Slippery", "Very slippery floor with noise, used in CCM"),
    ("SURFACE_NO_CAM_COLLISION", "No Cam Collision", "Surface with no cam collision flag"),
    ("SURFACE_NO_CAM_COLLISION_77", "No Cam Collision 77", "Surface with no cam collision flag, unused"),
    (
        "SURFACE_NO_CAM_COL_VERY_SLIPPERY",
        "No Cam Col Very Slippery",
        "Surface with no cam collision flag, very slippery with noise (THI)",
    ),
    (
        "SURFACE_NO_CAM_COL_SLIPPERY",
        "No Cam Col Slippery",
        "Surface with no cam collision flag, slippery with noise (CCM, PSS and TTM slides)",
    ),
    (
        "SURFACE_SWITCH",
        "Switch",
        "Surface with no cam collision flag, non-slippery with noise, used by switches and Dorrie",
    ),
    ("SURFACE_VANISH_CAP_WALLS", "Vanish Cap Walls", "Vanish cap walls, pass through them with Vanish Cap"),
    ("SURFACE_PAINTING_WOBBLE_A6", "Painting Wobble A6", "Painting wobble (BoB Left)"),
    ("SURFACE_PAINTING_WOBBLE_A7", "Painting Wobble A7", "Painting wobble (BoB Middle)"),
    ("SURFACE_PAINTING_WOBBLE_A8", "Painting Wobble A8", "Painting wobble (BoB Right)"),
    ("SURFACE_PAINTING_WOBBLE_A9", "Painting Wobble A9", "Painting wobble (CCM Left)"),
    ("SURFACE_PAINTING_WOBBLE_AA", "Painting Wobble AA", "Painting wobble (CCM Middle)"),
    ("SURFACE_PAINTING_WOBBLE_AB", "Painting Wobble AB", "Painting wobble (CCM Right)"),
    ("SURFACE_PAINTING_WOBBLE_AC", "Painting Wobble AC", "Painting wobble (WF Left)"),
    ("SURFACE_PAINTING_WOBBLE_AD", "Painting Wobble AD", "Painting wobble (WF Middle)"),
    ("SURFACE_PAINTING_WOBBLE_AE", "Painting Wobble AE", "Painting wobble (WF Right)"),
    ("SURFACE_PAINTING_WOBBLE_AF", "Painting Wobble AF", "Painting wobble (JRB Left)"),
    ("SURFACE_PAINTING_WOBBLE_B0", "Painting Wobble B0", "Painting wobble (JRB Middle)"),
    ("SURFACE_PAINTING_WOBBLE_B1", "Painting Wobble B1", "Painting wobble (JRB Right)"),
    ("SURFACE_PAINTING_WOBBLE_B2", "Painting Wobble B2", "Painting wobble (LLL Left)"),
    ("SURFACE_PAINTING_WOBBLE_B3", "Painting Wobble B3", "Painting wobble (LLL Middle)"),
    ("SURFACE_PAINTING_WOBBLE_B4", "Painting Wobble B4", "Painting wobble (LLL Right)"),
    ("SURFACE_PAINTING_WOBBLE_B5", "Painting Wobble B5", "Painting wobble (SSL Left)"),
    ("SURFACE_PAINTING_WOBBLE_B6", "Painting Wobble B6", "Painting wobble (SSL Middle)"),
    ("SURFACE_PAINTING_WOBBLE_B7", "Painting Wobble B7", "Painting wobble (SSL Right)"),
    ("SURFACE_PAINTING_WOBBLE_B8", "Painting Wobble B8", "Painting wobble (Unused - Left)"),
    ("SURFACE_PAINTING_WOBBLE_B9", "Painting Wobble B9", "Painting wobble (Unused - Middle)"),
    ("SURFACE_PAINTING_WOBBLE_BA", "Painting Wobble BA", "Painting wobble (Unused - Right)"),
    (
        "SURFACE_PAINTING_WOBBLE_BB",
        "Painting Wobble BB",
        "Painting wobble (DDD - Left), makes the painting wobble if touched",
    ),
    ("SURFACE_PAINTING_WOBBLE_BC", "Painting Wobble BC", "Painting wobble (Unused, DDD - Middle)"),
    ("SURFACE_PAINTING_WOBBLE_BD", "Painting Wobble BD", "Painting wobble (Unused, DDD - Right)"),
    ("SURFACE_PAINTING_WOBBLE_BE", "Painting Wobble BE", "Painting wobble (WDW Left)"),
    ("SURFACE_PAINTING_WOBBLE_BF", "Painting Wobble BF", "Painting wobble (WDW Middle)"),
    ("SURFACE_PAINTING_WOBBLE_C0", "Painting Wobble C0", "Painting wobble (WDW Right)"),
    ("SURFACE_PAINTING_WOBBLE_C1", "Painting Wobble C1", "Painting wobble (THI Tiny - Left)"),
    ("SURFACE_PAINTING_WOBBLE_C2", "Painting Wobble C2", "Painting wobble (THI Tiny - Middle)"),
    ("SURFACE_PAINTING_WOBBLE_C3", "Painting Wobble C3", "Painting wobble (THI Tiny - Right)"),
    ("SURFACE_PAINTING_WOBBLE_C4", "Painting Wobble C4", "Painting wobble (TTM Left)"),
    ("SURFACE_PAINTING_WOBBLE_C5", "Painting Wobble C5", "Painting wobble (TTM Middle)"),
    ("SURFACE_PAINTING_WOBBLE_C6", "Painting Wobble C6", "Painting wobble (TTM Right)"),
    ("SURFACE_PAINTING_WOBBLE_C7", "Painting Wobble C7", "Painting wobble (Unused, TTC - Left)"),
    ("SURFACE_PAINTING_WOBBLE_C8", "Painting Wobble C8", "Painting wobble (Unused, TTC - Middle)"),
    ("SURFACE_PAINTING_WOBBLE_C9", "Painting Wobble C9", "Painting wobble (Unused, TTC - Right)"),
    ("SURFACE_PAINTING_WOBBLE_CA", "Painting Wobble CA", "Painting wobble (Unused, SL - Left)"),
    ("SURFACE_PAINTING_WOBBLE_CB", "Painting Wobble CB", "Painting wobble (Unused, SL - Middle)"),
    ("SURFACE_PAINTING_WOBBLE_CC", "Painting Wobble CC", "Painting wobble (Unused, SL - Right)"),
    ("SURFACE_PAINTING_WOBBLE_CD", "Painting Wobble CD", "Painting wobble (THI Huge - Left)"),
    ("SURFACE_PAINTING_WOBBLE_CE", "Painting Wobble CE", "Painting wobble (THI Huge - Middle)"),
    ("SURFACE_PAINTING_WOBBLE_CF", "Painting Wobble CF", "Painting wobble (THI Huge - Right)"),
    (
        "SURFACE_PAINTING_WOBBLE_D0",
        "Painting Wobble D0",
        "Painting wobble (HMC & CotMC - Left), makes the painting wobble if touched",
    ),
    ("SURFACE_PAINTING_WOBBLE_D1", "Painting Wobble D1", "Painting wobble (Unused, HMC & CotMC - Middle)"),
    ("SURFACE_PAINTING_WOBBLE_D2", "Painting Wobble D2", "Painting wobble (Unused, HMC & CotMC - Right)"),
    ("SURFACE_PAINTING_WARP_D3", "Painting Warp D3", "Painting warp (BoB Left)"),
    ("SURFACE_PAINTING_WARP_D4", "Painting Warp D4", "Painting warp (BoB Middle)"),
    ("SURFACE_PAINTING_WARP_D5", "Painting Warp D5", "Painting warp (BoB Right)"),
    ("SURFACE_PAINTING_WARP_D6", "Painting Warp D6", "Painting warp (CCM Left)"),
    ("SURFACE_PAINTING_WARP_D7", "Painting Warp D7", "Painting warp (CCM Middle)"),
    ("SURFACE_PAINTING_WARP_D8", "Painting Warp D8", "Painting warp (CCM Right)"),
    ("SURFACE_PAINTING_WARP_D9", "Painting Warp D9", "Painting warp (WF Left)"),
    ("SURFACE_PAINTING_WARP_DA", "Painting Warp DA", "Painting warp (WF Middle)"),
    ("SURFACE_PAINTING_WARP_DB", "Painting Warp DB", "Painting warp (WF Right)"),
    ("SURFACE_PAINTING_WARP_DC", "Painting Warp DC", "Painting warp (JRB Left)"),
    ("SURFACE_PAINTING_WARP_DD", "Painting Warp DD", "Painting warp (JRB Middle)"),
    ("SURFACE_PAINTING_WARP_DE", "Painting Warp DE", "Painting warp (JRB Right)"),
    ("SURFACE_PAINTING_WARP_DF", "Painting Warp DF", "Painting warp (LLL Left)"),
    ("SURFACE_PAINTING_WARP_E0", "Painting Warp E0", "Painting warp (LLL Middle)"),
    ("SURFACE_PAINTING_WARP_E1", "Painting Warp E1", "Painting warp (LLL Right)"),
    ("SURFACE_PAINTING_WARP_E2", "Painting Warp E2", "Painting warp (SSL Left)"),
    ("SURFACE_PAINTING_WARP_E3", "Painting Warp E3", "Painting warp (SSL Medium)"),
    ("SURFACE_PAINTING_WARP_E4", "Painting Warp E4", "Painting warp (SSL Right)"),
    ("SURFACE_PAINTING_WARP_E5", "Painting Warp E5", "Painting warp (Unused - Left)"),
    ("SURFACE_PAINTING_WARP_E6", "Painting Warp E6", "Painting warp (Unused - Medium)"),
    ("SURFACE_PAINTING_WARP_E7", "Painting Warp E7", "Painting warp (Unused - Right)"),
    ("SURFACE_PAINTING_WARP_E8", "Painting Warp E8", "Painting warp (DDD - Left)"),
    ("SURFACE_PAINTING_WARP_E9", "Painting Warp E9", "Painting warp (DDD - Middle)"),
    ("SURFACE_PAINTING_WARP_EA", "Painting Warp EA", "Painting warp (DDD - Right)"),
    ("SURFACE_PAINTING_WARP_EB", "Painting Warp EB", "Painting warp (WDW Left)"),
    ("SURFACE_PAINTING_WARP_EC", "Painting Warp EC", "Painting warp (WDW Middle)"),
    ("SURFACE_PAINTING_WARP_ED", "Painting Warp ED", "Painting warp (WDW Right)"),
    ("SURFACE_PAINTING_WARP_EE", "Painting Warp EE", "Painting warp (THI Tiny - Left)"),
    ("SURFACE_PAINTING_WARP_EF", "Painting Warp EF", "Painting warp (THI Tiny - Middle)"),
    ("SURFACE_PAINTING_WARP_F0", "Painting Warp F0", "Painting warp (THI Tiny - Right)"),
    ("SURFACE_PAINTING_WARP_F1", "Painting Warp F1", "Painting warp (TTM Left)"),
    ("SURFACE_PAINTING_WARP_F2", "Painting Warp F2", "Painting warp (TTM Middle)"),
    ("SURFACE_PAINTING_WARP_F3", "Painting Warp F3", "Painting warp (TTM Right)"),
    ("SURFACE_TTC_PAINTING_1", "TTC Painting 1", "Painting warp (TTC Left)"),
    ("SURFACE_TTC_PAINTING_2", "TTC Painting 2", "Painting warp (TTC Medium)"),
    ("SURFACE_TTC_PAINTING_3", "TTC Painting 3", "Painting warp (TTC Right)"),
    ("SURFACE_PAINTING_WARP_F7", "Painting Warp F7", "Painting warp (SL Left)"),
    ("SURFACE_PAINTING_WARP_F8", "Painting Warp F8", "Painting warp (SL Middle)"),
    ("SURFACE_PAINTING_WARP_F9", "Painting Warp F9", "Painting warp (SL Right)"),
    ("SURFACE_PAINTING_WARP_FA", "Painting Warp FA", "Painting warp (THI Huge - Left)"),
    ("SURFACE_PAINTING_WARP_FB", "Painting Warp FB", "Painting warp (THI Huge - Middle)"),
    ("SURFACE_PAINTING_WARP_FC", "Painting Warp FC", "Painting warp (THI Huge - Right)"),
    ("SURFACE_WOBBLING_WARP", "Wobbling Warp", "Wobbling Warp"),
    ("SURFACE_TRAPDOOR", "Trapdoor", "Trapdoor"),
]

enumCollisionForceBased = ["COL_TYPE_WARP", "COL_TYPE_FORCE_INSTANT_WARP", "COL_TYPE_FORCE_AS_SPEED", "COL_TYPE_HORIZONTAL_WIND", "COL_TYPE_FLOWING_WATER", "MOVING_QUICKSAND"]

enumCollisionWarpsAndLevel = [
    ("COL_TYPE_LEVEL_DEFAULT", "Default", "COL_TYPE_LEVEL_DEFAULT"),
    ("CUSTOM", "Custom", "Custom"),
    ("", "Non-Force Based", ""),  # Non-Force based collumn
    ("INSTANT_WARP", "Instant Warps", "COL_TYPE_INSTANT_WARP_(N)"),
    ("COL_TYPE_LOOK_UP_WARP", "Look Up Warp", "COL_TYPE_LOOK_UP_WARP, warps to WARP_NODE_LOOK_UP (0xF2)"),
    ("COL_TYPE_TIMER_START", "Timer Start", "COL_TYPE_TIMER_START"),
    ("COL_TYPE_TIMER_END", "Timer End", "COL_TYPE_TIMER_END"),
    ("COL_TYPE_MUSIC", "Music (Merry Go Round)", "COL_TYPE_MUSIC"),
    ("", "Force Based", ""),  # Force based collumn
    ("COL_TYPE_WARP", "Warp", "COL_TYPE_WARP"),
    ("COL_TYPE_FORCE_INSTANT_WARP", "Instant Warp", "COL_TYPE_FORCE_INSTANT_WARP"),
]

enumCollisionSpecial = [
    ("COL_TYPE_SPECIAL_DEFAULT", "Default", "COL_TYPE_SPECIAL_DEFAULT"),
    ("CUSTOM", "Custom", "Custom"),
    ("", "Non-Force Based", ""),  # Non-Force based collumn
    ("COL_TYPE_HANGABLE", "Hangable", "COL_TYPE_HANGABLE"),
    ("COL_TYPE_INTANGIBLE", "Intangible", "COL_TYPE_INTANGIBLE"),
    ("COL_TYPE_DEATH_PLANE", "Death Plane", "COL_TYPE_DEATH_PLANE"),
    ("COL_TYPE_BURNING", "Burning", "COL_TYPE_BURNING"),
    ("COL_TYPE_WATER", "Water Top", "COL_TYPE_WATER"),
    ("COL_TYPE_WATER_BOTTOM", "Water Bottom", "COL_TYPE_WATER_BOTTOM"),
    ("COL_TYPE_SLOW", "Slow", "COL_TYPE_SLOW"),
    ("COL_TYPE_VERTICAL_WIND", "Vertical Wind", "COL_TYPE_VERTICAL_WIND"),
    ("QUICKSAND", "Quicksand", "Quicksand"),
    ("", "Force Based", ""),  # Force based collumn
    ("COL_TYPE_FORCE_AS_SPEED", "Force as Speed", "COL_TYPE_FORCE_AS_SPEED"),
    ("COL_TYPE_HORIZONTAL_WIND", "Horizontal Wind", "COL_TYPE_HORIZONTAL_WIND"),
    ("COL_TYPE_FLOWING_WATER", "Flowing Water", "COL_TYPE_FLOWING_WATER"),
    ("MOVING_QUICKSAND", "Moving Quicksand", "Moving Quicksand"),
]

enumQuicksandCollision = [
    ("NORMAL", "Normal", "COL_TYPE_QUICKSAND"),
    ("INSTANT", "Instant", "COL_TYPE_INSTANT_QUICKSAND"),
    ("SHALLOW", "Shallow", "COL_TYPE_SHALLOW_QUICKSAND"),
    ("DEEP", "Deep", "COL_TYPE_DEEP_QUICKSAND"),
]

enumCollisionSlipperiness = [
    ("SURFACE_CLASS_DEFAULT", "Default", "SURFACE_CLASS_DEFAULT"),
    ("CUSTOM", "Custom", "Custom"),
    ("", "", ""),
    ("SURFACE_CLASS_VERY_SLIPPERY", "Very Slippery", "SURFACE_CLASS_VERY_SLIPPERY"),
    ("SURFACE_CLASS_SLIPPERY", "Slippery", "SURFACE_CLASS_SLIPPERY"),
    ("SURFACE_CLASS_NOT_SLIPPERY", "Not Slippery", "SURFACE_CLASS_NOT_SLIPPERY"),
    ("SURFACE_CLASS_SUPER_SLIPPERY", "Super Slippery", "SURFACE_CLASS_SUPER_SLIPPERY"),
]

enumCollisionCamera = [
    ("COL_TYPE_CAMERA_DEFAULT", "Default", "COL_TYPE_CAMERA_DEFAULT"),
    ("CUSTOM", "Custom", "Custom"),
    ("", "", ""),
    ("COL_TYPE_CAMERA_WALL", "Wall", "COL_TYPE_CAMERA_WALL"),
    ("COL_TYPE_CLOSE_CAMERA", "Close", "COL_TYPE_CLOSE_CAMERA"),
    ("COL_TYPE_CAMERA_FREE_ROAM", "Free Roam", "COL_TYPE_CAMERA_FREE_ROAM"),
    ("COL_TYPE_BOSS_FIGHT_CAMERA", "Boss Fight", "COL_TYPE_BOSS_FIGHT_CAMERA"),
    ("COL_TYPE_CAMERA_8_DIR", "8 Direction", "COL_TYPE_CAMERA_8_DIR"),
    ("COL_TYPE_CAMERA_MIDDLE", "Middle", "COL_TYPE_CAMERA_MIDDLE"),
    ("COL_TYPE_CAMERA_ROTATE_RIGHT", "Rotate Right", "COL_TYPE_CAMERA_ROTATE_RIGHT"),
    ("COL_TYPE_CAMERA_ROTATE_LEFT", "Rotate Left", "COL_TYPE_CAMERA_ROTATE_LEFT"),
    ("COL_TYPE_CAMERA_BOUNDARY", "Boundary", "COL_TYPE_CAMERA_BOUNDARY"),
]

enumCollisionParticle = [
    ("COL_TYPE_PARTICLE_DEFAULT", "Default", "COL_TYPE_PARTICLE_DEFAULT"),
    ("CUSTOM", "Custom", "Custom"),
    ("", "", ""),
    ("COL_TYPE_PARTICLE_SPARKLES", "Sparkles", "COL_TYPE_PARTICLE_SPARKLES"),
    ("COL_TYPE_PARTICLE_DUST", "Dust", "COL_TYPE_PARTICLE_DUST"),
    ("COL_TYPE_PARTICLE_WATER_SPLASH", "Water Splash", "COL_TYPE_PARTICLE_WATER_SPLASH"),
    ("COL_TYPE_PARTICLE_WAVE_TRAIL", "Wave Trail", "COL_TYPE_PARTICLE_WAVE_TRAIL"),
    ("COL_TYPE_PARTICLE_FIRE", "Fire", "COL_TYPE_PARTICLE_FIRE"),
    ("COL_TYPE_PARTICLE_SHALLOW_WATER", "Shallow Water", "COL_TYPE_PARTICLE_SHALLOW_WATER"),
    ("COL_TYPE_PARTICLE_LEAF", "Leaf", "COL_TYPE_PARTICLE_LEAF"),
    ("COL_TYPE_PARTICLE_SNOW", "Snow", "COL_TYPE_PARTICLE_SNOW"),
    ("COL_TYPE_PARTICLE_BREATH", "Breath", "COL_TYPE_PARTICLE_BREATH"),
    ("COL_TYPE_PARTICLE_DIRT", "Dirt", "COL_TYPE_PARTICLE_DIRT"),
    ("COL_TYPE_PARTICLE_TRIANGLE", "Triangle", "COL_TYPE_PARTICLE_TRIANGLE"),
]

enumCollisionSound = [
    ("SOUND_TERRAIN_DEFAULT", "Default", "SOUND_TERRAIN_DEFAULT"),
    ("CUSTOM", "Custom", "Custom"),
    ("", "", ""),
    ("SOUND_TERRAIN_GRASS", "Grass", "SOUND_TERRAIN_GRASS"),
    ("SOUND_TERRAIN_WATER", "Water", "SOUND_TERRAIN_WATER"),
    ("SOUND_TERRAIN_STONE", "Stone", "SOUND_TERRAIN_STONE"),
    ("SOUND_TERRAIN_SPOOKY", "Spooky (Wood)", "SOUND_TERRAIN_SPOOKY"),
    ("SOUND_TERRAIN_SNOW", "Snow", "SOUND_TERRAIN_SNOW"),
    ("SOUND_TERRAIN_ICE", "Ice", "SOUND_TERRAIN_ICE"),
    ("SOUND_TERRAIN_SAND", "Sand", "SOUND_TERRAIN_SAND"),
]

sTerrainSounds = {
    "TERRAIN_GRASS": {
        "DEFAULT": "SOUND_TERRAIN_DEFAULT",
        "HARD": "SOUND_TERRAIN_STONE",
        "SLIPPERY": "SOUND_TERRAIN_GRASS",
        "VERY_SLIPPERY": "SOUND_TERRAIN_GRASS",
        "NOISY_DEFAULT": "SOUND_TERRAIN_GRASS",
        "NOISY_SLIPERRY": "SOUND_TERRAIN_DEFAULT",
    },
    "TERRAIN_STONE": {
        "DEFAULT": "SOUND_TERRAIN_STONE",
        "HARD": "SOUND_TERRAIN_STONE",
        "SLIPPERY": "SOUND_TERRAIN_STONE",
        "VERY_SLIPPERY": "SOUND_TERRAIN_STONE",
        "NOISY_DEFAULT": "SOUND_TERRAIN_GRASS",
        "NOISY_SLIPERRY": "SOUND_TERRAIN_GRASS",
    },
    "TERRAIN_SNOW": {
        "DEFAULT": "SOUND_TERRAIN_SNOW",
        "HARD": "SOUND_TERRAIN_ICE",
        "SLIPPERY": "SOUND_TERRAIN_SNOW",
        "VERY_SLIPPERY": "SOUND_TERRAIN_ICE",
        "NOISY_DEFAULT": "SOUND_TERRAIN_STONE",
        "NOISY_SLIPERRY": "SOUND_TERRAIN_STONE",
    },
    "TERRAIN_SAND": {
        "DEFAULT": "SOUND_TERRAIN_SAND",
        "HARD": "SOUND_TERRAIN_STONE",
        "SLIPPERY": "SOUND_TERRAIN_SAND",
        "VERY_SLIPPERY": "SOUND_TERRAIN_SAND",
        "NOISY_DEFAULT": "SOUND_TERRAIN_STONE",
        "NOISY_SLIPERRY": "SOUND_TERRAIN_STONE",
    },
    "TERRAIN_SPOOKY": {
        "DEFAULT": "SOUND_TERRAIN_SPOOKY",
        "HARD": "SOUND_TERRAIN_SPOOKY",
        "SLIPPERY": "SOUND_TERRAIN_SPOOKY",
        "VERY_SLIPPERY": "SOUND_TERRAIN_SPOOKY",
        "NOISY_DEFAULT": "SOUND_TERRAIN_STONE",
        "NOISY_SLIPERRY": "SOUND_TERRAIN_STONE",
    },
    "TERRAIN_WATER": {
        "DEFAULT": "SOUND_TERRAIN_DEFAULT",
        "HARD": "SOUND_TERRAIN_STONE",
        "SLIPPERY": "SOUND_TERRAIN_GRASS",
        "VERY_SLIPPERY": "SOUND_TERRAIN_ICE",
        "NOISY_DEFAULT": "SOUND_TERRAIN_STONE",
        "NOISY_SLIPERRY": "SOUND_TERRAIN_ICE",
    },
    "TERRAIN_SLIDE": {
        "DEFAULT": "SOUND_TERRAIN_STONE",
        "HARD": "SOUND_TERRAIN_STONE",
        "SLIPPERY": "SOUND_TERRAIN_STONE",
        "VERY_SLIPPERY": "SOUND_TERRAIN_STONE",
        "NOISY_DEFAULT": "SOUND_TERRAIN_ICE",
        "NOISY_SLIPERRY": "SOUND_TERRAIN_ICE",
    },
}


@dataclasses.dataclass
class NewCollisionTypePreset:
    non_decal_shadow: bool = False
    vanish: bool = False
    can_get_stuck: bool | None = None
    warps_and_level: str = "COL_TYPE_LEVEL_DEFAULT"
    special: str = "COL_TYPE_SPECIAL_DEFAULT"
    slipperiness: str | None = None
    no_camera_collision: bool = False
    camera: str = "COL_TYPE_CAMERA_DEFAULT"
    particle: str | None = None
    sound_type: str = "DEFAULT"  # Vanilla Info
    instant_warp_num: int = 0
    quicksand_type: str = "NORMAL"


vanillaSoundToParticle = {
    "SOUND_TERRAIN_SAND": "COL_TYPE_PARTICLE_DIRT",
    "SOUND_TERRAIN_SNOW": "COL_TYPE_PARTICLE_SNOW",
}

newCollisionPresets = {
    "SURFACE_BURNING": NewCollisionTypePreset(special="COL_TYPE_BURNING"),
    "SURFACE_HANGABLE": NewCollisionTypePreset(special="COL_TYPE_HANGABLE"),
    "SURFACE_DEATH_PLANE": NewCollisionTypePreset(special="COL_TYPE_DEATH_PLANE"),
    "SURFACE_INTANGIBLE": NewCollisionTypePreset(special="COL_TYPE_INTANGIBLE"),
    "SURFACE_MGR_MUSIC": NewCollisionTypePreset(warps_and_level="COL_TYPE_MUSIC"),
    "SURFACE_QUICKSAND": NewCollisionTypePreset(special="QUICKSAND"),
    "SURFACE_SHALLOW_QUICKSAND": NewCollisionTypePreset(special="QUICKSAND", quicksand_type="SHALLOW"),
    "SURFACE_DEEP_QUICKSAND": NewCollisionTypePreset(special="QUICKSAND", quicksand_type="DEEP"),
    "SURFACE_INSTANT_QUICKSAND": NewCollisionTypePreset(special="QUICKSAND", quicksand_type="INSTANT"),
    "SURFACE_MOVING_QUICKSAND": NewCollisionTypePreset(special="MOVING_QUICKSAND"),
    "SURFACE_DEEP_MOVING_QUICKSAND": NewCollisionTypePreset(special="MOVING_QUICKSAND", quicksand_type="DEEP"),
    "SURFACE_SHALLOW_MOVING_QUICKSAND": NewCollisionTypePreset(special="MOVING_QUICKSAND", quicksand_type="SHALLOW"),
    "SURFACE_INSTANT_MOVING_QUICKSAND": NewCollisionTypePreset(special="MOVING_QUICKSAND", quicksand_type="INSTANT"),
    "SURFACE_WALL_MISC": NewCollisionTypePreset(camera="COL_TYPE_CAMERA_WALL"),
    "SURFACE_HORIZONTAL_WIND": NewCollisionTypePreset(special="HORIZONTAL_WIND"),
    "SURFACE_VERTICAL_WIND": NewCollisionTypePreset(special="VERTICAL_WIND"),
    "SURFACE_TIMER_START": NewCollisionTypePreset(warps_and_level="TIMER_START"),
    "SURFACE_TIMER_END": NewCollisionTypePreset(warps_and_level="TIMER_END"),
    "SURFACE_ICE": NewCollisionTypePreset(
        slipperiness="SURFACE_CLASS_VERY_SLIPPERY", sound_type="SURFACE_CLASS_VERY_SLIPPERY", non_decal_shadow=True
    ),
    "SURFACE_SLOW": NewCollisionTypePreset(special="SLOW"),
    "SURFACE_SUPER_SLIPPERY": NewCollisionTypePreset(slipperiness="SURFACE_CLASS_SUPER_SLIPPERY", sound_type="VERY_SLIPPERY"),
    "SURFACE_VERY_SLIPPERY": NewCollisionTypePreset(slipperiness="SURFACE_CLASS_VERY_SLIPPERY", sound_type="VERY_SLIPPERY"),
    "SURFACE_SLIPPERY": NewCollisionTypePreset(slipperiness="SURFACE_CLASS_SLIPPERY", sound_type="SLIPPERY"),
    "SURFACE_NOT_SLIPPERY": NewCollisionTypePreset(slipperiness="SURFACE_CLASS_NOT_SLIPPERY", sound_type="HARD"),
    "SURFACE_NOISE_VERY_SLIPPERY": NewCollisionTypePreset(slipperiness="SURFACE_CLASS_VERY_SLIPPERY", sound_type="VERY_SLIPPERY"),
    "SURFACE_NOISE_VERY_SLIPPERY_73": NewCollisionTypePreset(slipperiness="SURFACE_CLASS_ERY_SLIPPERY", sound_type="VERY_SLIPPERY"),
    "SURFACE_NOISE_VERY_SLIPPERY_74": NewCollisionTypePreset(slipperiness="SURFACE_CLASS_VERY_SLIPPERY", sound_type="VERY_SLIPPERY"),
    "SURFACE_NOISE_SLIPPERY": NewCollisionTypePreset(slipperiness="SURFACE_CLASS_SLIPPERY", sound_type="NOISY_SLIPERRY"),
    "SURFACE_NOISE_DEFAULT": NewCollisionTypePreset(sound_type="NOISY_DEFAULT"),
    "SURFACE_HARD_VERY_SLIPPERY": NewCollisionTypePreset(
        slipperiness="SURFACE_CLASS_VERY_SLIPPERY", sound_type="VERY_SLIPPERY", can_get_stuck=False
    ),
    "SURFACE_HARD_SLIPPERY": NewCollisionTypePreset(
        slipperiness="SURFACE_CLASS_SLIPPERY", sound_type="SLIPPERY", can_get_stuck=False
    ),
    "SURFACE_HARD_NOT_SLIPPERY": NewCollisionTypePreset(
        slipperiness="SURFACE_CLASS_NOT_SLIPPERY", sound_type="HARD", can_get_stuck=False
    ),
    "SURFACE_HARD": NewCollisionTypePreset(sound_type="HARD", can_get_stuck=False),
    "SURFACE_CAMERA_FREE_ROAM": NewCollisionTypePreset(camera="COL_TYPE_CAMERA_FREE_ROAM"),
    "SURFACE_BOSS_FIGHT_CAMERA": NewCollisionTypePreset(camera="COL_TYPE_BOSS_FIGHT"),
    "SURFACE_CLOSE_CAMERA": NewCollisionTypePreset(camera="COL_TYPE_CLOSE_CAMERA"),
    "SURFACE_CAMERA_8_DIR": NewCollisionTypePreset(camera="COL_TYPE_CAMERA_8_DIR"),
    "SURFACE_CAMERA_MIDDLE": NewCollisionTypePreset(camera="COL_TYPE_CAMERA_MIDDLE"),
    "SURFACE_CAMERA_ROTATE_RIGHT": NewCollisionTypePreset(camera="COL_TYPE_CAMERA_ROTATE_RIGHT"),
    "SURFACE_CAMERA_ROTATE_LEFT": NewCollisionTypePreset(camera="COL_TYPE_CAMERA_ROTATE_LEFT"),
    "SURFACE_CAMERA_BOUNDARY": NewCollisionTypePreset(special="INTANGIBLE", camera="COL_TYPE_CAMERA_BOUNDARY"),
    "SURFACE_NO_CAM_COLLISION": NewCollisionTypePreset(no_camera_collision=True),
    "SURFACE_NO_CAM_COL_VERY_SLIPPERY": NewCollisionTypePreset(
        sound_type="VERY_SLIPPERY", slipperiness="SURFACE_CLASS_VERY_SLIPPERY", no_camera_collision=True
    ),
    "SURFACE_NO_CAM_COL_SLIPPERY": NewCollisionTypePreset(
        slipperiness="SURFACE_CLASS_SLIPPERY", sound_type="SLIPPERY", no_camera_collision=True
    ),
    "SURFACE_SWITCH": NewCollisionTypePreset(
        slipperiness="SURFACE_CLASS_NOT_SLIPPERY", sound_type="HARD", no_camera_collision=True
    ),
    "SURFACE_VANISH_CAP_WALLS": NewCollisionTypePreset(vanish=True),
    "SURFACE_WARP": NewCollisionTypePreset(warps_and_level="WARP"),
    "SURFACE_LOOK_UP_WARP": NewCollisionTypePreset(warps_and_level="LOOK_UP_WARP"),
    "SURFACE_INSTANT_WARP_1B": NewCollisionTypePreset(warps_and_level="INSTANT_WARP", instant_warp_num=0),
    "SURFACE_INSTANT_WARP_1C": NewCollisionTypePreset(warps_and_level="INSTANT_WARP", instant_warp_num=1),
    "SURFACE_INSTANT_WARP_1D": NewCollisionTypePreset(warps_and_level="INSTANT_WARP", instant_warp_num=2),
    "SURFACE_INSTANT_WARP_1E": NewCollisionTypePreset(warps_and_level="INSTANT_WARP", instant_warp_num=3),
}


class CollisionTypeDefinition(Enum):
    SURFACE_DEFAULT = 0x0000
    SURFACE_BURNING = 0x0001
    SURFACE_0004 = 0x0004
    SURFACE_HANGABLE = 0x0005
    SURFACE_SLOW = 0x0009
    SURFACE_DEATH_PLANE = 0x000A
    SURFACE_CLOSE_CAMERA = 0x000B
    SURFACE_WATER = 0x000D
    SURFACE_FLOWING_WATER = 0x000E
    SURFACE_INTANGIBLE = 0x0012
    SURFACE_VERY_SLIPPERY = 0x0013
    SURFACE_SLIPPERY = 0x0014
    SURFACE_NOT_SLIPPERY = 0x0015
    SURFACE_TTM_VINES = 0x0016
    SURFACE_MGR_MUSIC = 0x001A
    SURFACE_INSTANT_WARP_1B = 0x001B
    SURFACE_INSTANT_WARP_1C = 0x001C
    SURFACE_INSTANT_WARP_1D = 0x001D
    SURFACE_INSTANT_WARP_1E = 0x001E
    SURFACE_SHALLOW_QUICKSAND = 0x0021
    SURFACE_DEEP_QUICKSAND = 0x0022
    SURFACE_INSTANT_QUICKSAND = 0x0023
    SURFACE_DEEP_MOVING_QUICKSAND = 0x0024
    SURFACE_SHALLOW_MOVING_QUICKSAND = 0x0025
    SURFACE_QUICKSAND = 0x0026
    SURFACE_MOVING_QUICKSAND = 0x0027
    SURFACE_WALL_MISC = 0x0028
    SURFACE_NOISE_DEFAULT = 0x0029
    SURFACE_NOISE_SLIPPERY = 0x002A
    SURFACE_HORIZONTAL_WIND = 0x002C
    SURFACE_INSTANT_MOVING_QUICKSAND = 0x002D
    SURFACE_ICE = 0x002E
    SURFACE_LOOK_UP_WARP = 0x002F
    SURFACE_HARD = 0x0030
    SURFACE_WARP = 0x0032
    SURFACE_TIMER_START = 0x0033
    SURFACE_TIMER_END = 0x0034
    SURFACE_HARD_SLIPPERY = 0x0035
    SURFACE_HARD_VERY_SLIPPERY = 0x0036
    SURFACE_HARD_NOT_SLIPPERY = 0x0037
    SURFACE_VERTICAL_WIND = 0x0038
    SURFACE_BOSS_FIGHT_CAMERA = 0x0065
    SURFACE_CAMERA_FREE_ROAM = 0x0066
    SURFACE_THI3_WALLKICK = 0x0068
    SURFACE_CAMERA_PLATFORM = 0x0069
    SURFACE_CAMERA_MIDDLE = 0x006E
    SURFACE_CAMERA_ROTATE_RIGHT = 0x006F
    SURFACE_CAMERA_ROTATE_LEFT = 0x0070
    SURFACE_CAMERA_BOUNDARY = 0x0072
    SURFACE_NOISE_VERY_SLIPPERY_73 = 0x0073
    SURFACE_NOISE_VERY_SLIPPERY_74 = 0x0074
    SURFACE_NOISE_VERY_SLIPPERY = 0x0075
    SURFACE_NO_CAM_COLLISION = 0x0076
    SURFACE_NO_CAM_COLLISION_77 = 0x0077
    SURFACE_NO_CAM_COL_VERY_SLIPPERY = 0x0078
    SURFACE_NO_CAM_COL_SLIPPERY = 0x0079
    SURFACE_SWITCH = 0x007A
    SURFACE_VANISH_CAP_WALLS = 0x007B
    SURFACE_PAINTING_WOBBLE_A6 = 0x00A6
    SURFACE_PAINTING_WOBBLE_A7 = 0x00A7
    SURFACE_PAINTING_WOBBLE_A8 = 0x00A8
    SURFACE_PAINTING_WOBBLE_A9 = 0x00A9
    SURFACE_PAINTING_WOBBLE_AA = 0x00AA
    SURFACE_PAINTING_WOBBLE_AB = 0x00AB
    SURFACE_PAINTING_WOBBLE_AC = 0x00AC
    SURFACE_PAINTING_WOBBLE_AD = 0x00AD
    SURFACE_PAINTING_WOBBLE_AE = 0x00AE
    SURFACE_PAINTING_WOBBLE_AF = 0x00AF
    SURFACE_PAINTING_WOBBLE_B0 = 0x00B0
    SURFACE_PAINTING_WOBBLE_B1 = 0x00B1
    SURFACE_PAINTING_WOBBLE_B2 = 0x00B2
    SURFACE_PAINTING_WOBBLE_B3 = 0x00B3
    SURFACE_PAINTING_WOBBLE_B4 = 0x00B4
    SURFACE_PAINTING_WOBBLE_B5 = 0x00B5
    SURFACE_PAINTING_WOBBLE_B6 = 0x00B6
    SURFACE_PAINTING_WOBBLE_B7 = 0x00B7
    SURFACE_PAINTING_WOBBLE_B8 = 0x00B8
    SURFACE_PAINTING_WOBBLE_B9 = 0x00B9
    SURFACE_PAINTING_WOBBLE_BA = 0x00BA
    SURFACE_PAINTING_WOBBLE_BB = 0x00BB
    SURFACE_PAINTING_WOBBLE_BC = 0x00BC
    SURFACE_PAINTING_WOBBLE_BD = 0x00BD
    SURFACE_PAINTING_WOBBLE_BE = 0x00BE
    SURFACE_PAINTING_WOBBLE_BF = 0x00BF
    SURFACE_PAINTING_WOBBLE_C0 = 0x00C0
    SURFACE_PAINTING_WOBBLE_C1 = 0x00C1
    SURFACE_PAINTING_WOBBLE_C2 = 0x00C2
    SURFACE_PAINTING_WOBBLE_C3 = 0x00C3
    SURFACE_PAINTING_WOBBLE_C4 = 0x00C4
    SURFACE_PAINTING_WOBBLE_C5 = 0x00C5
    SURFACE_PAINTING_WOBBLE_C6 = 0x00C6
    SURFACE_PAINTING_WOBBLE_C7 = 0x00C7
    SURFACE_PAINTING_WOBBLE_C8 = 0x00C8
    SURFACE_PAINTING_WOBBLE_C9 = 0x00C9
    SURFACE_PAINTING_WOBBLE_CA = 0x00CA
    SURFACE_PAINTING_WOBBLE_CB = 0x00CB
    SURFACE_PAINTING_WOBBLE_CC = 0x00CC
    SURFACE_PAINTING_WOBBLE_CD = 0x00CD
    SURFACE_PAINTING_WOBBLE_CE = 0x00CE
    SURFACE_PAINTING_WOBBLE_CF = 0x00CF
    SURFACE_PAINTING_WOBBLE_D0 = 0x00D0
    SURFACE_PAINTING_WOBBLE_D1 = 0x00D1
    SURFACE_PAINTING_WOBBLE_D2 = 0x00D2
    SURFACE_PAINTING_WARP_D3 = 0x00D3
    SURFACE_PAINTING_WARP_D4 = 0x00D4
    SURFACE_PAINTING_WARP_D5 = 0x00D5
    SURFACE_PAINTING_WARP_D6 = 0x00D6
    SURFACE_PAINTING_WARP_D7 = 0x00D7
    SURFACE_PAINTING_WARP_D8 = 0x00D8
    SURFACE_PAINTING_WARP_D9 = 0x00D9
    SURFACE_PAINTING_WARP_DA = 0x00DA
    SURFACE_PAINTING_WARP_DB = 0x00DB
    SURFACE_PAINTING_WARP_DC = 0x00DC
    SURFACE_PAINTING_WARP_DD = 0x00DD
    SURFACE_PAINTING_WARP_DE = 0x00DE
    SURFACE_PAINTING_WARP_DF = 0x00DF
    SURFACE_PAINTING_WARP_E0 = 0x00E0
    SURFACE_PAINTING_WARP_E1 = 0x00E1
    SURFACE_PAINTING_WARP_E2 = 0x00E2
    SURFACE_PAINTING_WARP_E3 = 0x00E3
    SURFACE_PAINTING_WARP_E4 = 0x00E4
    SURFACE_PAINTING_WARP_E5 = 0x00E5
    SURFACE_PAINTING_WARP_E6 = 0x00E6
    SURFACE_PAINTING_WARP_E7 = 0x00E7
    SURFACE_PAINTING_WARP_E8 = 0x00E8
    SURFACE_PAINTING_WARP_E9 = 0x00E9
    SURFACE_PAINTING_WARP_EA = 0x00EA
    SURFACE_PAINTING_WARP_EB = 0x00EB
    SURFACE_PAINTING_WARP_EC = 0x00EC
    SURFACE_PAINTING_WARP_ED = 0x00ED
    SURFACE_PAINTING_WARP_EE = 0x00EE
    SURFACE_PAINTING_WARP_EF = 0x00EF
    SURFACE_PAINTING_WARP_F0 = 0x00F0
    SURFACE_PAINTING_WARP_F1 = 0x00F1
    SURFACE_PAINTING_WARP_F2 = 0x00F2
    SURFACE_PAINTING_WARP_F3 = 0x00F3
    SURFACE_TTC_PAINTING_1 = 0x00F4
    SURFACE_TTC_PAINTING_2 = 0x00F5
    SURFACE_TTC_PAINTING_3 = 0x00F6
    SURFACE_PAINTING_WARP_F7 = 0x00F7
    SURFACE_PAINTING_WARP_F8 = 0x00F8
    SURFACE_PAINTING_WARP_F9 = 0x00F9
    SURFACE_PAINTING_WARP_FA = 0x00FA
    SURFACE_PAINTING_WARP_FB = 0x00FB
    SURFACE_PAINTING_WARP_FC = 0x00FC
    SURFACE_WOBBLING_WARP = 0x00FD
    SURFACE_TRAPDOOR = 0x00FF
