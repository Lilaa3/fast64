sm64_extension_name = "EXT_sm64"

import bpy
import os
import bpy, mathutils, math

from ..gltf_utility import TypeToGlTF, appendGlTF2Extension, blenderColorToGlTFColor
from .utility import getExportDir
from ..utility import (
    PluginError,
    checkIdentityRotation,
    findTupleInBlenderEnum,
    toAlnum,
)

from .utility import checkExpanded, apply_basic_tweaks
from .geolayout.sm64_geolayout_classes import drawLayerNames
from .geolayout.constants import enumBoneType
from .sm64_objects import WarpNodeProperty, backgroundSegments
from .constants import levelIDNames

geoCommandsToGlTF = {
    "Start": TypeToGlTF("START"),
    "StartRenderArea": TypeToGlTF("CULL", {"radius": "culling_radius"}),
    "Shadow": TypeToGlTF(
        "DRAW_SHADOW", {"type": "shadow_type", "solidity": "shadow_solidity", "scale": "shadow_scale"}
    ),
    "Scale": TypeToGlTF("SCALE", {"scale": "geo_scale"}),
    "TranslateRotate": TypeToGlTF("TRANSLATE_ROTATE"),
    "Translate": TypeToGlTF("TRANSLATE"),
    "Rotate": TypeToGlTF("ROTATE"),
    "Billboard": TypeToGlTF("BILLBOARD"),
    "DisplayList": TypeToGlTF("DISPLAY_LIST"),  # This probably should be a warning in the future
    "DisplayListWithOffset": TypeToGlTF("ANIMATE"),
    "Switch": TypeToGlTF("SWITCH"),
    "Function": TypeToGlTF("FUNCTION"),
    "HeldObject": TypeToGlTF("HELD_OBJECT"),
    "SwitchOption": TypeToGlTF("SWITCH_OPTION"),
    "Ignore": TypeToGlTF("IGNORE"),
}


def nonCustomGeoCommandToGlTF(bone, command, hasDisplayList):
    info: TypeToGlTF = geoCommandsToGlTF[command]
    blenderCommandName = findTupleInBlenderEnum(enumBoneType, command)[1]

    defaultMessageStart = (
        f'Bone named "{bone.name}" uses the command ({blenderCommandName}) which is normally used in a'
    )

    if command in ["DisplayList"] and len(bone.children) > 0:
        message = f"{defaultMessageStart} childless bone."
        raise Exception(message)

    if command in ["Function"] and not hasDisplayList:
        message = f"{defaultMessageStart} deformable bone."
        raise Exception(message)

    if command in ["Function", "Switch"]:
        return {
            "function": bone.geo_func,
            "parameter": bone.func_param,
        }
    elif command == "HeldObject":
        return {"function": bone.geo_func}

    commandname = info.commandInGlTF
    arguments = {}

    for attr in info.argumentAttrsToGlTF:
        arguments[attr] = getattr(bone, info.argumentAttrsToGlTF[attr])

    return {"command": commandname, "arguments": arguments}


def geoCommandToGlTF(bone):
    command = bone.geo_cmd
    hasDisplayList = bone.use_deform

    if command in geoCommandsToGlTF:
        geoCommandData = nonCustomGeoCommandToGlTF(bone, command, hasDisplayList)
    else:
        commandname = bone.fast64.sm64.custom_geo_cmd_macro
        arguments = bone.fast64.sm64.custom_geo_cmd_args

        geoCommandData = {"customCommand": commandname, "arguments": arguments}

    if hasDisplayList:
        geoCommandData["hasDisplayList"] = hasDisplayList

    return geoCommandData


def texTileScrollToGlTF(tileScroll):
    s, t, interval = tileScroll.s, tileScroll.t, tileScroll.interval

    if s != 0 or t != 0:
        return {"s": s, "t": t, "interval": interval}


def tileScrollToGlTF(f3dMat):
    tileScrollData = {}
    tex0, tex1 = texTileScrollToGlTF(f3dMat.tex0.tile_scroll), texTileScrollToGlTF(f3dMat.tex0.tile_scroll)

    if tex0:
        tileScrollData["tex0"] = tex0
    if tex1:
        tileScrollData["tex1"] = tex1

    return tileScrollData


