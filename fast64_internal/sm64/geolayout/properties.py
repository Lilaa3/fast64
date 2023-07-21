import bpy, mathutils
from bpy.utils import register_class, unregister_class
from bpy.types import Object, Material, PropertyGroup
from bpy.props import (
    StringProperty,
    IntProperty,
    FloatProperty,
    BoolProperty,
    PointerProperty,
    CollectionProperty,
    EnumProperty,
    FloatVectorProperty,
)

from ...utility import PluginError, draw_text_with_wrapping, prop_split, copyPropToProp
from ...f3d.f3d_material import sm64EnumDrawLayers
from ..constants import MAX_S16, MIN_S16, level_enums, enumExportHeaderType, enumLevelNames
from ..utility import draw_error

from .operators import (
    SM64_DefineOptionOperations,
    SM64_ExportGeolayoutArmature,
    SM64_ExportGeolayoutObject,
    SM64_SwitchMaterialOperations,
    SM64_SwitchOptionOperations,
    drawLayerWarningBox,
    updateBone,
)
from .constants import (
    enumSwitchOptions,
    enumMatOverrideOptions,
    enumBoneType,
    enumDefineOptions,
    enumShadowType,
    animatableBoneTypes,
    linkedArmatureBoneTypes,
)


class MaterialPointerProperty(PropertyGroup):
    material: PointerProperty(type=Material)

    def copyMaterial(self, material: "MaterialPointerProperty"):
        copyPropToProp(material, self, [])

    def draw_props(self, layout: bpy.types.UILayout):
        col = layout.column()
        col.prop(self, "material", text="")
        if not self.material:
            col.box().label(text="Material not selected.", icon="ERROR")


