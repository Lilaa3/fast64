import bpy

from .utility import box_sm64_panel
from ..utility import prop_split
from ..utility_anim import ArmatureApplyWithMeshOperator


class SM64_Panel(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "SM64"
    bl_options = {"DEFAULT_CLOSED"}
    # goal refers to the selected sm64GoalTypeEnum, a different selection than this goal will filter this panel out
    goal = None
    # if this is True, the panel is hidden whenever the scene's export_type is not 'C'
    decomp_only = False
    isImport = False

    @classmethod
    def poll(cls, context):
        sm64Props = bpy.context.scene.fast64.sm64
        sceneGoal = sm64Props.goal
        isCurrentSceneGoal = sceneGoal == "All" or sceneGoal == cls.goal or not cls.goal

        if context.scene.gameEditorMode != "SM64":
            return False
        if cls.decomp_only and sm64Props.export_type != "C":
            return False

        if cls.isImport:
            if not isCurrentSceneGoal:
                return False
            # Only show if importing is enabled
            return sm64Props.show_importing_menus

        return isCurrentSceneGoal


class SM64_GeneralSettingsPanel(SM64_Panel):
    bl_idname = "SM64_PT_general_settings"
    bl_label = "General Settings"

    def draw(self, context):
        context.scene.fast64.sm64.draw_props(box_sm64_panel(self.layout))


class SM64_AddressConvertPanel(SM64_Panel):
    bl_idname = "SM64_PT_addr_conv"
    bl_label = "Address Converter"
    isImport = True

    def draw(self, context):
        from .operators import SM64_AddrConv
        from .properties import SM64_Properties

        col = box_sm64_panel(self.layout)
        sm64Props: SM64_Properties = context.scene.fast64.sm64

        segToVirtOp = col.operator(SM64_AddrConv.bl_idname, text="Convert Segmented To Virtual")
        segToVirtOp.segToVirt = True
        virtToSegOp = col.operator(SM64_AddrConv.bl_idname, text="Convert Virtual To Segmented")
        virtToSegOp.segToVirt = False
        prop_split(col, sm64Props, "convertible_addr", "Address")
        col.prop(sm64Props, "level_convert")

class SM64_ImportantPanel(SM64_Panel):
    bl_idname = "SM64_PT_important"
    bl_label = "Tools"

    def draw(self, context):
        from .operators import SM64_CreateSimpleLevel, SM64_AddWaterBox

        col = box_sm64_panel(self.layout)
        col.operator(SM64_CreateSimpleLevel.bl_idname)
        col.operator(SM64_AddWaterBox.bl_idname)

        from .operators import SM64_AddBoneGroups, SM64_CreateMetarig

        col = box_sm64_panel(self.layout)
        col.label(text="Armature Tools")
        col.operator(ArmatureApplyWithMeshOperator.bl_idname)
        col.operator(SM64_AddBoneGroups.bl_idname)
        col.operator(SM64_CreateMetarig.bl_idname)