def uvAxisScrollToGlTF(axis):
    if axis.animType == "None":
        return

    axisScrollData = {}
    axisScrollData["type"] = axis.animType
    if axis.animType == "Linear":
        axisScrollData["speed"] = axis.speed
    elif axis.animType == "Sine":
        axisScrollData["amplitude"] = axis.amplitude
        axisScrollData["frequency"] = axis.frequency
        axisScrollData["offset"] = axis.offset
    elif axis.animType == "Noise":
        axisScrollData["noiseAmplitude"] = axis.noiseAmplitude

    return axisScrollData


def uvScrollToGlTF(f3dMat):
    UVanim0 = f3dMat.UVanim0

    xCombined = UVanim0.x.animType == "Rotation"
    yCombined = UVanim0.y.animType == "Rotation"

    if xCombined or yCombined:
        return {"rotation": {"pivot": UVanim0.pivot, "angularSpeed": UVanim0.angularSpeed}}
    else:
        uvScrollData = {}
        u, v = uvAxisScrollToGlTF(UVanim0.x), uvAxisScrollToGlTF(UVanim0.y)

        if u or v:
            uvScrollData["u"] = u
            uvScrollData["v"] = v

            return uvScrollData


def drawLayerToGlTF(f3dMat):
    drawLayer = f3dMat.draw_layer.sm64
    if drawLayer != "1":
        if drawLayer in drawLayerNames:
            return drawLayerNames[drawLayer]
        else:
            return str(drawLayer)


def collisionToGlTF(blenderMaterial, extension):
    if extension.actorExport:
        return

    collision_data = {}

    if blenderMaterial.collision_all_options:
        colType = blenderMaterial.collision_type
    else:
        colType = blenderMaterial.collision_type_simple

    if colType == "Custom":
        collision_data["type"] = blenderMaterial.collision_custom
    elif colType != "SURFACE_DEFAULT":
        collision_data["type"] = colType

    if blenderMaterial.use_collision_param:
        collision_data["paramater"] = blenderMaterial.collision_param

    return collision_data


def objectFunctionToGlTF(obj: bpy.types.Object):
    if obj.add_func:
        func = obj.fast64.sm64.geo_asm
        return {
            "function": func.func,
            "parameter": func.param,
        }


def objectShadowToGlTF(obj: bpy.types.Object):
    if obj.add_shadow:
        return {
            "type": obj.shadow_type,
            "solidity": obj.shadow_solidity,
            "scale": obj.shadow_scale,
        }


puppyCamFlagAttrsToGlTF = [
    "NC_FLAG_XTURN",
    "NC_FLAG_YTURN",
    "NC_FLAG_ZOOM",
    "NC_FLAG_8D",
    "NC_FLAG_4D",
    "NC_FLAG_2D",
    "NC_FLAG_FOCUSX",
    "NC_FLAG_FOCUSY",
    "NC_FLAG_FOCUSZ",
    "NC_FLAG_POSX",
    "NC_FLAG_POSY",
    "NC_FLAG_POSZ",
    "NC_FLAG_COLLISION",
    "NC_FLAG_SLIDECORRECT",
]


def puppyCamVolumeToGlTF(obj):
    checkIdentityRotation(obj, obj.matrix_basis.to_quaternion(), False)
    puppyCam = obj.puppycamProp

    specialData = {"function": puppyCam.puppycamVolumeFunction, "permaSwap": puppyCam.puppycamVolumePermaswap}

    if puppyCam.puppycamUseFlags:
        flags = []
        for flagAttr in puppyCamFlagAttrsToGlTF:
            flags.append(getattr(puppyCam, flagAttr))
        specialData["flags"] = flags
    else:
        specialData["mode"] = puppyCam.puppycamMode if puppyCam.puppycamMode != "Custom" else puppyCam.puppycamType

    pos, camFocus = (32767, 32767, 32767), (32767, 32767, 32767)

    if puppyCam.puppycamUseEmptiesForPos:
        if puppyCam.puppycamCamPos != "":
            posObject = bpy.context.scene.objects[puppyCam.puppycamCamPos]
            pos = posObject.location
        if puppyCam.puppycamCamFocus != "":
            focObject = bpy.context.scene.objects[puppyCam.puppycamCamFocus]
            camFocus = focObject.location
    else:
        camera = puppyCam.puppycamCamera
        if camera is not None:
            pos = camera.location
            camFocus = (camera.matrix_local @ mathutils.Vector((0, 0, -1)))[:]

    specialData["pos"] = list(pos)
    specialData["camFocus"] = list(camFocus)

    return specialData