class OptionProperty(PropertyGroup):
    switch_type: EnumProperty(name="Option Type", items=enumSwitchOptions)
    option_armature: PointerProperty(name="Option Armature", type=Object)
    material_override: PointerProperty(type=Material, name="Material Override")
    material_override_type: EnumProperty(name="Material Override Type", items=enumMatOverrideOptions)
    specific_override_array: CollectionProperty(type=MaterialPointerProperty, name="Specified Materials To Override")
    specific_ignore_array: CollectionProperty(type=MaterialPointerProperty, name="Specified Materials To Ignore")
    override_draw_layer: BoolProperty()
    draw_layer: EnumProperty(items=sm64EnumDrawLayers, name="Draw Layer")
    expandTab: BoolProperty(default=True)

    def copySwitchOption(self, switchOption: "OptionProperty"):
        copyPropToProp(switchOption, self, [])

    def get_mesh_obj(self):
        option_objs = []
        for child_obj in self.option_armature.children:
            if child_obj.type == "MESH":
                option_objs.append(child_obj)
        if len(option_objs) > 1:
            raise PluginError(
                f"Option armature has more than one mesh child."
            )
        elif len(option_objs) == 0:
            raise PluginError(
                f"Option armature has no mesh children."
            )
        return option_objs[0]

    def get_option_obj(self, armature):
        if self.option_armature is None:
            raise PluginError(f"Armature is None.")
        elif self.option_armature.type != "ARMATURE":
            raise PluginError(f"Object provided is not an armature.")
        elif len(self.option_armature.pose.bones) == 0:
            raise PluginError(f'Armature "{self.option_armature.name}" has no bones.')
        elif self.option_armature == armature:
            raise PluginError(f'Option´s armature "{self.option_armature.name}" is the same as this bone´s armature')

        option_obj = self.get_mesh_obj()
        return self.option_armature

    def drawMatArray(self, layout: bpy.types.UILayout, optionProps, arrayType, optionNum, isSpecific):
        col = layout.column()

        if isSpecific:
            array = optionProps.specific_override_array
        else:
            array = optionProps.specific_ignore_array

        if array:
            clearOp = col.operator(SM64_SwitchMaterialOperations.bl_idname, text="Clear Materials", icon="TRASH")
            clearOp.option, clearOp.type, clearOp.array = optionNum, "CLEAR", arrayType
        else:
            addOp = col.operator(SM64_SwitchMaterialOperations.bl_idname, text="Add Material", icon="ADD")
            addOp.option, addOp.isSpecific, addOp.type, addOp.array = optionNum, isSpecific, "ADD", arrayType

        for index, material in enumerate(array):
            if index != 0:
                col.separator(factor=1.0)

            opRow = col.row()
            addOp = opRow.operator(SM64_SwitchMaterialOperations.bl_idname, icon="ADD")
            addOp.option, addOp.index, addOp.isSpecific, addOp.type, addOp.array = (
                optionNum,
                index,
                isSpecific,
                "ADD",
                arrayType,
            )
            removeOp = opRow.operator(SM64_SwitchMaterialOperations.bl_idname, icon="REMOVE")
            removeOp.option, removeOp.index, removeOp.isSpecific, removeOp.type, removeOp.array = (
                optionNum,
                index,
                isSpecific,
                "REMOVE",
                arrayType,
            )
            moveUpCol = opRow.column()
            moveUpCol.enabled = index != 0
            moveUpOp = moveUpCol.operator(SM64_SwitchMaterialOperations.bl_idname, icon="TRIA_UP")
            moveUpOp.option, moveUpOp.index, moveUpOp.isSpecific, moveUpOp.type, moveUpOp.array = (
                optionNum,
                index,
                isSpecific,
                "MOVE_UP",
                arrayType,
            )
            moveDownCol = opRow.column()
            moveDownCol.enabled = index != len(array) - 1
            moveDownOp = moveDownCol.operator(SM64_SwitchMaterialOperations.bl_idname, icon="TRIA_DOWN")
            moveDownOp.option, moveDownOp.index, moveDownOp.isSpecific, moveDownOp.type, moveDownOp.array = (
                optionNum,
                index,
                isSpecific,
                "MOVE_DOWN",
                arrayType,
            )

            material.draw_props(opRow)

    def drawMaterialSwitch(self, layout: bpy.types.UILayout, optionProps, arrayType: str, index: int):
        col = layout.column()
        prop_split(col, self, "material_override", "Material")
        prop_split(col, self, "material_override_type", "Material Override Type")
        if self.material_override_type == "Specific":
            matArrayBox = col.box()
            matArrayBox.label(text="Specified Materials To Override")
            self.drawMatArray(matArrayBox, optionProps, arrayType, index, True)
        else:
            matArrayBox = col.box()
            matArrayBox.label(text="Specified Materials To Ignore")
            self.drawMatArray(matArrayBox, optionProps, arrayType, index, False)

        prop_split(col, self, "override_draw_layer", "Override Draw Layer")
        if self.override_draw_layer:
            prop_split(col, self, "draw_layer", "Draw Layer")

    def draw_props(
        self, layout: bpy.types.UILayout, context: bpy.types.Context, optionProps, arrayType: str, option: int
    ):
        col = layout.column()

        try:
            prop_split(col, self, "switch_type", "Type")
            if self.switch_type == "Material":
                self.drawMaterialSwitch(col, optionProps, arrayType, option)
            elif self.switch_type == "Draw Layer":
                prop_split(col, self, "draw_layer", "Draw Layer")
            elif self.switch_type == "Mesh":
                prop_split(col, self, "option_armature", "Option Armature")
                option_obj = self.get_option_obj(context.object)
        except Exception as e:
            draw_error(col, str(e))



class DefineOptionProperty(PropertyGroup):
    condition: EnumProperty(name="Condition", items=enumDefineOptions)
    arg: StringProperty(name="Argument", default="")
    option: PointerProperty(name="Option", type=OptionProperty)
    expandTab: BoolProperty(default=True)

    def copyDefineOption(self, defineOption: "DefineOptionProperty"):
        copyPropToProp(defineOption, self, [])

    def get_ifdefine(self):
        if self.arg == "":
            raise PluginError("Empty argument") 
        return f"#{self.condition} {self.arg}"

    def draw_props(self, layout: bpy.types.UILayout, context: bpy.types.Context, option: int):
        col = layout.column()

        prop_split(col, self, "condition", "Condition")
        prop_split(col, self, "arg", "Argument")
        try:
            ifdefine = self.get_ifdefine()
            col.box().label(text=ifdefine)
            self.option.draw_props(col, context, self.option, "Define", option)
        except Exception as e:
            draw_error(col, str(e))

