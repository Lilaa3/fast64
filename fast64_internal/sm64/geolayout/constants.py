from enum import Enum

geoNodeRotateOrder = "ZXY"

linkedArmatureBoneTypes = ["Switch", "DefineVariants"]

drawLayers = {"Unused": [0, 3], "Solid": 1, "Decal": 2, "AlphaTest": 4, "Blend": 5, "BlendBehind": 6}

nodeDeformCmdsBoneGroups = ["TranslateRotate", "Translate", "Rotate", "Billboard", "DisplayList", "Scale"]

class GeoNodeEnum(Enum):
    BRANCH_STORE = 0x00
    END = 0x01
    BRANCH = 0x02
    RETURN = 0x03
    NODE_OPEN = 0x04
    NODE_CLOSE = 0x05
    SET_RENDER_AREA = 0x08
    SET_ORTHO = 0x09
    SET_CAMERA_FRUSTRUM = 0x0A
    START = 0x0B
    SET_Z_BUF = 0x0C
    SET_RENDER_RANGE = 0x0D
    SWITCH = 0x0E
    CAMERA = 0x0F
    TRANSLATE_ROTATE = 0x10
    TRANSLATE = 0x11
    ROTATE = 0x12
    LOAD_DL_W_OFFSET = 0x13
    BILLBOARD = 0x14
    LOAD_DL = 0x15
    START_W_SHADOW = 0x16
    SETUP_OBJ_RENDER = 0x17
    CALL_ASM = 0x18
    SET_BG = 0x19
    HELD_OBJECT = 0x1C
    NOP = [0x1A, 0x1E, 0x1F]
    SCALE = 0x1D
    START_W_RENDERAREA = 0x20

nodeGroupCmds = [
    GeoNodeEnum.START,
    GeoNodeEnum.SWITCH,
    GeoNodeEnum.TRANSLATE_ROTATE,
    GeoNodeEnum.TRANSLATE,
    GeoNodeEnum.ROTATE,
    GeoNodeEnum.LOAD_DL_W_OFFSET,
    GeoNodeEnum.BILLBOARD,
    GeoNodeEnum.START_W_SHADOW,
    GeoNodeEnum.SCALE,
    GeoNodeEnum.START_W_RENDERAREA,
]

nodeDeformCmds = [
    GeoNodeEnum.TRANSLATE_ROTATE,
    GeoNodeEnum.TRANSLATE,
    GeoNodeEnum.ROTATE,
    GeoNodeEnum.LOAD_DL_W_OFFSET,
    GeoNodeEnum.BILLBOARD,
    GeoNodeEnum.LOAD_DL,
    GeoNodeEnum.SCALE,
]

nodeCmds = [
    GeoNodeEnum.NODE_OPEN,
    # GEO_START,
    # GEO_START_W_SHADOW,
    # GEO_START_W_RENDERAREA,
    GeoNodeEnum.LOAD_DL,
    GeoNodeEnum.LOAD_DL_W_OFFSET,
    GeoNodeEnum.BRANCH,
    # GEO_SWITCH,
    # GEO_SCALE,
    # GEO_TRANSLATE_ROTATE
]

geoCmdStatic = {
    0x04: [0x01, 0x03, 0x04, 0x05, 0x09, 0x0B, 0x0C, 0x17, 0x20],
    0x08: [0x00, 0x02, 0x0D, 0x0E, 0x12, 0x14, 0x15, 0x16, 0x18, 0x19],
    0x0C: [0x08, 0x13, 0x1C],
    0x14: [0x0F],
}

drawLayerNames = {
    0: "LAYER_FORCE",
    1: "LAYER_OPAQUE",
    2: "LAYER_OPAQUE_DECAL",
    3: "LAYER_OPAQUE_INTER",
    4: "LAYER_ALPHA",
    5: "LAYER_TRANSPARENT",
    6: "LAYER_TRANSPARENT_DECAL",
    7: "LAYER_TRANSPARENT_INTER",
}

enumBoneType = [
    ("DisplayListWithOffset", "Animated Part (0x13)", "Animated Part (Animatable Bone)"),
    ("TranslateRotate", "Translate Rotate (0x10)", "Translate Rotate"),
    ("Translate", "Translate (0x11)", "Translate"),
    ("Rotate", "Rotate (0x12)", "Rotate"),
    ("Billboard", "Billboard (0x14)", "Billboard"),
    ("DisplayList", "Display List (0x15)", "Display List"),
    ("Switch", "Switch (0x0E)", "Switch"),
    ("Function", "Function (0x18)", "Function"),
    ("HeldObject", "Held Object (0x1C)", "Held Object"),
    ("Scale", "Scale (0x1D)", "Scale"),
    ("Start", "Start (0x0B)", "Start"),
    ("Ignore", "Ignore", "Ignore bones when exporting"),
    ("Shadow", "Shadow (0x16)", "Shadow"),
    ("", "Decomp exclusive (C/glTF)", ""),
    ("Custom", "Custom Command", "Custom command, can select properties."),
    ("DefineVariants", "Define Variants", "Define Variants"),
    ("", "Depricated", ""),
]

animatableBoneTypes = {"DisplayListWithOffset"}

enumGeoStaticType = [
    ("Billboard", "Billboard (0x14)", "Billboard"),
    ("DisplayListWithOffset", "Animated Part (0x13)", "Animated Part (Animatable Bone)"),
    ("Optimal", "Optimal", "Optimal"),
]

enumShadowType = [
    ("SHADOW_CIRCLE_9_VERTS", "Circle Scalable (9 verts)", "Circle Scalable (9 verts)"),
    ("SHADOW_CIRCLE_4_VERTS", "Circle Scalable (4 verts)", "Circle Scalable (4 verts)"),
    ("SHADOW_CIRCLE_4_VERTS_FLAT_UNUSED", "Circle Permanent (4 verts)", "Circle Permanent (4 verts)"),
    ("SHADOW_SQUARE_PERMANENT", "Square Permanent", "Square Permanent"),
    ("SHADOW_SQUARE_SCALABLE", "Square Scalable", "Square Scalable"),
    ("SHADOW_SQUARE_TOGGLABLE", "Square Togglable", "Square Togglable"),
    ("SHADOW_RECTANGLE_HARDCODED_OFFSET", "Rectangle", "Rectangle"),
    ("SHADOW_CIRCLE_PLAYER", "Circle Player", "Circle Player"),
    ("Custom", "Custom", "Custom"),
]

enumDefineOptions = [
    ("ifdef", "If Define", "#ifdef"),
    ("ifndef", "If Not Define", "#ifndef"),
]

enumSwitchOptions = [
    ("Mesh", "Mesh Override", "Switch to a different mesh hierarchy."),
    (
        "Material",
        "Material Override",
        "Use the same mesh hierarchy, but override material on ALL meshes. Optionally override draw layer.",
    ),
    ("Draw Layer", "Draw Layer Override", "Override draw layer only."),
]

enumMatOverrideOptions = [
    ("All", "All", "Override every material with this one."),
    ("Specific", "Specific", "Only override instances of give material."),
]



# Old enums (used for upgrade logic)

enumBoneTypeOLD = [
    "Switch",
    "Start",
    "TranslateRotate",
    "Translate",
    "Rotate",
    "Billboard",
    "DisplayList",
    "Shadow",
    "Function",
    "HeldObject",
    "Scale",
    "StartRenderArea",
    "Ignore",
    "Start", # "SwitchOption",
    "DisplayListWithOffset",
    "CustomNonAnimated",
    "CustomAnimated",
]