waterBoxTypeToGlTFDict = {"Water": "WATER", "Toxic Haze": "TOXIC_HAZE"}


def waterBoxToGlTF(obj: bpy.types.Object):
    checkIdentityRotation(obj, obj.matrix_basis.to_quaternion(), False)
    return {"boxType": waterBoxTypeToGlTFDict[obj.waterBoxType]}


def behaviorToGlTF(obj: bpy.types.Object, alwaysHasBParm: bool = False):
    if obj.sm64_obj_set_bparam or alwaysHasBParm:
        return obj.fast64.sm64.game_object.get_behavior_params()


def specialToGlTF(obj: bpy.types.Object):
    specialData = {}

    specialData["preset"] = obj.sm64_special_enum if obj.sm64_special_enum != "Custom" else obj.sm64_obj_preset
    specialData["setYaw"] = obj.sm64_obj_set_yaw
    if obj.sm64_obj_set_yaw:
        specialData["params"] = behaviorToGlTF(obj)

    return specialData


def macroToGlTF(obj: bpy.types.Object):
    macrotData = {}

    macrotData["macro"] = obj.sm64_macro_enum if obj.sm64_macro_enum != "Custom" else obj.sm64_obj_preset
    macrotData["params"] = behaviorToGlTF(obj)

    return macrotData


def gameObjectToGlTF(obj: bpy.types.Object):
    objectData = {}

    objectData["model"] = obj.sm64_model_enum if obj.sm64_model_enum != "Custom" else obj.sm64_obj_model

    objectData["behaviour"] = obj.sm64_behaviour_enum if obj.sm64_behaviour_enum != "Custom" else obj.sm64_obj_behaviour
    objectData["params"] = behaviorToGlTF(obj, True)

    excludedFromActs = []
    for i in range(1, 7, 1):
        isInAct = getattr(obj, f"sm64_obj_use_act{i}")
        if not isInAct:
            excludedFromActs.append(i)
    objectData["excludedFromActs"] = excludedFromActs

    return objectData


warpTypeToGlTFDict = {
    "Warp": "WARP",
    "Painting": "PAINTING",
    "Instant": "INSTANT",
}


def areaObjectToGlTF(obj: bpy.types.Object):
    def warpNodeToGlTF(warpNode: WarpNodeProperty):
        warpData = {}
        warpData["warpType"] = warpTypeToGlTFDict[warpNode.warpType]
        warpData["warpID"] = warpNode.warpID

        warpData["area"] = warpNode.destArea

        if warpNode.warpType == "Instant":
            if warpNode.useOffsetObjects:
                offset = warpNode.calc_offsets_from_objects(warpNode.uses_area_nodes())
            else:
                offset = warpNode.instantOffset
                offset = [offset[0], offset[1], offset[2]]

            warpData["instantOffset"] = list(offset)
            return warpData

        # Not instant warp
        warpData["level"] = (
            levelIDNames[warpNode.destLevelEnum] if warpNode.destLevelEnum != "custom" else warpNode.destLevel
        )
        warpData["node"] = warpNode.destNode
        warpData["flags"] = warpNode.warpFlagEnum if warpNode.warpFlagEnum != "Custom" else warpNode.warpFlags

        return warpData

    def areaScreenRectToGlTF(obj: bpy.types.Object):
        if obj.useDefaultScreenRect:
            return
        return {
            "pos": list(obj.screenPos),
            "size": list(obj.screenSize),
        }

    def areaBackgroundToGlTF(obj: bpy.types.Object):
        if obj.fast64.sm64.area.disable_background:
            return {"disableBackground": True}
        elif obj.areaOverrideBG:
            return {"backgroundColor": blenderColorToGlTFColor(obj.areaBGColor)}
        return {}

    def areaMusicToGlTF(obj: bpy.types.Object):
        if obj.noMusic:
            return

        seq, customSeq = obj.musicSeqEnum, obj.music_seq

        return {
            "enum": customSeq if seq == "Custom" else seq,
            "preset": obj.music_preset,
        }

    areaData = {}
    areaData["areaIndex"] = obj.areaIndex

    areaData["music"] = areaMusicToGlTF(obj)

    areaData["terrain"] = obj.terrainEnum if obj.terrainEnum != "Custom" else obj.terrain_type

    env, customEnv = obj.envOption, obj.envType
    areaData["envfx"] = customEnv if env == "Custom" else env

    camera, customCamera = obj.camOption, obj.camType
    areaData["cameraType"] = customCamera if camera == "Custom" else camera

    areaData["fog"] = {
        "color": blenderColorToGlTFColor(obj.area_fog_color),
        "range": list(obj.area_fog_position),
    }

    areaData["echoLevel"] = obj.echoLevel
    areaData["zoomOutOnPause"] = obj.zoomOutOnPause
    areaData.update(areaBackgroundToGlTF(obj))
    areaData["startDialog"] = obj.startDialog if obj.showStartDialog else None
    areaData["enableRooms"] = obj.enableRoomSwitch
    areaData["screenRect"] = areaScreenRectToGlTF(obj)

    warpNodesData = []
    for warpNode in obj.warpNodes:
        warpNodesData.append(warpNodeToGlTF(warpNode))
    areaData["warpNodes"] = warpNodesData

    return areaData