def drawCollectionElementOps(layout: bpy.types.UILayout, opType, array, index):
    opRow = layout.row(align=True)

    removeOp = opRow.operator(opType.bl_idname, text="", icon="REMOVE")
    removeOp.option, removeOp.type = index, "REMOVE"

    addOp = opRow.operator(opType.bl_idname, text="", icon="ADD")
    addOp.option, addOp.type = index, "ADD"

    moveUpCol = opRow.column()
    moveUpCol.enabled = index != 0
    moveUpOp = moveUpCol.operator(opType.bl_idname, text="", icon="TRIA_UP")
    moveUpOp.option, moveUpOp.type = index, "MOVE_UP"

    moveDownCol = opRow.column()
    moveDownCol.enabled = index != len(array) - 1
    moveDownOp = moveDownCol.operator(opType.bl_idname, text="", icon="TRIA_DOWN")
    moveDownOp.option, moveDownOp.type = index, "MOVE_DOWN"


class SM64_CullingRadiusProperties(bpy.types.PropertyGroup):
    radius: FloatProperty(name="Culling Radius", default=10, min=0)
    auto: BoolProperty(name="Automatic radius", default=True)

    def get_auto_radius(self, obj: bpy.types.Object):
        culling_radius = 0.0
        bound_objs = [obj]
        if obj.type == "ARMATURE":
            bound_objs = obj.children
        for bound_obj in bound_objs:
            bbox_corners = [bound_obj.matrix_world @ mathutils.Vector(corner) for corner in bound_obj.bound_box]
            culling_radius = 0.0
            for vec in bbox_corners:
                for x in list(vec):
                    culling_radius = max(culling_radius, abs(x))
        return round(culling_radius, 3)

    def radius_in_game(self, obj: bpy.types.Object):
        if self.auto:
            culling_radius = self.get_auto_radius(obj)
        else:
            culling_radius = self.radius
        return int(culling_radius * bpy.context.scene.fast64.sm64.blender_to_sm64_scale)

    def draw_props(self, layout: bpy.types.UILayout, obj: bpy.types.Object):
        col = layout.column()

        col.box().prop(self, "auto")
        if not self.auto:
            prop_split(col, self, "radius", "Culling Radius")
        info = col.box().column()
        info.label(text=f"Recommended radius {self.get_auto_radius(obj)}")
        info.label(text=f"Radius is in blender units. ({self.radius_in_game(obj)})", icon="INFO")

    def get_node(self, obj: bpy.types.Object):
        from .sm64_geolayout_classes import StartRenderAreaNode
        return StartRenderAreaNode(self.radius_in_game(obj))


class SM64_ShadowProperties(PropertyGroup):
    type: EnumProperty(name="Shadow Type", items=enumShadowType, default="SHADOW_CIRCLE_4_VERTS")
    solidity: FloatProperty(name="Shadow Alpha", min=0, max=1, default=1)
    scale: FloatProperty(name="Shadow Scale", min=0, max=MAX_S16, default=0.01)

    def scale_in_game(self):
        return int(self.scale * bpy.context.scene.fast64.sm64.blender_to_sm64_scale)

    def get_node(self):
        from .sm64_geolayout_classes import ShadowNode
        return ShadowNode(self.type, self.solidity, self.scale_in_game())

    def draw_props(self, layout: bpy.types.UILayout):
        col = layout.column()
        prop_split(col, self, "type", "Type")

        row = col.row()
        prop_split(row, self, "solidity", "Alpha")
        prop_split(row, self, "scale", "Scale")

        col.label(text=f"Scale is in blender units. ({self.scale_in_game()})", icon="INFO")


class SM64_GeoASMProperties(bpy.types.PropertyGroup):
    func: bpy.props.StringProperty(
        name="Geo ASM Func", default="", description="Name of function for C, hex address for binary."
    )
    param: bpy.props.StringProperty(
        name="Geo ASM Param", default="0", description="Function parameter. (Binary exporting will cast to int)"
    )

    def draw_function(self, layout: bpy.types.UILayout):
        from ..sm64_function_map import func_map
        col = layout.column()
        prop_split(col, self, "func", "Function")
        refresh_func_map = func_map[bpy.context.scene.fast64.sm64.refresh_version]
        function = refresh_func_map.get(self.func.lower(), None)
        if function:
            col.box().label(text=function)

    def draw_props(self, layout: bpy.types.UILayout):
        col = layout.column()
        self.draw_function(col)
        prop_split(col, self, "param", "Parameter")

    def get_node(self, node: bpy.types.Bone | bpy.types.Object):
        from .sm64_geolayout_classes import FunctionNode
        if self.func == "":
            if isinstance(node, bpy.types.Object):
                raise PluginError(f'Object "{node.name}" has an empty function field.')
            raise PluginError(f'Function bone "{node.name}" has an empty function field.')
        return FunctionNode(self.func, self.param)


class SM64_CustomCmdProperties(bpy.types.PropertyGroup):
    macro: StringProperty(name="Macro", default="YOUR_CUSTOM_COMMAND")
    command_num: StringProperty(name="Command", default="0x1A")
    args: StringProperty(name="Arguments", default="YOUR, ARGUMENTS")
    parameter: StringProperty(name="Parameter", default="0x01")
    animatable: BoolProperty(name="Animatable")
    add_translation: BoolProperty(name="Add Translation")
    add_rotation: BoolProperty(name="Add Rotation")
    add_dl: BoolProperty(name="Uses Displaylist")

    def get_node(self, translate, rotate, draw_layer: int, external_dl):
        from .sm64_geolayout_classes import CustomNode

        if not self.macro:
            raise PluginError(f'Custom geo command´s macro is empty.')

        is_binary = bpy.context.scene.fast64.sm64.is_binary_export()
        return CustomNode(
            self.command_num if is_binary else self.macro,
            self.parameter if is_binary else self.args,
            self.animatable,
            draw_layer,
            translate if self.add_translation else None,
            rotate if self.add_rotation else None,
            self.add_dl,
            external_dl,
        )

    def draw_props(self, layout: bpy.types.UILayout, bone, sm64_props):
        col = layout.column()
        props = bone.fast64.sm64

        if sm64_props.is_binary_export():
            prop_split(col, self, "command_num", "Command")
            prop_split(col, self, "parameter", "Parameter")
        else:
            prop_split(col, self, "macro", "Macro")
            prop_split(col, self, "args", "Arguments")
        try:
            if bone.parent is not None:
                transforms = (bone.parent.matrix_local.inverted() @ bone.matrix_local).decompose()
            else:
                matrix = bone.matrix_local.decompose()
            translate = transforms[0]
            rotate = transforms[1]
            node = self.get_node(translate, rotate, props.draw_layer, props.external_dl if props.use_external_dL else None)

            col.prop(self, "animatable")
            col.prop(self, "add_translation")
            col.prop(self, "add_rotation")
            col.prop(self, "add_dl")

            box = col.box().column()
            if self.add_translation or self.add_rotation:
                box.label(text="Transformation values may be innacurate")

            if sm64_props.is_binary_export():
                node_preview = f"0x{node.to_binary(None).hex().upper()}"
            else:
                node_preview = node.to_c()

            draw_text_with_wrapping(col.box().column(), node_preview)
        except Exception as e:
            draw_text_with_wrapping(col.box().column(), str(e))