starGetCutsceneToGlTFDict = {
    "0": "LAKITU_FLIES_AWAY",
    "1": "ROTATE_AROUND_MARIO",
    "2": "CLOSEUP_OF_MARIO",
    "3": "BOWSER_KEYS",
    "4": "COIN_STAR",
}


def areaObjectChecks(areaDict, obj: bpy.types.Object):
    if len(obj.children) == 0:
        error = f"\
Area for {obj.name} has no children."
        raise PluginError(error)

    if obj.areaIndex in areaDict:
        error = f"\
{obj.name} shares the same area index as {areaDict[obj.areaIndex].name}"
        raise PluginError(error)

    areaDict[obj.areaIndex] = obj


def levelObjectToGlTF(obj: bpy.types.Object):
    def levelBackgroundToGlTF(obj: bpy.types.Object):
        if obj.useBackgroundColor:
            return {"backgroundColor": blenderColorToGlTFColor(obj.backgroundColor)}
        else:
            if obj.background == "CUSTOM":
                return {"skyboxSegment": obj.fast64.sm64.level.backgroundSegment}
            else:
                return {"skybox": obj.background}

    def starCutscenesToGlTF(obj: bpy.types.Object):
        starGetCutscenes = obj.starGetCutscenes
        starCutscenes = []
        isDefault = True
        for i in range(1, 8, 1):
            starOption = getattr(starGetCutscenes, f"star{i}_option")

            if starOption != "4":
                isDefault = False

            if starOption == "Custom":
                starValue = getattr(starGetCutscenes, f"star{i}_value")
            else:
                starValue = starGetCutsceneToGlTFDict[starOption]

            starCutscenes.append(starValue)
        if not isDefault:
            return starCutscenes

    def segmentToGlTF(segementEnum, customSegment, customGroup):
        if segementEnum != "Do Not Write":
            if segementEnum == "Custom":
                return {"segment": customSegment, "group": customGroup}
            else:
                return {"segment": segementEnum}

    levelData = {}

    childAreas = [child for child in obj.children if child.data is None and child.sm64_obj_type == "Area Root"]
    if len(childAreas) == 0:
        raise PluginError("The level root has no child empties with the 'Area Root' object type.")

    areaDict = {}

    for area in childAreas:
        areaObjectChecks(areaDict, area)

    levelData.update(levelBackgroundToGlTF(obj))
    levelData["hasStarSelect"] = False if obj.actSelectorIgnore else None
    # TODO: Set as start level is not included, it should remain on the fast64 side.
    # This becomes a problem when exporting through the glTF export window.
    segmentLoads = obj.fast64.sm64.segment_loads
    levelData["segment5"] = segmentToGlTF(
        segmentLoads.seg5_enum, segmentLoads.seg5_load_custom, segmentLoads.seg5_group_custom
    )
    levelData["segment6"] = segmentToGlTF(
        segmentLoads.seg6_enum, segmentLoads.seg6_load_custom, segmentLoads.seg6_group_custom
    )

    levelData["acousticReach"] = obj.acousticReach if obj.acousticReach == 20000 else None
    levelData["starCutscenes"] = starCutscenesToGlTF(obj)

    return levelData