class SM64_BoneProperties(PropertyGroup):
    version: IntProperty(name="SM64_BoneProperties Version", default=0)
    cur_version: IntProperty(default=1)

    geo_cmd: EnumProperty(
        name="Geolayout Command", items=enumBoneType, default="DisplayListWithOffset", update=updateBone
    )

    draw_layer: EnumProperty(name="Draw Layer", items=sm64EnumDrawLayers, default="1")

    custom_cmd: PointerProperty(type=SM64_CustomCmdProperties)
    # Scale
    scale: FloatProperty(name="Scale", min=0, max=1, default=1)
    # Function, HeldObject, Switch
    # 8027795C for HeldObject
    function: PointerProperty(type=SM64_GeoASMProperties)
    # Shadow
    shadow: PointerProperty(type=SM64_ShadowProperties)
    # StartRenderArea
    culling: PointerProperty(type=SM64_CullingRadiusProperties)
    # Switch
    manual_paramter: BoolProperty(name="Manual Parameter")
    switch_options: CollectionProperty(type=OptionProperty)
    # DefineOptions
    define_variants: CollectionProperty(type=DefineOptionProperty)
    # Display list commands
    use_external_dL: BoolProperty(name="Reference Displaylist", default=False)
    external_dl: StringProperty(name="External Displaylist", default="NULL")

    def upgrade_version_0(self, armature_obj, bone):
        from .constants import enumBoneTypeOLD

        old_cmd = bone.get("geo_cmd", None)
        if old_cmd is not None:
            new_cmd = enumBoneTypeOLD[old_cmd]
        else:
            new_cmd = self.geo_cmd

        if new_cmd == "CustomNonAnimated" or new_cmd == "CustomNonAnimated":
            custom: SM64_CustomCmdProperties = self.custom_cmd
            if new_cmd == "CustomAnimated":
                custom.animatable = True
                custom.add_translation = True
                custom.add_dl = True
            new_cmd = "Custom"

        if new_cmd == "TranslateRotate":
            field_layout = bone.get("field_layout", 0)
            if field_layout == "1":
                new_cmd = "Translate"
            elif field_layout == "2":
                new_cmd = "Rotate"
            print(f"Upgraded from old translate rotate layout")
        elif new_cmd == "REMOVE":
            print(f"Removable deprecated bone type. Removing bone.")
            name = bone.name  # Store here to prevent blender from shitting itself
            if bpy.context.mode != "EDIT":
                bpy.ops.object.mode_set(mode="EDIT")
                print(f"Changed context to edit mode.")
            print(f"Removable deprecated bone type. Removing bone.")
            for edit_bone in armature_obj.data.edit_bones:
                if edit_bone.name == name:
                    armature_obj.data.edit_bones.remove(edit_bone)
                    break
            else:
                bpy.ops.object.mode_set(mode="OBJECT")
                raise PluginError("Could not find the bone.")
            bpy.ops.object.mode_set(mode="OBJECT")
            print(f"Changing back to object context mode.")
            return

        self.draw_layer = str(bone.get("draw_layer", self.draw_layer))
        self.scale = bone.get("geo_scale", self.scale)

        function_props: SM64_GeoASMProperties = self.function
        function_props.func = bone.get("geo_func", function_props.func)
        function_props.param = str(bone.get("func_param", function_props.param))

        armature_props = armature_obj.fast64.sm64
        if new_cmd == "Shadow":
            shadow_props: SM64_ShadowProperties = armature_props.shadow
            shadow_type = bone.get("shadow_type", None)
            if shadow_type is not None:
                shadow_props.type = enumShadowType[shadow_type][0]
            shadow_props.solidity = bone.get("shadow_solidity", shadow_props.solidity)
            scale = bone.get("shadow_scale")
            if scale is not None:
                shadow_props.scale = scale / bpy.context.scene.fast64.sm64.blender_to_sm64_scale
            
            armature_props.add_shadow = True
            new_cmd = "Start"
        elif new_cmd == "StartRenderArea":
            culling_radius = bone.get("culling_radius", None)
            if culling_radius:
                armature_props.culling.radius = culling_radius
                armature_props.culling.auto = False
            armature_props.set_culling_radius = True
            new_cmd = "Start"

        for old_option in bone.get("switch_options", []):
            self.switch_options.add()
            option: OptionProperty = self.switch_options[-1]

            switch_type = old_option.get("switchType")
            if switch_type:
                option.switch_type = enumSwitchOptions[switch_type][0]

            option_obj_props = old_option.get("optionArmature")
            if option_obj_props:
                option.option_armature = option_obj_props

            material_override_props = old_option.get("materialOverride")
            if material_override_props:
                option.material_override = material_override_props

            material_override_type = old_option.get("materialOverrideType")
            if material_override_type:
                option.material_override_type = enumMatOverrideOptions[material_override_type][0]

            for material_pointer in old_option.get("specificOverrideArray", []):
                option.specific_override_array.add()
                option.specific_override_array[-1].material = material_pointer.get("material")
            for material_pointer in old_option.get("specificIgnoreArray", []):
                option.specific_ignore_array.add()
                option.specific_ignore_array[-1].material = material_pointer.get("material")

            option.override_draw_layer = old_option.get("overrideDrawLayer", option.override_draw_layer)
            option.draw_layer = str(old_option.get("drawLayer", option.draw_layer))

        option_amount = len(self.switch_options) + 1
        if bone.get("func_param", option_amount) != option_amount:
            self.manual_paramter = True

        self.geo_cmd = new_cmd
        print(f"Command type updated. From index {old_cmd} to {self.geo_cmd}")


    @staticmethod
    def upgrade_changed_props(obj):
        if obj.type != "ARMATURE":
            return

        if bpy.context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj

        print(f"Setting context mode to OBJECT")
        bpy.ops.object.mode_set(mode="OBJECT")

        bone_names = [bone.name for bone in obj.data.bones]
        for bone_name in bone_names:
            try:
                if bone_name in obj.data.bones:
                    bone = obj.data.bones[bone_name]
                else:
                    raise PluginError("Bone does not exist.")
                bone_props = bone.fast64.sm64

                if bone_props.version == 0:
                    print(f"Upgrading bone {bone_name} from version 0")
                    bone_props.upgrade_version_0(obj, bone)

                if bone_props.version != bone_props.cur_version:
                    bone_props.version = bone_props.cur_version
                    print("Bone upgrade was sucessfull!")
            except Exception as e:
                print(f"Failed to upgrade version 0 bone: {str(e)}")

    def is_animatable(self) -> bool:
        return self.geo_cmd in animatableBoneTypes or (
            self.geo_cmd == "Custom" and self.custom_cmd.animatable
        )

    def get_needed_armatures(self, bone, armature_obj):
        linked_armatures = set()
        if self.geo_cmd not in linkedArmatureBoneTypes:
            return linked_armatures
        for switchOption in self.switch_options:
            if switchOption.switch_type != "Mesh":
                continue
            elif switchOption.option_armature is None:
                raise PluginError(
                    f'\
"{bone.name}" in armature "{armature_obj.name}" has a mesh switch option with no defined mesh.'
                )

            armature_option_obj = switchOption.option_armature
            linked_armatures.add(armature_option_obj)
            for option_bone in armature_option_obj.data.bones:
                bone_props: "SM64_BoneProperties" = option_bone.fast64.sm64
                linked_armatures.update(bone_props.get_needed_armatures(option_bone, armature_option_obj))
        return linked_armatures

    def drawTranslateRotate(self, layout: bpy.types.UILayout, infoBox: bpy.types.UILayout = None):
        col = layout.column()

        isTranslation = self.geo_cmd == "Translate"
        isRotation = self.geo_cmd == "Rotate"
        if self.geo_cmd == "TranslateRotate":
            isTranslation, isRotation = True, True

        fieldInfo = "This command will use this bone´s "
        if isTranslation and isRotation:
            fieldInfo += "translation and rotation."
        elif isTranslation:
            fieldInfo += "translation."
        elif isRotation:
            fieldInfo += "rotation."

        if not infoBox:
            infoBox = col.box().column()
        draw_text_with_wrapping(infoBox, fieldInfo)

    def draw_define_option(self, layout: bpy.types.UILayout, context: bpy.types.Context, option, index):
        col = layout.column()

        opRow = col.row(align=True)
        drawCollectionElementOps(opRow, SM64_DefineOptionOperations, self.switch_options, index)
        opRow.prop(
            option,
            "expandTab",
            text=f"Define Option {index + 1}",
            icon="TRIA_DOWN" if option.expandTab else "TRIA_RIGHT",
        )

        if option.expandTab:
            option.draw_props(col, context, index)

    def drawDefine(self, layout: bpy.types.UILayout, context: bpy.types.Context, infoBox: bpy.types.UILayout = None):
        col = layout.column()

        if not infoBox:
            infoBox = col.box().column()

        draw_text_with_wrapping(infoBox, "If all other defines are false this child´s bone will be used as the variation.")

        if self.define_variants:
            col.operator(SM64_DefineOptionOperations.bl_idname, text="Clear Options", icon="TRASH").type = "CLEAR"

        addOp = col.operator(SM64_DefineOptionOperations.bl_idname, text="Add Option", icon="ADD")
        addOp.option, addOp.type = len(self.define_variants), "ADD"

        for index, option in enumerate(self.define_variants):
            self.draw_define_option(col.box(), context, option, index)

    def draw_switch_option(self, layout: bpy.types.UILayout, context: bpy.types.Context, switchOption, index):
        box = layout.box()

        opRow = box.row(align=True)
        drawCollectionElementOps(opRow, SM64_SwitchOptionOperations, self.switch_options, index)
        opRow.prop(
            switchOption,
            "expandTab",
            text=f"Switch Option {index + 1}",
            icon="TRIA_DOWN" if switchOption.expandTab else "TRIA_RIGHT",
        )

        if switchOption.expandTab:
            switchOption.draw_props(box, context, switchOption, "Switch", index)

    def draw_switch(self, layout: bpy.types.UILayout, context: bpy.types.Context, infoBox: bpy.types.UILayout = None):
        col = layout.column()

        if not infoBox:
            infoBox = col.box().column()
        infoBox.label(text="Switch Option 0 is always this bone's children.")
        
        self.function.draw_function(col)

        col.prop(self, "manual_paramter")
        if self.manual_paramter:
            prop_split(col, self.function, "param", "Parameter")

        if self.switch_options:
            col.box().label(text=f"{len(self.switch_options) + 1} Options")
            col.operator(SM64_SwitchOptionOperations.bl_idname, text="Clear Options", icon="TRASH").type = "CLEAR"

        addOp = col.operator(SM64_SwitchOptionOperations.bl_idname, text="Add Option", icon="ADD")
        addOp.option, addOp.type = len(self.switch_options), "ADD"

        for index, option in enumerate(self.switch_options):
            self.draw_switch_option(col, context, option, index)

    def draw_props(self, layout: bpy.types.UILayout, context: bpy.types.Context):
        col = layout.column()
        prop_split(col, self, "geo_cmd", "Geolayout Command")

        infoBox = col.box().column()
        if self.geo_cmd == "AnimatedPart":
            infoBox.label(text="Animated bones use armature layer 0.")
        else:
            infoBox.label(text="This bone command uses armature layer 1.")

        if self.geo_cmd == "Scale":
            prop_split(layout, self, "scale", "Scale")
        elif self.geo_cmd == "HeldObject":
            prop_split(layout, self.function, "func", "Function")
        elif self.geo_cmd == "DefineVariants":
            self.drawDefine(col, context, infoBox)
        elif self.geo_cmd == "Switch":
            self.draw_switch(col, context, infoBox)
        elif self.geo_cmd == "Function":
            self.function.draw_props(col)
            col.box().label(text="This affects the next sibling bone in " + "alphabetical order.")
        elif self.geo_cmd in ["TranslateRotate", "Translate", "Rotate"]:
            self.drawTranslateRotate(col, infoBox)
        elif self.geo_cmd == "Custom":
            self.custom_cmd.draw_props(col, context.bone, context.scene.fast64.sm64)

        if self.geo_cmd in [
            "TranslateRotate",
            "Translate",
            "Rotate",
            "Billboard",
            "DisplayList",
            "Scale",
            "DisplayListWithOffset",
            "CustomAnimated",
        ] or self.custom_cmd.add_dl:
            col.prop(self, "use_external_dL")
            if self.use_external_dL:
                prop_split(col, self, "external_dl", "External Display List")
            drawLayerWarningBox(col, self, "draw_layer")


class SM64_ExportGeolayoutProps(PropertyGroup):
    insertableBinaryPath: StringProperty(name="Filepath", subtype="FILE_PATH")

    overwrite_model_load: BoolProperty(name="Modify level script", default=True)
    modelLoadLevelScriptCmd: StringProperty(name="Level script model load command", default="2ABCE0")
    modelID: StringProperty(name="Model ID", default="1")

    dump_as_text: BoolProperty(name="Dump as text", default=False)
    text_dump_path: StringProperty(name="Text Dump Path", subtype="FILE_PATH")
    ram_address: StringProperty(name="RAM Address", default="80000000")
    texture_dir: StringProperty(name="Include Path", default="actors/mario/")
    separate_texture_def: BoolProperty(name="Save texture.inc.c separately")

    replace_old_dls: BoolProperty(name="Replace old DL references in other actors", default=True)

    modify_old_geos: BoolProperty(name="Rename old geolayout to avoid conflicts", default=True)
    name: StringProperty(name="Geolayout Name", default="mario_geo")

    def drawBinary(self, layout: bpy.types.UILayout, scene: bpy.types.Scene):
        sm64Props = scene.fast64.sm64
        col = layout.column()

        if sm64Props.export.use_bank0:
            prop_split(col, self, "ram_address", "RAM Address")
        col.prop(self, "overwrite_model_load")
        if self.overwrite_model_load:
            prop_split(col, self, "modelLoadLevelScriptCmd", "Model Load Command")
            prop_split(col, self, "modelID", "Model ID")
        col.prop(self, "dump_as_text")
        if self.dump_as_text:
            col.prop(self, "text_dump_path")

    def drawC(self, layout: bpy.types.UILayout, scene: bpy.types.Scene):
        sm64Props = scene.fast64.sm64
        col = layout.column()

        if scene.saveTextures:
            if sm64Props.export.header_type == "Custom":
                prop_split(col, self, "texture_dir", "Texture Include Path")
            col.prop(self, "separate_texture_def")

        prop_split(col, self, "name", "Geolayout Name")

        if sm64Props.export.header_type != "Custom":
            if sm64Props.export.header_type == "Actor" and sm64Props.export.name in [
                "star",
                "transparent_star",
                "marios_cap",
            ]:
                col.prop(self, "replace_old_dls")

            infoBox = col.box().column()
            infoBox.label(text="If a geolayout file contains multiple actors,")
            infoBox.label(text="all other actors must also be replaced to prevent compilation errors.")

    def draw_props(self, layout: bpy.types.UILayout, scene: bpy.types.Scene):
        sm64Props = scene.fast64.sm64

        col = layout.column()
        col.operator(SM64_ExportGeolayoutArmature.bl_idname)
        col.operator(SM64_ExportGeolayoutObject.bl_idname)

        if sm64Props.export_type in ["C", "glTF"]:
            # TODO: Add seperate code for gltf
            self.drawC(col, scene)
        elif sm64Props.export_type == "Binary":
            self.drawBinary(col, scene)


properties = (
    MaterialPointerProperty,
    OptionProperty,
    DefineOptionProperty,
    SM64_CullingRadiusProperties,
    SM64_ShadowProperties,
    SM64_GeoASMProperties,
    SM64_CustomCmdProperties,
    SM64_BoneProperties,
    SM64_ExportGeolayoutProps,
)


def propertiesRegister():
    for cls in properties:
        register_class(cls)


def propertiesUnregister():
    for cls in reversed(properties):
        unregister_class(cls)