emptyTypesToGlTFDict = {
    "Level Root": TypeToGlTF("LEVEL_ROOT", levelObjectToGlTF),
    "Area Root": TypeToGlTF("AREA_ROOT", areaObjectToGlTF),
    "Object": TypeToGlTF("OBJECT", gameObjectToGlTF),
    "Macro": TypeToGlTF("MACRO", macroToGlTF),
    "Special": TypeToGlTF("SPECIAL", specialToGlTF),
    "Mario Start": TypeToGlTF("MARIO_START", {"area": "sm64_obj_mario_start_area"}),
    "Whirlpool": TypeToGlTF(
        "WHIRLPOOL", {"index": "whirpool_index", "condition": "whirpool_condition", "strength": "whirpool_strength"}
    ),
    "Water Box": TypeToGlTF("WATER_BOX", waterBoxToGlTF),
    "Camera Volume": TypeToGlTF("CAMERA_VOLUME", {"function": "cameraVolumeFunction", "global": "cameraVolumeGlobal"}),
    "Switch": TypeToGlTF("SWITCH_NODE", {"function": "switchFunc", "parameter": "switchParam"}),
    "Puppycam Volume": TypeToGlTF("PUPPYCAM_VOLUME", puppyCamVolumeToGlTF),
}


def emptyToGlTF(extension, obj: bpy.types.Object):
    objectData = {}
    if obj.sm64_obj_type == "None":
        return objectData

    toGlTFInfo = emptyTypesToGlTFDict[obj.sm64_obj_type]
    objectData["type"] = toGlTFInfo.typeName

    objectData.update(toGlTFInfo.toGltf(obj))

    return objectData


def gather_asset_hook_sm64(extension, gltf2_asset, export_settings):
    if not extension.sm64:
        return

    extension.level = None
    extension.actorExport = export_settings["gltf_export_id"] == "fast64_sm64_geolayout_export"


def gather_gltf_extensions_hook_sm64(extension, gltf2_plan, export_settings):
    if not extension.sm64:
        return

    scene = bpy.context.scene

    extensionData = {}

    extensionData["scale"] = scene.fast64.sm64.blender_to_sm64_scale

    if scene.fast64.sm64.disable_scroll:
        extensionData["scroll"] = not scene.fast64.sm64.disable_scroll

    appendGlTF2Extension(extension, sm64_extension_name, gltf2_plan, extensionData)


def gather_node_hook_sm64(extension, gltf2Node, obj, exportSettings):
    if not extension.sm64:
        return

    extensionData = {}

    if obj.type == "EMPTY":
        extensionData.update(emptyToGlTF(extension, obj))

    appendGlTF2Extension(extension, sm64_extension_name, gltf2Node, extensionData)


def gather_mesh_hook_sm64(extension, gltf2_mesh, blenderMesh, obj, vertexGroups, modifiers, materials, exportSettings):
    if not extension.sm64 or obj is None:
        return

    extensionData = {}

    if obj.use_render_area:
        extensionData["cullingRadius"] = obj.culling_radius

    if obj.use_render_range:
        extensionData["renderRange"] = obj.render_range

    extensionData["shadow"] = objectShadowToGlTF(obj)
    extensionData["function"] = objectFunctionToGlTF(obj)

    if obj.ignore_render:
        extensionData["render"] = obj.ignore_render

    if obj.ignore_collision:
        extensionData["useCollision"] = obj.ignore_collision

    if obj.use_f3d_culling:
        extensionData["useCulling"] = obj.use_f3d_culling

    appendGlTF2Extension(extension, sm64_extension_name, gltf2_mesh, extensionData)


def gather_skin_hook_sm64(extension, gltf2_skin, obj, exportSettings):
    if not extension.sm64:
        return

    extensionData = {}

    if obj.use_render_area:
        extensionData["cullingRadius"] = obj.culling_radius

    appendGlTF2Extension(extension, sm64_extension_name, gltf2_skin, extensionData)


def gather_joint_hook_sm64(extension, gltf2Node, blender_bone, exportSettings):
    if not extension.sm64:
        return

    if gltf2Node.extensions is None:
        gltf2Node.extensions = {}

    gltf2Node.extensions[sm64_extension_name] = extension.Extension(
        name=sm64_extension_name,
        extension={"geoLayoutCommand": geoCommandToGlTF(blender_bone.bone)},
        required=False,
    )


def gather_scene_hook_sm64(extension, gltf2_scene, blender_scene, exportSettings):
    if not extension.sm64:
        return


def gather_material_hook_sm64(extension, gltf2_material, blenderMaterial, exportSettings):
    if not extension.sm64:
        return

    extensionData = {}

    extensionData["collision"] = collisionToGlTF(blenderMaterial, extension)

    if blenderMaterial.is_f3d:
        f3dMat = blenderMaterial.f3d_mat

        extensionData["drawLayer"] = drawLayerToGlTF(f3dMat)

        if f3dMat.set_fog:
            fogInfo = {}
            if f3dMat.use_global_fog:
                fogInfo["setAccordingToArea"] = True
            extensionData["fog"] = fogInfo

        extensionData["uvScroll"] = uvScrollToGlTF(f3dMat)
        extensionData["tileScroll"] = tileScrollToGlTF(f3dMat)

    appendGlTF2Extension(extension, sm64_extension_name, gltf2_material, extensionData)


def exportSm64GlTFGeolayout():
    scene: bpy.types.Scene = bpy.context.scene
    exportPath, levelName = getPathAndLevel(
        scene.geoCustomExport,
        scene.geoExportPath,
        scene.geoLevelName,
        scene.geoLevelOption,
    )

    saveTextures = scene.saveTextures
    if not scene.geoCustomExport:
        apply_basic_tweaks(exportPath)

    dirPath, texDir = getExportDir(
        scene.geoCustomExport,
        exportPath,
        scene.geoExportHeaderType,
        scene.geoLevelName,
        scene.geoTexDir,
        scene.geoName,
    )

    dirName = toAlnum(scene.geoName)
    groupName = toAlnum(scene.geoGroupName)
    geoDirPath = os.path.join(dirPath, toAlnum(dirName))

    glTFProps: Fast64_glTFProperties = scene.fast64.settings.glTF

    bpy.ops.export_scene.gltf(
        filepath=f"{geoDirPath}/{scene.geoName}",
        gltf_export_id="fast64_sm64_geolayout_export",
        export_format=glTFProps.exportFormat,
        ui_tab="GENERAL",
        export_copyright=glTFProps.copyright,
        export_image_format="AUTO",
        export_texture_dir="textures",
        export_jpeg_quality=100,
        export_texcoords=True,
        export_normals=True,
        use_visible=(not scene.exportHiddenGeometry),
        use_selection=True,
        export_draco_mesh_compression_enable=glTFProps.useMeshCompression,
        export_draco_mesh_compression_level=glTFProps.meshCompressionLevel,
        export_tangents=True,  # TODO: Are tangents really needed?
        export_materials="EXPORT",
        export_original_specular=False,
        export_colors=True,
        export_attributes=True,
        use_mesh_edges=False,  # I do not think there is any pratical porpuse for this and the following
        use_mesh_vertices=False,
        export_cameras=False,
        use_renderable=False,
        use_active_collection_with_nested=False,  # ?
        use_active_collection=False,
        use_active_scene=True,
        export_yup=False,  # Fast64 already does this
        export_apply=True,  # Breaks shape keys but those are not supported anyways
        export_animations=False,  # This panel will be used to export specifically geolayouts, there will be a panel to export an entire actor´s data with glTF.
        export_frame_range=False,
        export_frame_step=1,  # I think one should be correct.
        export_animation_mode="ACTIONS",  # A lot of users don´t use the NLA tracks, this is another concern with glTF tbh.
        # export_nla_strips_merged_animation_name="",
        export_def_bones=True,
        export_optimize_animation_size=True,
        export_optimize_animation_keep_anim_armature=False,
        export_optimize_animation_keep_anim_object=False,
        export_negative_frame="CROP",  # Still need to think more about this one
        export_anim_slide_to_zero=False,
        export_bake_animation=False,
        export_anim_single_armature=True,  # Maybe set this to false?
        export_reset_pose_bones=True,
        export_current_frame=False,
        export_rest_position_armature=True,
        export_anim_scene_split_object=False,  # Probably a bad idea to set this to true
        export_skins=True,
        export_all_influences=False,  # This has not much porpuse, even for real skinning
        export_morph=False,
        export_morph_normal=False,
        export_morph_tangent=False,
        export_morph_animation=False,
        export_morph_reset_sk_data=False,
        export_lights=False,  # Maybe enable this for levels
        export_nla_strips=False,
        will_save_settings=False,
        # filter_glob="" # What
    )
