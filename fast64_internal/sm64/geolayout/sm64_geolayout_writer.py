from __future__ import annotations
from dataclasses import dataclass

import bpy, mathutils, math, copy, os, shutil, re

from ..sm64_gltf import exportSm64GlTFGeolayout
from bpy.utils import register_class, unregister_class
from io import BytesIO

from ..sm64_objects import InlineGeolayoutObjConfig, SM64_ObjectProperties, inlineGeoLayoutObjects
from ..sm64_camera import saveCameraSettingsToGeolayout
from ..sm64_f3d_writer import SM64Model, SM64GfxFormatter
from ..sm64_texscroll import modifyTexScrollFiles, modifyTexScrollHeadersGroup
from ..sm64_level_parser import parseLevelAtPointer
from ..sm64_rom_tweaks import ExtendBank0x04
from ...utility import (
    PluginError,
    VertexWeightError,
    setOrigin,
    raisePluginError,
    duplicateHierarchy,
    cleanupDuplicatedObjects,
    toAlnum,
    writeMaterialFiles,
    writeIfNotFound,
    get64bitAlignedAddr,
    encodeSegmentedAddr,
    writeMaterialHeaders,
    writeInsertableFile,
    bytesToHex,
    checkSM64EmptyUsesGeoLayout,
    convertEulerFloatToShort,
    convertFloatToShort,
    checkIsSM64InlineGeoLayout,
    checkIsSM64PreInlineGeoLayout,
    translate_blender_to_n64,
    rotate_quat_blender_to_n64,
    get_obj_temp_mesh,
    getGroupNameFromIndex,
    highlightWeightErrors,
    getGroupIndexFromname,
    getFMeshName,
    checkUniqueBoneNames,
)
from ..utility import getExportDir
from ...utility_anim import armatureApplyWithMesh, attemptModifierApply
from ...f3d.f3d_material import (
    isTexturePointSampled,
    isLightingDisabled,
)

from ...f3d.f3d_writer import (
    TriangleConverterInfo,
    LoopConvertInfo,
    BufferVertex,
    revertMatAndEndDraw,
    getInfoDict,
    saveStaticModel,
    getTexDimensions,
    checkForF3dMaterialInFaces,
    saveOrGetF3DMaterial,
    saveMeshWithLargeTexturesByFaces,
    saveMeshByFaces,
    getF3DVert,
    convertVertexData,
)

from ...f3d.f3d_gbi import (
    GfxList,
    GfxListTag,
    GfxMatWriteMethod,
    DPSetAlphaCompare,
    FModel,
    FMesh,
    SPVertex,
    DPSetEnvColor,
    FAreaData,
    FFogData,
    ScrollMethod,
    TextureExportSettings,
    DLFormat,
    SPEndDisplayList,
    SPDisplayList,
)

from .sm64_geolayout_classes import (
    DefineNode,
    DisplayListNode,
    TransformNode,
    StartNode,
    GeolayoutGraph,
    GeoLayoutBleed,
    JumpNode,
    SwitchOverrideNode,
    SwitchNode,
    TranslateNode,
    RotateNode,
    TranslateRotateNode,
    FunctionNode,
    CustomNode,
    BillboardNode,
    ScaleNode,
    RenderRangeNode,

    DisplayListWithOffsetNode,
    HeldObjectNode,
    Geolayout,
)

from ..constants import insertableBinaryTypes, bank0Segment, sm64BoneUp

from .utility import find_start_bones
from .constants import geoNodeRotateOrder
from .properties import SM64_BoneProperties

# TODO: Apply bone rotation before model conversion like oot


def replace_star_references(base_path):
    klepto_pattern = (
        "GEO\_SCALE\(0x00\, 16384\)\,\s*"
        + "GEO\_OPEN\_NODE\(\)\,\s*"
        + "GEO\_ASM\([^\)]*?\)\,\s*"
        + "GEO\_TRANSLATE\_ROTATE\_WITH\_DL\([^\)]*? star\_seg3.*?GEO\_CLOSE\_NODE\(\)\,"
    )

    unagi_pattern = (
        "GEO\_SCALE\(0x00\, 16384\)\,\s*"
        + "GEO\_OPEN\_NODE\(\)\,\s*"
        + "GEO\_TRANSLATE\_ROTATE\_WITH\_DL\([^\)]*? star\_seg3.*?GEO\_CLOSE\_NODE\(\)\,"
    )

    unagiReplacement = (
        "GEO_TRANSLATE_ROTATE(LAYER_OPAQUE, 500, 0, 0, 0, 0, 0),\n"
        + "\t" * 10
        + "GEO_OPEN_NODE(),\n"
        + "\t" * 10
        + "\tGEO_BRANCH_AND_LINK(star_geo),\n"
        + "\t" * 10
        + "GEO_CLOSE_NODE(),"
    )

    klepto_replacement = (
        "GEO_TRANSLATE_ROTATE(LAYER_OPAQUE, 75, 75, 0, 180, 270, 0),\n"
        + "\t" * 10
        + "GEO_OPEN_NODE(),\n"
        + "\t" * 10
        + "\tGEO_BRANCH_AND_LINK(star_geo),\n"
        + "\t" * 10
        + "GEO_CLOSE_NODE(),"
    )

    unagiPath = os.path.join(base_path, "actors/unagi/geo.inc.c")
    replace_dl_references_in_geo(unagiPath, unagi_pattern, unagiReplacement)

    kleptoPath = os.path.join(base_path, "actors/klepto/geo.inc.c")
    replace_dl_references_in_geo(kleptoPath, klepto_pattern, klepto_replacement)


def replace_transparent_star_references(base_path):
    pattern = (
        "GEO\_SCALE\(0x00\, 16384\)\,\s*"
        + "GEO\_OPEN\_NODE\(\)\,\s*"
        + "GEO\_ASM\([^\)]*?\)\,\s*"
        + "GEO\_TRANSLATE\_ROTATE\_WITH\_DL\([^\)]*? transparent_star\_seg3.*?GEO\_CLOSE\_NODE\(\)\,"
    )

    klepto_replacement = (
        "GEO_TRANSLATE_ROTATE(LAYER_OPAQUE, 75, 75, 0, 180, 270, 0),\n"
        + "\t" * 10
        + "GEO_OPEN_NODE(),\n"
        + "\t" * 10
        + "\tGEO_BRANCH_AND_LINK(transparent_star_geo),\n"
        + "\t" * 10
        + "GEO_CLOSE_NODE(),"
    )

    kleptoPath = os.path.join(base_path, "actors/klepto/geo.inc.c")
    replace_dl_references_in_geo(kleptoPath, pattern, klepto_replacement)


def replace_cap_references(base_path):
    pattern = "GEO\_TRANSLATE\_ROTATE\_WITH\_DL\([^\)]*?mario\_cap\_seg3.*?\)\,"
    klepto_pattern = (
        "GEO\_SCALE\(0x00\, 16384\)\,\s*"
        + "GEO\_OPEN\_NODE\(\)\,\s*"
        + "GEO\_ASM\([^\)]*?\)\,\s*"
        + "GEO\_TRANSLATE\_ROTATE\_WITH\_DL\([^\)]*? mario\_cap\_seg3.*?GEO\_CLOSE\_NODE\(\)\,"
    )

    klepto_replacement = (
        "GEO_TRANSLATE_ROTATE(LAYER_OPAQUE, 75, 75, 0, 180, 270, 0),\n"
        + "\t" * 10
        + "GEO_OPEN_NODE(),\n"
        + "\t" * 10
        + "\tGEO_BRANCH_AND_LINK(marios_cap_geo),\n"
        + "\t" * 10
        + "GEO_CLOSE_NODE(),"
    )

    ukiki_replacement = (
        "GEO_TRANSLATE_ROTATE(LAYER_OPAQUE, 100, 0, 0, -90, -90, 0),\n"
        + "\t" * 8
        + "GEO_OPEN_NODE(),\n"
        + "\t" * 8
        + "GEO_SCALE(0x00, 0x40000),\n"
        + "\t" * 8
        + "\tGEO_OPEN_NODE(),\n"
        + "\t" * 8
        + "\t\tGEO_BRANCH_AND_LINK(marios_cap_geo),\n"
        + "\t" * 8
        + "\tGEO_CLOSE_NODE(),"
        + "\t" * 8
        + "GEO_CLOSE_NODE(),"
    )

    snowman_replacement = (
        "GEO_TRANSLATE_ROTATE(LAYER_OPAQUE, 490, 14, 43, 305, 0, 248),\n"
        + "\t" * 7
        + "GEO_OPEN_NODE(),\n"
        + "\t" * 7
        + "GEO_SCALE(0x00, 0x40000),\n"
        + "\t" * 7
        + "\tGEO_OPEN_NODE(),\n"
        + "\t" * 7
        + "\t\tGEO_BRANCH_AND_LINK(marios_cap_geo),\n"
        + "\t" * 7
        + "\tGEO_CLOSE_NODE(),"
        + "\t" * 7
        + "GEO_CLOSE_NODE(),"
    )

    ukikiPath = os.path.join(base_path, "actors/ukiki/geo.inc.c")
    replace_dl_references_in_geo(ukikiPath, pattern, ukiki_replacement)

    snowmanPath = os.path.join(base_path, "actors/snowman/geo.inc.c")
    replace_dl_references_in_geo(snowmanPath, pattern, snowman_replacement)

    kleptoPath = os.path.join(base_path, "actors/klepto/geo.inc.c")
    replace_dl_references_in_geo(kleptoPath, klepto_pattern, klepto_replacement)


def replace_dl_references_in_geo(geo_path, pattern, replacement):
    if not os.path.exists(geo_path):
        return
    geo_file = open(geo_path, "r", newline="\n")
    geo_data = geo_file.read()
    geo_file.close()

    new_data = re.sub(pattern, replacement, geo_data, flags=re.DOTALL)
    if new_data != geo_data:
        geo_file = open(geo_path, "w", newline="\n")
        geo_file.write(new_data)
        geo_file.close()


def prepare_geolayout_export(armature_obj, obj):  # Add OOT bone crumpling logic
    # Make object and armature space the same.
    setOrigin(armature_obj, obj)

    # Apply armature scale.
    bpy.ops.object.select_all(action="DESELECT")
    armature_obj.select_set(True)
    bpy.context.view_layer.objects.active = armature_obj
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True, properties=False)


def get_all_armatures_objects(armature_obj) -> list[bpy.types.Object]:
    linked_armatures = set()
    linked_armatures.add(armature_obj)
    for bone in armature_obj.data.bones:
        bone_props: SM64_BoneProperties = bone.fast64.sm64
        linked_armatures.update(bone_props.get_needed_armatures(bone, armature_obj))
    return list(linked_armatures)


def get_camera_obj(camera):
    for obj in bpy.data.objects:
        if obj.data == camera:
            return obj
    raise PluginError(f"The level camera {camera.name} is no longer in the scene.")


def append_revert_to_geolayout(geolayout_graph, f_model):
    f_model.materialRevert = GfxList(
        f_model.name + "_" + "material_revert_render_settings", GfxListTag.MaterialRevert, f_model.DLFormat
    )
    revertMatAndEndDraw(f_model.materialRevert, [DPSetEnvColor(0xFF, 0xFF, 0xFF, 0xFF), DPSetAlphaCompare("G_AC_NONE")])

    drawLayers = set(str(layer) for layer in geolayout_graph.getDrawLayers())

    # Revert settings in each draw layer
    for layer in sorted(drawLayers):  # Must be sorted, otherwise ordering is random due to `set` behavior
        dlNode = DisplayListNode(layer)
        dlNode.DLmicrocode = f_model.materialRevert

        # Assume first node is culling radius
        # This is important, since a culling radius groups things separately.
        # If we added these nodes outside the culling radius, they would not happen
        # right after the nodes inside.
        geolayout_graph.startGeolayout.nodes[0].children.append(TransformNode(dlNode))


def get_start_bones(obj):
    start_nodes: list = []

    obj_props: SM64_ObjectProperties = obj.fast64.sm64

    if obj_props.set_culling_radius:
        start_nodes.append(TransformNode(obj_props.culling.get_node(obj)))
    if obj_props.use_render_range:
        if not start_nodes:
            start_nodes.append(TransformNode(StartNode()))
        start_nodes.append(TransformNode(RenderRangeNode(obj_props.render_range[0], obj_props.render_range[1])))
    if obj_props.add_shadow:
        start_nodes.append(TransformNode(obj_props.shadow.get_node()))
    if obj_props.add_func:
        if not start_nodes:
            start_nodes.append(TransformNode(StartNode()))
        start_nodes.append(TransformNode(obj_props.geo_asm.get_node(obj)))

    if not start_nodes:
        start_nodes.append(TransformNode(StartNode()))

    first_bone = start_nodes[0]
    parent_bone = None

    for bone in start_nodes:
        if parent_bone:
            bone.parent = parent_bone
            parent_bone.children.append(bone)
        parent_bone = bone
    return first_bone, bone


def convert_armature_to_geolayout(
    armature_obj, obj, f3d_type, is_hw_v1, camera, name, dl_format, convert_texture_data
):
    inline = bpy.context.scene.exportInlineF3D
    f_model = SM64Model(
        f3d_type,
        is_hw_v1,
        name,
        dl_format,
        GfxMatWriteMethod.WriteDifferingAndRevert if not inline else GfxMatWriteMethod.WriteAll,
    )

    if len(armature_obj.children) == 0:
        raise PluginError("No mesh parented to armature.")

    info_dict = getInfoDict(obj)

    # Find start bones (parentless bones)
    start_bone_names = find_start_bones(armature_obj)

    # Start geolayout
    if camera:
        geolayout_graph = GeolayoutGraph(name)
        cameraObj = get_camera_obj(camera)
        mesh_geolayout = saveCameraSettingsToGeolayout(geolayout_graph, cameraObj, armature_obj, name + "_geo")
        start_command = mesh_geolayout.nodes[0]
    else:
        geolayout_graph = GeolayoutGraph(name + "_geo")
        first_command, start_command = get_start_bones(armature_obj)
        geolayout_graph.startGeolayout.nodes.append(first_command)
        mesh_geolayout = geolayout_graph.startGeolayout

    for i, start_bone_name in enumerate(start_bone_names):
        process_bone(
            f_model,
            start_bone_name,
            obj,
            armature_obj,
            None,
            None,
            None,
            start_command,
            [],
            name,
            mesh_geolayout,
            geolayout_graph,
            info_dict,
            convert_texture_data,
        )
    generate_switch_options(start_command, mesh_geolayout, geolayout_graph, name)

    append_revert_to_geolayout(geolayout_graph, f_model)
    geolayout_graph.generateSortedList()

    if inline:
        bleed_gfx = GeoLayoutBleed()
        bleed_gfx.bleed_geo_layout_graph(f_model, geolayout_graph)

    return geolayout_graph, f_model


def convert_object_to_geolayout(
    obj, convert_transform_matrix, f3d_type, is_hw_v1, name, f_model: FModel, areaObj, dl_format, convert_texture_data
):
    inline = bpy.context.scene.exportInlineF3D
    if f_model is None:
        f_model = SM64Model(
            f3d_type,
            is_hw_v1,
            name,
            dl_format,
            GfxMatWriteMethod.WriteDifferingAndRevert if not inline else GfxMatWriteMethod.WriteAll,
        )

    # Start geolayout
    if areaObj is not None:
        geolayout_graph = GeolayoutGraph(name)
        mesh_geolayout = saveCameraSettingsToGeolayout(geolayout_graph, areaObj, obj, name + "_geo")
        root_obj = areaObj
        f_model.global_data.addAreaData(
            areaObj.areaIndex, FAreaData(FFogData(areaObj.area_fog_position, areaObj.area_fog_color))
        )
        start_command = mesh_geolayout.nodes[0]
    else:
        geolayout_graph = GeolayoutGraph(name + "_geo")
        if isinstance(obj.data, bpy.types.Mesh):
            first_command, start_command = get_start_bones(obj)
            geolayout_graph.startGeolayout.nodes.append(first_command)
        mesh_geolayout = geolayout_graph.startGeolayout
        root_obj = obj

    # Duplicate objects to apply scale / modifiers / linked data
    tempObj, allObjs = duplicateHierarchy(
        root_obj, "ignore_render", True, None if areaObj is None else areaObj.areaIndex
    )
    try:
        processMesh(
            f_model,
            tempObj,
            convert_transform_matrix,
            start_command,
            geolayout_graph.startGeolayout,
            geolayout_graph,
            True,
            convert_texture_data,
        )
        cleanupDuplicatedObjects(allObjs)
        root_obj.select_set(True)
        bpy.context.view_layer.objects.active = root_obj
    except Exception as e:
        cleanupDuplicatedObjects(allObjs)
        root_obj.select_set(True)
        bpy.context.view_layer.objects.active = root_obj
        raise Exception(str(e))

    append_revert_to_geolayout(geolayout_graph, f_model)
    geolayout_graph.generateSortedList()
    if inline:
        bleed_gfx = GeoLayoutBleed()
        bleed_gfx.bleed_geo_layout_graph(
            f_model, geolayout_graph, use_rooms=None if areaObj is None else areaObj.enableRoomSwitch
        )

    return geolayout_graph, f_model


# C Export
def exportGeolayoutArmatureC(
    armature_obj,
    obj,
    convert_transform_matrix,
    f3d_type,
    is_hw_v1,
    tex_dir,
    save_png,
    tex_separate,
    camera,
    dl_format,
    export_settings: "SM64_ExportSettings",
    geo_name,
):
    geolayout_graph, f_model = convert_armature_to_geolayout(
        armature_obj, obj, f3d_type, is_hw_v1, camera, geo_name, dl_format, not save_png
    )

    return saveGeolayoutC(
        geolayout_graph,
        f_model,
        tex_dir,
        save_png,
        tex_separate,
        dl_format,
        export_settings,
        geo_name,
    )


def exportGeolayoutObjectC(
    obj,
    convert_transform_matrix,
    f3d_type,
    is_hw_v1,
    tex_dir,
    save_png,
    tex_separate,
    dl_format,
    export_settings: "SM64_ExportSettings",
    geo_name,
):
    geolayout_graph, f_model = convert_object_to_geolayout(
        obj, convert_transform_matrix, f3d_type, is_hw_v1, geo_name, None, None, dl_format, not save_png
    )

    return saveGeolayoutC(
        geolayout_graph,
        f_model,
        tex_dir,
        save_png,
        tex_separate,
        dl_format,
        export_settings,
        geo_name,
    )


def saveGeolayoutC(
    geolayout_graph: GeolayoutGraph,
    f_model: FModel,
    tex_dir,
    save_png,
    tex_separate,
    dl_format,
    export_settings: "SM64_ExportSettings",
    geo_name,
):
    from ..properties import SM64_HeaderType

    dir_path = export_settings.export_path

    if export_settings.header_type == SM64_HeaderType.ACTOR:
        scrollName = "actor_geo_" + export_settings.folder_name
    elif export_settings.folder_name == SM64_HeaderType.LEVEL:
        scrollName = export_settings.level_name + "_level_geo_" + export_settings.folder_name
    else:
        scrollName = ""

    gfxFormatter = SM64GfxFormatter(ScrollMethod.Vertex)

    group_name = export_settings.group_name

    if not os.path.exists(dir_path):
        os.mkdir(dir_path)

    if export_settings.header_type == SM64_HeaderType.LEVEL:
        texExportPath = export_settings.get_level_directory()
    else:
        texExportPath = dir_path  # Is this one correct?
    tex_dir = export_settings.get_tex_directory(tex_dir)

    exportData = f_model.to_c(TextureExportSettings(tex_separate, save_png, tex_dir, texExportPath), gfxFormatter)
    staticData = exportData.staticData
    dynamicData = exportData.dynamicData
    texC = exportData.textureData

    scrollData = f_model.to_c_scroll(scrollName, gfxFormatter)
    geolayout_graph.startGeolayout.name = geo_name

    geo_data = geolayout_graph.to_c()

    if export_settings.header_type == SM64_HeaderType.ACTOR:
        actor_directory = export_settings.get_actor_directory()
        matCInclude = f'#include "{actor_directory}/material.inc.c"'
        matHInclude = f'#include "{actor_directory}/material.inc.h"'
        headerInclude = f'#include "{actor_directory}/geo_header.h"'

        actor_directory = export_settings.get_actors_directory()
        groupPathC = os.path.join(actor_directory, f"{group_name}.c")
        groupPathGeoC = os.path.join(actor_directory, f"{group_name}_geo.c")
        groupPathH = os.path.join(actor_directory, f"{group_name}.h")

        if not os.path.exists(groupPathC):
            raise PluginError(
                f'{groupPathC} not found.\n Most likely issue is that "{group_name}" is an invalid group name.'
            )
        elif not os.path.exists(groupPathGeoC):
            raise PluginError(
                f'{groupPathGeoC} not found.\n Most likely issue is that "{groupPathGeoC}" is an invalid group name.'
            )
        elif not os.path.exists(groupPathH):
            raise PluginError(
                f'{groupPathH} not found.\n Most likely issue is that "{groupPathH}" is an invalid group name.'
            )
    elif export_settings.header_type == SM64_HeaderType.LEVEL:
        level_directory = export_settings.get_level_directory()
        matCInclude = f'#include "{level_directory}/material.inc.c"'
        matHInclude = f'#include "{level_directory}/material.inc.h"'
        headerInclude = f'#include "{level_directory}/geo_header.h"'

    modifyTexScrollFiles(export_settings.decomp_path, dir_path, scrollData)

    if dl_format == DLFormat.Static:
        staticData.source += "\n" + dynamicData.source
        staticData.header = geo_data.header + staticData.header + dynamicData.header
    else:
        geo_data.source = writeMaterialFiles(
            export_settings.decomp_path,
            dir_path,
            headerInclude,
            matHInclude,
            dynamicData.header,
            dynamicData.source,
            geo_data.source,
            export_settings.header_type == SM64_HeaderType.CUSTOM,
        )

    modelPath = os.path.join(dir_path, "model.inc.c")
    modelFile = open(modelPath, "w", newline="\n")
    modelFile.write(staticData.source)
    modelFile.close()

    if tex_separate:
        texPath = os.path.join(dir_path, "texture.inc.c")
        texFile = open(texPath, "w", newline="\n")
        texFile.write(texC.source)
        texFile.close()

    f_model.freePalettes()

    # save geolayout
    geo_path = os.path.join(dir_path, "geo.inc.c")
    geo_file = open(geo_path, "w", newline="\n")
    geo_file.write(geo_data.source)
    geo_file.close()

    # save header
    headerPath = os.path.join(dir_path, "geo_header.h")
    cDefFile = open(headerPath, "w", newline="\n")
    cDefFile.write(staticData.header)
    cDefFile.close()

    fileStatus = None
    if export_settings.header_type == SM64_HeaderType.ACTOR:
        if export_settings.folder_name == "star" and bpy.context.scene.replaceStarRefs:
            replace_star_references(export_settings.decomp_path)
        if export_settings.folder_name == "transparent_star" and bpy.context.scene.replaceTransparentStarRefs:
            replace_transparent_star_references(export_settings.decomp_path)
        if export_settings.folder_name == "marios_cap" and bpy.context.scene.replaceCapRefs:
            replace_cap_references(export_settings.decomp_path)

        # Write to group files
        actor_directory = export_settings.get_actors_directory()
        groupPathC = os.path.join(actor_directory, group_name + ".c")
        groupPathGeoC = os.path.join(actor_directory, group_name + "_geo.c")
        groupPathH = os.path.join(actor_directory, group_name + ".h")

        writeIfNotFound(groupPathC, f'\n#include "{export_settings.folder_name}/model.inc.c"', "")
        writeIfNotFound(groupPathGeoC, f'\n#include "{export_settings.folder_name}/geo.inc.c"', "")
        writeIfNotFound(groupPathH, f'\n#include "{export_settings.folder_name}/geo_header.h"', "\n#endif")

        texscrollIncludeC = f'#include "{actor_directory}/texscroll.inc.c"'
        texscrollIncludeH = f'#include "{actor_directory}/texscroll.inc.h"'
        texscrollGroup = group_name
        texscrollGroupInclude = '#include "actors/' + group_name + '.h"'

    elif export_settings.header_type == SM64_HeaderType.LEVEL:
        level_folder = export_settings.get_level_directory()

        groupPathC = os.path.join(level_folder, "leveldata.c")
        groupPathGeoC = os.path.join(level_folder, "geo.c")
        groupPathH = os.path.join(level_folder, "header.h")

        writeIfNotFound(groupPathC, f'\n#include "{level_folder}/model.inc.c"', "")
        writeIfNotFound(groupPathGeoC, f'\n#include "{level_folder}/geo.inc.c"', "")
        writeIfNotFound(groupPathH, f'\n#include "{level_folder}/geo_header.h"', "\n#endif")

        texscrollIncludeC = f'#include "{level_folder}/texscroll.inc.c"'
        texscrollIncludeH = f'#include "{level_folder}/texscroll.inc.h"'
        texscrollGroup = export_settings.level_name
        texscrollGroupInclude = f'#include "{level_folder}/header.h"'

    if export_settings.header_type != SM64_HeaderType.CUSTOM:
        fileStatus = modifyTexScrollHeadersGroup(
            export_settings.decomp_path,
            texscrollIncludeC,
            texscrollIncludeH,
            texscrollGroup,
            scrollData.topLevelScrollFunc,
            texscrollGroupInclude,
            scrollData.hasScrolling(),
        )

        if dl_format != DLFormat.Static:  # Change this
            writeMaterialHeaders(export_settings.decomp_path, matCInclude, matHInclude)

    return staticData.header, fileStatus


# Insertable Binary
def exportGeolayoutArmatureInsertableBinary(
    armature_obj, obj, convert_transform_matrix, f3d_type, is_hw_v1, filepath, camera
):
    geolayout_graph, f_model = convert_armature_to_geolayout(
        armature_obj,
        obj,
        f3d_type,
        is_hw_v1,
        camera,
        armature_obj.name,
        DLFormat.Static,
        True,
    )

    saveGeolayoutInsertableBinary(geolayout_graph, f_model, filepath, f3d_type)


def exportGeolayoutObjectInsertableBinary(obj, convert_transform_matrix, f3d_type, is_hw_v1, filepath, camera):
    geolayout_graph, f_model = convert_object_to_geolayout(
        obj, convert_transform_matrix, f3d_type, is_hw_v1, obj.name, None, None, DLFormat.Static, True
    )

    saveGeolayoutInsertableBinary(geolayout_graph, f_model, filepath, f3d_type)


def saveGeolayoutInsertableBinary(geolayout_graph, f_model, filepath, f3d):
    data, startRAM = getBinaryBank0GeolayoutData(f_model, geolayout_graph, 0, [0, 0xFFFFFF])

    address_ptrs = geolayout_graph.get_ptr_addresses()
    address_ptrs.extend(f_model.get_ptr_addresses(f3d))

    writeInsertableFile(
        filepath, insertableBinaryTypes["Geolayout"], address_ptrs, geolayout_graph.startGeolayout.startAddress, data
    )


# Binary Bank 0 Export
def exportGeolayoutArmatureBinaryBank0(
    romfile,
    armature_obj,
    obj,
    exportRange,
    convert_transform_matrix,
    levelCommandPos,
    modelID,
    textDumpFilePath,
    f3d_type,
    is_hw_v1,
    ram_address,
    camera,
):

    geolayout_graph, f_model = convert_armature_to_geolayout(
        armature_obj,
        obj,
        f3d_type,
        is_hw_v1,
        camera,
        armature_obj.name,
        DLFormat.Static,
        True,
    )

    return saveGeolayoutBinaryBank0(
        romfile, f_model, geolayout_graph, exportRange, levelCommandPos, modelID, textDumpFilePath, ram_address
    )


def exportGeolayoutObjectBinaryBank0(
    romfile,
    obj,
    exportRange,
    convert_transform_matrix,
    levelCommandPos,
    modelID,
    textDumpFilePath,
    f3d_type,
    is_hw_v1,
    ram_address,
    camera,
):

    geolayout_graph, f_model = convert_object_to_geolayout(
        obj, convert_transform_matrix, f3d_type, is_hw_v1, obj.name, None, None, DLFormat.Static, True
    )

    return saveGeolayoutBinaryBank0(
        romfile, f_model, geolayout_graph, exportRange, levelCommandPos, modelID, textDumpFilePath, ram_address
    )


def saveGeolayoutBinaryBank0(
    romfile, f_model, geolayout_graph, exportRange, levelCommandPos, modelID, textDumpFilePath, ram_address
):
    data, startRAM = getBinaryBank0GeolayoutData(f_model, geolayout_graph, ram_address, exportRange)
    segmentData = copy.copy(bank0Segment)

    startAddress = get64bitAlignedAddr(exportRange[0])
    romfile.seek(startAddress)
    romfile.write(data)

    geoStart = geolayout_graph.startGeolayout.startAddress
    segPointerData = encodeSegmentedAddr(geoStart, segmentData)
    geoWriteLevelCommand(romfile, segPointerData, levelCommandPos, modelID)
    geoWriteTextDump(textDumpFilePath, geolayout_graph, segmentData)

    return ((startAddress, startAddress + len(data)), startRAM + 0x80000000, geoStart + 0x80000000)


def getBinaryBank0GeolayoutData(f_model, geolayout_graph, ram_address, exportRange):
    f_model.freePalettes()
    segmentData = copy.copy(bank0Segment)
    startRAM = get64bitAlignedAddr(ram_address)
    nonGeoStartAddr = startRAM + geolayout_graph.size()

    geolayout_graph.set_addr(startRAM)
    addrRange = f_model.set_addr(nonGeoStartAddr)
    addrEndInROM = addrRange[1] - startRAM + exportRange[0]
    if addrEndInROM > exportRange[1]:
        raise PluginError(f"Size too big: Data ends at {hex(addrEndInROM)}, which is larger than the specified range.")
    bytesIO = BytesIO()
    geolayout_graph.save_binary(bytesIO, segmentData)
    f_model.save_binary(bytesIO, segmentData)

    data = bytesIO.getvalue()[startRAM:]
    bytesIO.close()
    return data, startRAM


# Binary Export
def exportGeolayoutArmatureBinary(
    romfile,
    armature_obj,
    obj,
    exportRange,
    convert_transform_matrix,
    levelData,
    levelCommandPos,
    modelID,
    textDumpFilePath,
    f3d_type,
    is_hw_v1,
    camera,
):

    geolayout_graph, f_model = convert_armature_to_geolayout(
        armature_obj,
        obj,
        f3d_type,
        is_hw_v1,
        camera,
        armature_obj.name,
        DLFormat.Static,
        True,
    )

    return saveGeolayoutBinary(
        romfile, geolayout_graph, f_model, exportRange, levelData, levelCommandPos, modelID, textDumpFilePath
    )


def exportGeolayoutObjectBinary(
    romfile,
    obj,
    exportRange,
    convert_transform_matrix,
    levelData,
    levelCommandPos,
    modelID,
    textDumpFilePath,
    f3d_type,
    is_hw_v1,
    camera,
):

    geolayout_graph, f_model = convert_object_to_geolayout(
        obj, convert_transform_matrix, f3d_type, is_hw_v1, obj.name, None, None, DLFormat.Static, True
    )

    return saveGeolayoutBinary(
        romfile, geolayout_graph, f_model, exportRange, levelData, levelCommandPos, modelID, textDumpFilePath
    )


def saveGeolayoutBinary(
    romfile, geolayout_graph, f_model, exportRange, levelData, levelCommandPos, modelID, textDumpFilePath
):
    f_model.freePalettes()

    # Get length of data, then actually write it after relative addresses
    # are found.
    startAddress = get64bitAlignedAddr(exportRange[0])
    nonGeoStartAddr = startAddress + geolayout_graph.size()

    geolayout_graph.set_addr(startAddress)
    addrRange = f_model.set_addr(nonGeoStartAddr)
    if addrRange[1] > exportRange[1]:
        raise PluginError(
            "Size too big: Data ends at " + hex(addrRange[1]) + ", which is larger than the specified range."
        )
    geolayout_graph.save_binary(romfile, levelData)
    f_model.save_binary(romfile, levelData)

    geoStart = geolayout_graph.startGeolayout.startAddress
    segPointerData = encodeSegmentedAddr(geoStart, levelData)
    geoWriteLevelCommand(romfile, segPointerData, levelCommandPos, modelID)
    geoWriteTextDump(textDumpFilePath, geolayout_graph, levelData)

    return (startAddress, addrRange[1]), bytesToHex(segPointerData)


def geoWriteLevelCommand(romfile, segPointerData, levelCommandPos, modelID):
    if levelCommandPos is not None and modelID is not None:
        romfile.seek(levelCommandPos + 3)
        romfile.write(modelID.to_bytes(1, byteorder="big"))
        romfile.seek(levelCommandPos + 4)
        romfile.write(segPointerData)


def geoWriteTextDump(textDumpFilePath, geolayout_graph, levelData):
    if textDumpFilePath is not None:
        openfile = open(textDumpFilePath, "w", newline="\n")
        openfile.write(geolayout_graph.toTextDump(levelData))
        openfile.close()


# Switch Handling Process
# When convert armature to geolayout node hierarchy, mesh switch options
# are converted to switch node children, but material/draw layer options
# are converted to SwitchOverrideNodes. During this process, any material
# override geometry will be generated as well.

# Afterward, the node hierarchy is traversed again, and any SwitchOverride
# nodes are converted to actual geolayout node hierarchies.
def generate_switch_options(transform_node, geolayout, geolayout_graph, prefix):
    print(f"Generating switch options for {geolayout.name}")
    if isinstance(transform_node.node, JumpNode):
        for node in transform_node.node.geolayout.nodes:
            generate_switch_options(node, transform_node.node.geolayout, geolayout_graph, prefix)
    overrideNodes = []
    if isinstance(transform_node.node, SwitchNode):
        switchName = transform_node.node.switch_name
        prefix += "_" + switchName

        materialOverrideTexDimensions = None

        for i, childNode in enumerate(transform_node.children):
            prefixName = prefix + "_opt" + str(i)

            if isinstance(childNode.node, SwitchOverrideNode):
                draw_layer = childNode.node.drawLayer
                material = childNode.node.material
                specific_material = childNode.node.specificMat
                override_type = childNode.node.overrideType
                texDimensions = childNode.node.texDimensions
                if (
                    texDimensions is not None
                    and materialOverrideTexDimensions is not None
                    and materialOverrideTexDimensions != tuple(texDimensions)
                ):
                    raise PluginError(
                        f'In switch bone "{switchName}", some material overrides \n\
                        have textures with dimensions differing from the original material.\n\
                        UV coordinates are in pixel units, so there will be UV errors in those overrides.\n\
                        Make sure that all overrides have the same texture dimensions as the original material.\n\
                        Note that materials with no textures default to dimensions of 32x32.'
                    )

                if texDimensions is not None:
                    materialOverrideTexDimensions = tuple(texDimensions)

                # This should be a 0xB node
                index = transform_node.children.index(childNode)
                transform_node.children.remove(childNode)

                # Switch option bones should have unique names across all
                # armatures.
                option_geolayout = geolayout_graph.addGeolayout(childNode, prefixName)
                geolayout_graph.addJumpNode(transform_node, geolayout, option_geolayout, index)
                option_geolayout.nodes.append(TransformNode(StartNode()))
                copyNode = option_geolayout.nodes[0]

                option0Nodes = transform_node.children[0]
                for overrideChild in option0Nodes.children:
                    generateOverrideHierarchy(
                        copyNode,
                        overrideChild,
                        material,
                        specific_material,
                        override_type,
                        draw_layer,
                        option0Nodes.children.index(overrideChild),
                        option_geolayout,
                        geolayout_graph,
                        option_geolayout.name,
                    )
                if material is not None:
                    overrideNodes.append(copyNode)

    for i, childNode in enumerate(transform_node.children):
        if isinstance(transform_node.node, SwitchNode):
            prefixName = prefix + "_opt" + str(i)
        else:
            prefixName = prefix

        if childNode not in overrideNodes:
            generate_switch_options(childNode, geolayout, geolayout_graph, prefixName)


def generateOverrideHierarchy(
    parentCopyNode,
    transform_node,
    material,
    specific_material,
    override_type,
    draw_layer,
    index,
    geolayout,
    geolayout_graph,
    switchOptionName,
):
    if isinstance(transform_node.node, SwitchOverrideNode) and material is not None:
        return

    copyNode = TransformNode(copy.copy(transform_node.node))
    copyNode.parent = parentCopyNode
    parentCopyNode.children.insert(index, copyNode)
    if isinstance(transform_node.node, JumpNode):
        jumpName = switchOptionName + "_jump_" + transform_node.node.geolayout.name
        if any([geolayout.name == jumpName for geolayout in geolayout_graph.secondaryGeolayouts.values()]):
            return
        jumpGeolayout = geolayout_graph.addGeolayout(transform_node, jumpName)
        geolayout_graph.addGeolayoutCall(geolayout, jumpGeolayout)
        start_node = TransformNode(StartNode())
        jumpGeolayout.nodes.append(start_node)

        oldGeolayout = copyNode.node.geolayout
        copyNode.node.geolayout = jumpGeolayout
        nodes = oldGeolayout.nodes
        if len(nodes) == 1 and isinstance(nodes[0].node, StartNode):
            nodes = nodes[0].children
        for node in nodes:
            generateOverrideHierarchy(
                start_node,
                node,
                material,
                specific_material,
                override_type,
                draw_layer,
                nodes.index(node),
                jumpGeolayout,
                geolayout_graph,
                jumpGeolayout.name,
            )

    elif not isinstance(copyNode.node, SwitchOverrideNode) and copyNode.node.has_dl and not getattr(copyNode.node, "dlRef", False):
        if material is not None:
            copyNode.node.DLmicrocode = copyNode.node.fMesh.drawMatOverrides[
                (material, specific_material, override_type)
            ]
            copyNode.node.override_hash = (material, specific_material, override_type)
        if draw_layer is not None:
            copyNode.node.drawLayer = draw_layer

    for child in transform_node.children:
        generateOverrideHierarchy(
            copyNode,
            child,
            material,
            specific_material,
            override_type,
            draw_layer,
            transform_node.children.index(child),
            geolayout,
            geolayout_graph,
            switchOptionName,
        )


def addParentNode(parent_transform_node: TransformNode, geoNode):
    transform_node = TransformNode(geoNode)
    transform_node.parent = parent_transform_node
    parent_transform_node.children.append(transform_node)
    return transform_node


def partOfGeolayout(obj):
    useGeoEmpty = obj.type == "EMPTY" and checkSM64EmptyUsesGeoLayout(obj.sm64_obj_type)
    return obj.type == "MESH" or useGeoEmpty


def getSwitchChildren(areaRoot):
    geoChildren = [child for child in areaRoot.children if partOfGeolayout(child)]
    alphabeticalChildren = sorted(geoChildren, key=lambda childObj: childObj.original_name.lower())
    return alphabeticalChildren


def set_rooms(obj, roomIndex=None):
    # Child objects
    if roomIndex is not None:
        obj.room_num = roomIndex
        for childObj in obj.children:
            set_rooms(childObj, roomIndex)

    # Area root object
    else:
        alphabeticalChildren = getSwitchChildren(obj)
        for i in range(len(alphabeticalChildren)):
            set_rooms(alphabeticalChildren[i], i)  # index starts at 1, but 0 is reserved for no room.


def isZeroRotation(rotate: mathutils.Quaternion):
    eulerRot = rotate.to_euler(geoNodeRotateOrder)
    return (
        convertEulerFloatToShort(eulerRot[0]) == 0
        and convertEulerFloatToShort(eulerRot[1]) == 0
        and convertEulerFloatToShort(eulerRot[2]) == 0
    )


def isZeroTranslation(translate: mathutils.Vector):
    return (
        convertFloatToShort(translate[0]) == 0
        and convertFloatToShort(translate[1]) == 0
        and convertFloatToShort(translate[2]) == 0
    )


def isZeroScaleChange(scale: mathutils.Vector):
    return (
        int(round(scale[0] * 0x10000)) == 0x10000
        and int(round(scale[1] * 0x10000)) == 0x10000
        and int(round(scale[2] * 0x10000)) == 0x10000
    )


def getOptimalNode(translate, rotate, draw_layer, has_dl, zero_translation, zero_rotation):
    if zero_rotation and zero_translation:
        node = DisplayListNode(draw_layer)
    elif zero_rotation:
        node = TranslateNode(draw_layer, has_dl, translate)
    elif zero_translation:
        node = RotateNode(draw_layer, has_dl, rotate)
    else:
        node = TranslateRotateNode(draw_layer, has_dl, translate, rotate)
    return node


def processPreInlineGeo(
    inlineGeoConfig: InlineGeolayoutObjConfig, obj: bpy.types.Object, parent_transform_node: TransformNode
):
    if inlineGeoConfig.name == "Geo ASM":
        node = obj.fast64.sm64.geo_asm.get_node(obj)
    elif inlineGeoConfig.name == "Geo Branch":
        node = JumpNode(True, None, obj.geoReference)
    elif inlineGeoConfig.name == "Geo Displaylist":
        node = DisplayListNode(int(obj.draw_layer_static), obj.dlReference)
    elif inlineGeoConfig.name == "Custom Geo Command":
        node = CustomNode(obj.customGeoCommand, obj.customGeoCommandArgs)
    addParentNode(parent_transform_node, node)  # Allow this node to be translated/rotated


def processInlineGeoNode(
    inlineGeoConfig: InlineGeolayoutObjConfig,
    obj: bpy.types.Object,
    parent_transform_node: TransformNode,
    translate: mathutils.Vector,
    rotate: mathutils.Quaternion,
    scale: mathutils.Vector,
):
    node = None
    if inlineGeoConfig.name == "Geo Translate/Rotate":
        node = TranslateRotateNode(obj.draw_layer_static, obj.useDLReference, translate, rotate, obj.dlReference)
    elif inlineGeoConfig.name == "Geo Billboard":
        node = BillboardNode(obj.draw_layer_static, obj.useDLReference, translate, obj.dlReference)
    elif inlineGeoConfig.name == "Geo Translate Node":
        node = TranslateNode(obj.draw_layer_static, obj.useDLReference, translate, obj.dlReference)
    elif inlineGeoConfig.name == "Geo Rotation Node":
        node = RotateNode(obj.draw_layer_static, obj.useDLReference, rotate, obj.dlReference)
    elif inlineGeoConfig.name == "Geo Scale":
        node = ScaleNode(obj.draw_layer_static, scale, obj.useDLReference, obj.dlReference)
    else:
        raise PluginError(f"Ooops! Didnt implement inline geo exporting for {inlineGeoConfig.name}")

    return node, parent_transform_node


# This function should be called on a copy of an object
# The copy will have modifiers / scale applied and will be made single user
def processMesh(
    f_model: FModel,
    obj: bpy.types.Object,
    transformMatrix: mathutils.Matrix,
    parent_transform_node: TransformNode,
    geolayout: Geolayout,
    geolayout_graph: GeolayoutGraph,
    isRoot: bool,
    convert_texture_data: bool,
):
    useGeoEmpty = obj.data is None and checkSM64EmptyUsesGeoLayout(obj.sm64_obj_type)

    useSwitchNode = obj.data is None and obj.sm64_obj_type == "Switch"

    useInlineGeo = obj.data is None and checkIsSM64InlineGeoLayout(obj.sm64_obj_type)

    addRooms = isRoot and obj.data is None and obj.sm64_obj_type == "Area Root" and obj.enableRoomSwitch

    inlineGeoConfig: InlineGeolayoutObjConfig = inlineGeoLayoutObjects.get(obj.sm64_obj_type)
    processed_inline_geo = False

    isPreInlineGeoLayout = checkIsSM64PreInlineGeoLayout(obj.sm64_obj_type)
    if useInlineGeo and isPreInlineGeoLayout:
        processed_inline_geo = True
        processPreInlineGeo(inlineGeoConfig, obj, parent_transform_node)

    # Its okay to return if ignore_render, because when we duplicated obj hierarchy we stripped all
    # ignore_renders from geolayout.
    if not partOfGeolayout(obj) or obj.ignore_render:
        return

    if isRoot:
        translate = mathutils.Vector((0, 0, 0))
        rotate = mathutils.Quaternion()
        scale = mathutils.Vector((1, 1, 1))
    elif obj.get("original_mtx"):  # object is instanced or a transformation
        orig_mtx = mathutils.Matrix(obj["original_mtx"])
        translate, rotate, scale = orig_mtx.decompose()
        translate = translate_blender_to_n64(translate)
        rotate = rotate_quat_blender_to_n64(rotate)
    else:  # object is NOT instanced
        translate, rotate, scale = obj.matrix_local.decompose()

    zero_rotation = isZeroRotation(rotate)
    zero_translation = isZeroTranslation(translate)
    zero_scale_change = isZeroScaleChange(scale)

    if useSwitchNode or addRooms:  # Specific empty types
        if useSwitchNode:
            switchFunc = obj.switchFunc
            switchParam = obj.switchParam
        elif addRooms:
            switchFunc = "geo_switch_area"
            switchParam = len(obj.children)

        # Rooms are not set here (since this is just a copy of the original hierarchy)
        # They should be set previously, using set_rooms()
        preRoomSwitchParentNode = parent_transform_node
        parent_transform_node = addParentNode(
            parent_transform_node, SwitchNode(switchFunc, switchParam, obj.original_name)
        )
        alphabeticalChildren = getSwitchChildren(obj)
        for i in range(len(alphabeticalChildren)):
            childObj = alphabeticalChildren[i]
            if i == 0:  # Outside room system
                # TODO: Allow users to specify whether this should be rendered before or after rooms (currently, it is after)
                processMesh(
                    f_model,
                    childObj,
                    transformMatrix,
                    preRoomSwitchParentNode,
                    geolayout,
                    geolayout_graph,
                    False,
                    convert_texture_data,
                )
            else:
                option_geolayout = geolayout_graph.addGeolayout(
                    childObj, f_model.name + "_" + childObj.original_name + "_geo"
                )
                geolayout_graph.addJumpNode(parent_transform_node, geolayout, option_geolayout)
                if not zero_rotation or not zero_translation:
                    start_node = TransformNode(
                        getOptimalNode(translate, rotate, 1, False, zero_translation, zero_rotation)
                    )
                else:
                    start_node = TransformNode(StartNode())
                option_geolayout.nodes.append(start_node)
                processMesh(
                    f_model,
                    childObj,
                    transformMatrix,
                    start_node,
                    option_geolayout,
                    geolayout_graph,
                    False,
                    convert_texture_data,
                )

    else:
        if useInlineGeo and not processed_inline_geo:
            node, parent_transform_node = processInlineGeoNode(
                inlineGeoConfig, obj, parent_transform_node, translate, rotate, scale[0]
            )
            processed_inline_geo = True

        elif obj.geo_cmd_static == "Optimal" or useGeoEmpty:
            if not zero_scale_change:
                # - first translate/rotate without a DL
                # - then child -> scale with DL
                if not zero_translation or not zero_rotation:
                    pNode = getOptimalNode(
                        translate, rotate, int(obj.draw_layer_static), False, zero_translation, zero_rotation
                    )
                    parent_transform_node = addParentNode(parent_transform_node, pNode)
                node = ScaleNode(int(obj.draw_layer_static), scale[0], True)
            else:
                node = getOptimalNode(
                    translate, rotate, int(obj.draw_layer_static), True, zero_translation, zero_rotation
                )

        elif obj.geo_cmd_static == "DisplayListWithOffset":
            if not zero_rotation or not zero_scale_change:
                # translate/rotate -> scale -> DisplayListWithOffset
                node = DisplayListWithOffsetNode(int(obj.draw_layer_static), True, mathutils.Vector((0, 0, 0)))

                parent_transform_node = addParentNode(
                    parent_transform_node, TranslateRotateNode(1, False, translate, rotate)
                )

                if not zero_scale_change:
                    parent_transform_node = addParentNode(
                        parent_transform_node, ScaleNode(int(obj.draw_layer_static), scale[0], False)
                    )
            else:
                node = DisplayListWithOffsetNode(int(obj.draw_layer_static), True, translate)

        else:  # Billboard
            if not zero_rotation or not zero_scale_change:  # If rotated or scaled
                # Order here MUST be billboard with translation -> rotation -> scale -> displaylist
                node = DisplayListNode(int(obj.draw_layer_static))

                # Add billboard to top layer with translation
                parent_transform_node = addParentNode(
                    parent_transform_node, BillboardNode(int(obj.draw_layer_static), False, translate)
                )

                if not zero_rotation:
                    # Add rotation to top layer
                    parent_transform_node = addParentNode(
                        parent_transform_node, RotateNode(int(obj.draw_layer_static), False, rotate)
                    )

                if not zero_scale_change:
                    # Add scale node after billboard
                    parent_transform_node = addParentNode(
                        parent_transform_node, ScaleNode(int(obj.draw_layer_static), scale[0], False)
                    )
            else:  # Use basic billboard node
                node = BillboardNode(int(obj.draw_layer_static), True, translate)

        transform_node = TransformNode(node)
        obj_props: SM64_ObjectProperties = obj.fast64.sm64

        if obj.data is None:
            fMeshes = {}
        elif obj.get("instanced_mesh_name"):
            temp_obj = get_obj_temp_mesh(obj)
            if temp_obj is None:
                raise ValueError(
                    "The source of an instanced mesh could not be found. Please contact a Fast64 maintainer for support."
                )

            src_meshes = temp_obj.get("src_meshes", [])

            if len(src_meshes):
                fMeshes = {}
                node.dlRef = src_meshes[0]["name"]
                node.drawLayer = src_meshes[0]["layer"]
                processed_inline_geo = True

                for src_mesh in src_meshes[1:]:
                    additionalNode = (
                        DisplayListNode(src_mesh["layer"], src_mesh["name"])
                        if not isinstance(node, BillboardNode)
                        else BillboardNode(src_mesh["layer"], True, [0, 0, 0], src_mesh["name"])
                    )
                    additional_transform_node = TransformNode(additionalNode)
                    transform_node.children.append(additional_transform_node)
                    additional_transform_node.parent = transform_node

            else:
                tri_converter_info = TriangleConverterInfo(
                    temp_obj, None, f_model.f3d, transformMatrix, getInfoDict(temp_obj)
                )
                fMeshes = saveStaticModel(
                    tri_converter_info,
                    f_model,
                    temp_obj,
                    transformMatrix,
                    f_model.name,
                    convert_texture_data,
                    False,
                    "sm64",
                )
                if fMeshes:
                    temp_obj["src_meshes"] = [
                        ({"name": f_mesh.draw.name, "layer": draw_layer}) for draw_layer, f_mesh in fMeshes.items()
                    ]
                    node.dlRef = temp_obj["src_meshes"][0]["name"]
                else:
                    # TODO: Display warning to the user that there is an object that doesn't have polygons
                    print("Object", obj.original_name, "does not have any polygons.")

        else:
            tri_converter_info = TriangleConverterInfo(obj, None, f_model.f3d, transformMatrix, getInfoDict(obj))
            fMeshes = saveStaticModel(
                tri_converter_info, f_model, obj, transformMatrix, f_model.name, convert_texture_data, False, "sm64"
            )

        if fMeshes is None or len(fMeshes) == 0:
            if not processed_inline_geo or isPreInlineGeoLayout:
                node.has_dl = False
        else:
            firstNodeProcessed = False
            for draw_layer, f_mesh in fMeshes.items():
                if not firstNodeProcessed:
                    node.DLmicrocode = f_mesh.draw
                    node.fMesh = f_mesh
                    node.drawLayer = draw_layer  # previous draw_layer assigments useless?
                    firstNodeProcessed = True
                else:
                    additionalNode = (
                        DisplayListNode(draw_layer)
                        if not isinstance(node, BillboardNode)
                        else BillboardNode(draw_layer, True, [0, 0, 0])
                    )
                    additionalNode.DLmicrocode = f_mesh.draw
                    additionalNode.fMesh = f_mesh
                    additional_transform_node = TransformNode(additionalNode)
                    transform_node.children.append(additional_transform_node)
                    additional_transform_node.parent = transform_node

        parent_transform_node.children.append(transform_node)
        transform_node.parent = parent_transform_node

        alphabeticalChildren = sorted(obj.children, key=lambda childObj: childObj.original_name.lower())
        for childObj in alphabeticalChildren:
            processMesh(
                f_model,
                childObj,
                transformMatrix,
                transform_node,
                geolayout,
                geolayout_graph,
                False,
                convert_texture_data,
            )


# need to remember last geometry holding parent bone.
# to do skinning, add the 0x15 command before any non-geometry bone groups.
#

# transformMatrix is a constant matrix to apply to verts,
# not related to heirarchy.

# lastTransformParentName: last parent with mesh data.
# lastDeformParentName: last parent in transform node category.
# this may or may not include mesh data.

# If an armature is rotated, its bones' local_matrix will remember original
# rotation. Thus we don't want a bone's matrix relative to armature, but
# relative to the root bone of the armature.


def process_bone(
    f_model: SM64Model,
    bone_name,
    obj,
    armature_obj,
    last_translate_name,
    last_rotate_name,
    last_deform_name,
    parent_transform_node,
    material_overrides,
    name_prefix,
    geolayout,
    geolayout_graph,
    info_dict,
    convert_texture_data,
):
    bone = armature_obj.data.bones[bone_name]
    bone_props: SM64_BoneProperties = bone.fast64.sm64

    material_overrides = copy.copy(material_overrides)

    if bone_props.geo_cmd == "Ignore":
        return

    # Get translate
    if last_translate_name is not None:
        translateParent = armature_obj.data.bones[last_translate_name]
        translate = (translateParent.matrix_local.inverted() @ bone.matrix_local).decompose()[0]
    else:
        translateParent = None
        translate = bone.matrix_local.decompose()[0]

    zero_translation: bool = isZeroTranslation(translate)

    # Get rotate
    if last_rotate_name is not None:
        rotateParent = armature_obj.data.bones[last_rotate_name]
        rotate = (rotateParent.matrix_local.inverted() @ bone.matrix_local).decompose()[1]
    else:
        rotateParent = None
        rotate = bone.matrix_local.decompose()[1]

    zero_rotation: bool = isZeroRotation(rotate)

    has_dl = True

    external_dl = bone_props.external_dl if bone_props.use_external_dL else None

    if bone_props.geo_cmd == "Custom":
        node: CustomNode = bone_props.custom_cmd.get_node(translate, rotate, int(bone_props.draw_layer), external_dl)
        if node.translate:
            last_rotate_name = bone_name
        if node.rotate:
            last_rotate_name = bone_name
    elif bone_props.is_animatable():
        node = DisplayListWithOffsetNode(int(bone_props.draw_layer), has_dl, translate, external_dl)
        last_translate_name = bone_name
    elif bone_props.geo_cmd == "Function":
        node = bone_props.function.get_node(bone)
        if bone.children:
            raise PluginError(
                "Function bones cannot have children. They instead affect the next sibling bone in alphabetical order."
            )
    elif bone_props.geo_cmd == "HeldObject":
        if bone_props.function.func == "":
            raise PluginError(f"Held object bone {bone_name} function value is empty.")
        node = HeldObjectNode(bone_props.function.param, bone_props.function.func, translate)
    elif bone_props.geo_cmd == "Switch":
        # This is done so we can easily calculate transforms
        # of switch options.
        if bone_props.function.func == "":
            raise PluginError(f"Switch bone {bone_name} function value is empty.")
        param = bone_props.function.param if bone_props.manual_paramter else len(bone_props.switch_options) + 1
        node = SwitchNode(bone_props.function.func, param, bone_name)
        processSwitchBoneMatOverrides(material_overrides, bone)
    elif bone_props.geo_cmd == "DefineVariants":
        node = DefineNode()
        #processSwitchBoneMatOverrides(material_overrides, bone)
    elif bone_props.geo_cmd == "Start":
        node = StartNode()
    elif bone_props.geo_cmd == "TranslateRotate":
        draw_layer = int(bone_props.draw_layer)
        node = TranslateRotateNode(draw_layer, has_dl, translate, rotate, external_dl)
        last_translate_name = bone_name
        last_rotate_name = bone_name
    elif bone_props.geo_cmd == "Translate":
        node = TranslateNode(int(bone_props.draw_layer), has_dl, translate, external_dl)
        last_translate_name = bone_name
    elif bone_props.geo_cmd == "Rotate":
        node = RotateNode(int(bone_props.draw_layer), has_dl, rotate, external_dl)
        last_rotate_name = bone_name
    elif bone_props.geo_cmd == "Billboard":
        node = BillboardNode(int(bone_props.draw_layer), has_dl, translate, external_dl)
        last_translate_name = bone_name
    elif bone_props.geo_cmd == "DisplayList":
        if not armature_obj.data.bones[bone_name].use_deform:
            raise PluginError(
                f"Display List (0x15) {bone_name} must be a deform bone. Make sure deform is checked in bone properties."
            )
        node = DisplayListNode(int(bone_props.draw_layer))
    elif bone_props.geo_cmd == "Scale":
        node = ScaleNode(int(bone_props.draw_layer), bone_props.scale, has_dl, external_dl)
    else:
        raise PluginError(f"Invalid geometry command: {bone_props.geo_cmd}")

    transform_node = TransformNode(node)
    additional_nodes = []

    if node.has_dl and not getattr(node, "dlRef", False):
        tri_converter_info = TriangleConverterInfo(
            obj,
            armature_obj.data,
            f_model.f3d,
            mathutils.Matrix.Scale(bpy.context.scene.fast64.sm64.blender_to_sm64_scale, 4)
            @ bone.matrix_local.inverted(),
            info_dict,
        )

        fMeshes, fSkinnedMeshes, used_draw_layers = save_model_given_vertex_group(
            f_model,
            obj,
            bone.name,
            last_deform_name,
            armature_obj,
            material_overrides,
            name_prefix,
            info_dict,
            convert_texture_data,
            tri_converter_info,
            "sm64",
        )

        if not fMeshes and not fSkinnedMeshes:
            node.has_dl = False
            transform_node.skinnedWithoutDL = used_draw_layers is not None
            if used_draw_layers is not None:
                last_deform_name = bone_name
            parent_transform_node.children.append(transform_node)
            transform_node.parent = parent_transform_node
        else:
            last_deform_name = bone_name
            if not bone.use_deform:
                raise PluginError(
                    f"{bone.name} has vertices in its vertex group but is not set to deformable. \
                    Make sure to enable deform on this bone."
                )
            for draw_layer, f_mesh in fMeshes.items():
                draw_layer = int(draw_layer)  # IMPORTANT, otherwise 1 and '1' will be considered separate keys
                if node.DLmicrocode is not None:
                    print("Adding additional node from layer " + str(draw_layer))
                    additionalNode = (
                        DisplayListNode(draw_layer)
                        if not isinstance(node, BillboardNode)
                        else BillboardNode(draw_layer, True, [0, 0, 0])
                    )
                    additionalNode.DLmicrocode = f_mesh.draw
                    additionalNode.fMesh = f_mesh
                    additional_transform_node = TransformNode(additionalNode)
                    additional_nodes.append(additional_transform_node)
                else:
                    print("Adding node from layer " + str(draw_layer))
                    # Setting draw_layer on construction is useless?
                    node.drawLayer = draw_layer
                    node.DLmicrocode = f_mesh.draw
                    node.fMesh = f_mesh  # Used for material override switches

                    parent_transform_node.children.append(transform_node)
                    transform_node.parent = parent_transform_node

            for draw_layer, f_skinned_mesh in fSkinnedMeshes.items():
                print("Adding skinned mesh node.")
                transform_node = addSkinnedMeshNode(
                    armature_obj, bone_name, f_skinned_mesh, transform_node, parent_transform_node, int(draw_layer)
                )

            for additional_transform_node in additional_nodes:
                transform_node.children.append(additional_transform_node)
                additional_transform_node.parent = transform_node
    else:
        parent_transform_node.children.append(transform_node)
        transform_node.parent = parent_transform_node

    if isinstance(transform_node.node, SwitchNode):
        if len(bone.children) == 0:
            raise PluginError(f'Switch bone "{bone.name}" must have child bones with geometry attached.')
        next_start_node = TransformNode(StartNode())
        transform_node.children.append(next_start_node)
        next_start_node.parent = transform_node

        children_names = sorted([bone.name for bone in bone.children])
        for name in children_names:
            process_bone(
                f_model,
                name,
                obj,
                armature_obj,
                last_translate_name,
                last_rotate_name,
                last_deform_name,
                next_start_node,
                material_overrides,
                name_prefix,
                geolayout,
                geolayout_graph,
                info_dict,
                convert_texture_data,
            )

        bone = armature_obj.data.bones[bone_name]
        for switch_index in range(len(bone_props.switch_options)):
            switch_option = bone_props.switch_options[switch_index]
            if switch_option.switch_type == "Mesh":
                option_armature = switch_option.get_option_obj(armature_obj)
                option_obj = switch_option.get_mesh_obj()

                if option_armature in geolayout_graph.secondaryGeolayouts:
                    option_geolayout = geolayout_graph.secondaryGeolayouts[option_armature]
                    geolayout_graph.addJumpNode(transform_node, geolayout, option_geolayout)
                    continue

                # Armature doesn't matter here since node is not based off bone
                option_geolayout = geolayout_graph.addGeolayout(
                    option_armature, name_prefix + "_" + option_armature.name
                )
                geolayout_graph.addJumpNode(transform_node, geolayout, option_geolayout)

                if not zero_rotation or not zero_translation:
                    start_node = TransformNode(TranslateRotateNode(1, False, translate, rotate))
                else:
                    start_node = TransformNode(StartNode())
                option_geolayout.nodes.append(start_node)

                children_names = sorted(find_start_bones(option_armature))
                for name in children_names:
                    process_bone(
                        f_model,
                        name,
                        option_obj,
                        option_armature,
                        None,
                        None,
                        None,
                        start_node,
                        material_overrides,
                        option_geolayout.name + "_" + name,
                        option_geolayout,
                        geolayout_graph,
                        getInfoDict(option_obj),
                        convert_texture_data,
                    )
                return
            if switch_option.switch_type == "Material":
                material = switch_option.material_override
                if switch_option.override_draw_layer:
                    draw_layer = int(switch_option.draw_layer)
                else:
                    draw_layer = None
                if switch_option.material_override_type == "Specific":
                    specific_material = tuple([matPtr.material for matPtr in switch_option.specific_override_array])
                else:
                    specific_material = tuple([matPtr.material for matPtr in switch_option.specific_ignore_array])
            else:
                material = None
                specific_material = None
                draw_layer = int(switch_option.draw_layer)

            texDimensions = getTexDimensions(material) if material is not None else None
            overrideNode = TransformNode(
                SwitchOverrideNode(
                    material, specific_material, draw_layer, switch_option.material_override_type, texDimensions
                )
            )
            overrideNode.parent = transform_node
            transform_node.children.append(overrideNode)
    else: # see generate_switch_options() for explanation.
        # Handle child nodes
        # nonDeformTransformData should be modified to be sent to children,
        # otherwise it should not be modified for parent.
        # This is so it can be used for siblings.
        children_names = sorted([bone.name for bone in bone.children])
        for name in children_names:
            process_bone(
                f_model,
                name,
                obj,
                armature_obj,
                last_translate_name,
                last_rotate_name,
                last_deform_name,
                transform_node,
                material_overrides,
                name_prefix,
                geolayout,
                geolayout_graph,
                info_dict,
                convert_texture_data,
            )


def processSwitchBoneMatOverrides(material_overrides, switchBone):
    bone_props = switchBone.fast64.sm64
    for switch_option in bone_props.switch_options:
        if switch_option.switch_type != "Material":
            continue
        if switch_option.material_override is None:
            raise PluginError(
                f"Error: On switch bone {switchBone.name}, a switch option is a Material Override, but no material is provided."
            )
        if switch_option.material_override_type == "Specific":
            if any(item is None for item in switch_option.specific_override_array):
                raise PluginError(
                    f"Error: On switch bone {switchBone.name}, a switch option has a material override field that is None."
                )
            specific_material = tuple([matPtr.material for matPtr in switch_option.specific_override_array])
        else:
            if any(item is None for item in switch_option.specific_ignore_array):
                raise PluginError(
                    f"Error: On switch bone {switchBone.name}, a switch option has a material ignore field that is None."
                )
            specific_material = tuple([matPtr.material for matPtr in switch_option.specific_ignore_array])

        material_overrides.append(
            (switch_option.material_override, specific_material, switch_option.material_override_type)
        )


def getGroupIndex(vert, armature_obj, obj):
    actualGroups = []
    belowLimitGroups = []
    nonBoneGroups = []
    for group in vert.groups:
        group_name = getGroupNameFromIndex(obj, group.group)
        if group_name is not None:
            if group_name in armature_obj.data.bones:
                if group.weight > 0.4:
                    actualGroups.append(group)
                else:
                    belowLimitGroups.append(group_name)
            else:
                nonBoneGroups.append(group_name)

    if len(actualGroups) == 0:
        highlightWeightErrors(obj, [vert], "VERT")
        raise VertexWeightError(
            f"All vertices must be part of a vertex group, be non-trivially weighted (> 0.4), \
            and the vertex group must correspond to a bone in the armature.\n\
            Groups of the bad vert that don't correspond to a bone: {str(nonBoneGroups)}. \
            If a vert is supposed to belong to this group then either a bone is missing or you have the wrong group.\n \
            Groups of the bad vert below weight limit: {str(belowLimitGroups)}. \
            If a vert is supposed to belong to one of these groups then make sure to increase its weight."
        )
    vertGroup = actualGroups[0]
    significantWeightGroup = None
    for group in actualGroups:
        if group.weight > 0.5:
            if significantWeightGroup is None:
                significantWeightGroup = group
                continue
            highlightWeightErrors(obj, [vert], "VERT")
            raise VertexWeightError(
                f"A vertex was found that was significantly weighted to multiple groups. \
                Make sure each vertex only belongs to one group whose weight is greater than 0.5. \
                ({getGroupNameFromIndex(obj, group.group)}, \
                {getGroupNameFromIndex(obj, significantWeightGroup.group)})"
            )
        if group.weight > vertGroup.weight:
            vertGroup = group

    return vertGroup.group


def checkIfFirstNonASMNode(childNode):
    index = childNode.parent.children.index(childNode)
    if index == 0:
        return True
    while index > 0 and (
        isinstance(childNode.parent.children[index - 1].node, FunctionNode)
        or not childNode.parent.children[index - 1].skinned
    ):
        index -= 1
    return index == 0


# parent connects child node to itself
# skinned node handled by child

# A skinned mesh node should be before a mesh node.
# However, other transform nodes may exist in between two mesh nodes,
# So the skinned mesh node must be inserted before any of those transforms.
# Sibling mesh nodes thus cannot share the same transform nodes before it
# If they are both deform.
# Additionally, ASM nodes should count as modifiers for other nodes if
# they precede them
def addSkinnedMeshNode(armature_obj, bone_name, skinned_mesh, transform_node, parent_node, draw_layer):
    # Add node to its immediate parent
    transform_node.skinned = True

    # Get skinned node
    bone = armature_obj.data.bones[bone_name]
    skinned_node = DisplayListNode(draw_layer)
    skinned_node.fMesh = skinned_mesh
    skinned_node.DLmicrocode = skinned_mesh.draw
    skinned_transform_node = TransformNode(skinned_node)

    # Ascend heirarchy until reaching first node before a deform parent.
    # We duplicate the hierarchy along the way to possibly use later.
    highestChildNode = transform_node
    transformNodeCopy = TransformNode(copy.copy(transform_node.node))
    transformNodeCopy.parent = parent_node
    highestChildCopy = transformNodeCopy
    isFirstChild = True
    hasNonDeform0x13Command = False
    acrossSwitchNode = False
    while highestChildNode.parent and not (
        highestChildNode.parent.node.has_dl or highestChildNode.parent.skinnedWithoutDL
    ):  # empty 0x13 command?
        isFirstChild &= checkIfFirstNonASMNode(highestChildNode)
        hasNonDeform0x13Command |= isinstance(highestChildNode.parent.node, DisplayListWithOffsetNode)

        acrossSwitchNode |= isinstance(highestChildNode.parent.node, SwitchNode)

        highestChildNode = highestChildNode.parent
        highestChildCopyParent = TransformNode(copy.copy(highestChildNode.node))
        highestChildCopyParent.children = [highestChildCopy]
        highestChildCopy.parent = highestChildCopyParent
        highestChildCopy = highestChildCopyParent
    if highestChildNode.parent is None:
        raise PluginError('Issue with "' + bone_name + '": Deform parent bone not found for skinning.')

    # Otherwise, remove the transform_node from the parent and
    # duplicate the node heirarchy up to the last deform parent.
    # Add the skinned node first to the last deform parent,
    # then add the duplicated node hierarchy afterward.
    if highestChildNode != transform_node:
        if not isFirstChild:
            if hasNonDeform0x13Command:
                raise PluginError(
                    f"Error with {bone_name}: You cannot have more that one child skinned mesh connected to a parent skinned mesh with a non deform 0x13 bone in between. Try removing any unnecessary non-deform bones."
                )
            if acrossSwitchNode:
                raise PluginError(
                    f"Error with {bone_name}: You cannot skin across a switch node with more than one child."
                )

            # Remove transform_node
            parent_node.children.remove(transform_node)
            transform_node.parent = None

            # copy hierarchy, along with any preceding Function commands
            highestChildIndex = highestChildNode.parent.children.index(highestChildNode)
            precedingFunctionCmds = []
            while (
                highestChildIndex > 0
                and type(highestChildNode.parent.children[highestChildIndex - 1].node) is FunctionNode
            ):

                precedingFunctionCmds.insert(0, copy.deepcopy(highestChildNode.parent.children[highestChildIndex - 1]))
                highestChildIndex -= 1

            # add skinned mesh node
            highestChildCopy.parent = highestChildNode.parent
            highestChildCopy.parent.children.append(skinned_transform_node)
            skinned_transform_node.parent = highestChildCopy.parent

            # add Function cmd nodes
            for asmCmdNode in precedingFunctionCmds:
                highestChildCopy.parent.children.append(asmCmdNode)

            # add heirarchy to parent
            highestChildCopy.parent.children.append(highestChildCopy)

            transform_node = transformNodeCopy
        else: # Hierarchy with first child
            nodeIndex = highestChildNode.parent.children.index(highestChildNode)
            while nodeIndex > 0 and type(highestChildNode.parent.children[nodeIndex - 1].node) is FunctionNode:
                nodeIndex -= 1
            highestChildNode.parent.children.insert(nodeIndex, skinned_transform_node)
            skinned_transform_node.parent = highestChildNode.parent
    else: # Immediate child
        nodeIndex = parent_node.children.index(transform_node)
        parent_node.children.insert(nodeIndex, skinned_transform_node)
        skinned_transform_node.parent = parent_node

    return transform_node


def getAncestorGroups(parent_group, vertex_group, armature_obj, obj):
    if parent_group is None:
        return []
    ancestorBones = []
    processingBones = [armature_obj.data.bones[vertex_group]]
    while len(processingBones) > 0:
        currentBone = processingBones[0]
        processingBones = processingBones[1:]

        ancestorBones.append(currentBone)
        processingBones.extend(currentBone.children)

    currentBone = armature_obj.data.bones[vertex_group].parent
    while currentBone is not None and currentBone.name != parent_group:
        ancestorBones.append(currentBone)
        currentBone = currentBone.parent
    ancestorBones.append(armature_obj.data.bones[parent_group])

    return [getGroupIndexFromname(obj, bone.name) for bone in armature_obj.data.bones if bone not in ancestorBones]

@dataclass
class SimpleSkinnedFace:
    bFace: bpy.types.Mesh
    loopsInGroup: bpy.types.Mesh
    loopsNotInGroup: bpy.types.Mesh

def save_face_given_vertex_group(
    ancestorGroups,
    groupFaces,
    used_draw_layers,
    skinned_faces,
    obj: bpy.types.Object,
    armature_obj,
    parent_group: None | str,
    parentGroupIndex,
    vertex_group: str,
    currentGroupIndex,
    face,
    drawLayerField,
):
    mesh = obj.data

    loopsInGroup = []
    loopsNotInGroup = []
    isChildSkinnedFace = False

    # loop is interpreted as face + loop index
    for i in range(3):
        vertGroupIndex = getGroupIndex(mesh.vertices[face.vertices[i]], armature_obj, obj)
        if vertGroupIndex not in ancestorGroups:
            ancestorGroups[vertGroupIndex] = getAncestorGroups(parent_group, vertex_group, armature_obj, obj)

        if vertGroupIndex == currentGroupIndex:
            loopsInGroup.append((face, mesh.loops[face.loops[i]]))
        elif vertGroupIndex == parentGroupIndex:
            loopsNotInGroup.append((face, mesh.loops[face.loops[i]]))
        elif vertGroupIndex not in ancestorGroups[vertGroupIndex]:
            # Only want to handle skinned faces connected to parent
            isChildSkinnedFace = True
            break
        else:
            highlightWeightErrors(obj, [face], "FACE")
            raise VertexWeightError(
                f"Error with {vertex_group}: Verts attached to one bone can not be attached to any of its ancestor or sibling bones besides its first immediate deformable parent bone. For example, a foot vertex can be connected to a leg vertex, but a foot vertex cannot be connected to a thigh vertex."
            )

    material = obj.material_slots[face.material_index].material
    draw_layer = int(getattr(material.f3d_mat.draw_layer, drawLayerField))

    if isChildSkinnedFace:
        used_draw_layers.add(draw_layer)
        return

    if len(loopsNotInGroup) == 0:
        if draw_layer not in groupFaces:
            groupFaces[draw_layer] = {}
        drawLayerFaces = groupFaces[draw_layer]
        if face.material_index not in drawLayerFaces:
            drawLayerFaces[face.material_index] = []
        drawLayerFaces[face.material_index].append(face)
    else:
        if draw_layer not in skinned_faces:
            skinned_faces[draw_layer] = {}
        drawLayerSkinnedFaces = skinned_faces[draw_layer]
        if face.material_index not in drawLayerSkinnedFaces:
            drawLayerSkinnedFaces[face.material_index] = []
        drawLayerSkinnedFaces[face.material_index].append(SimpleSkinnedFace(face, loopsInGroup, loopsNotInGroup))


# returns fMeshes, fSkinnedMeshes, makeLastDeformBone
def save_model_given_vertex_group(
    f_model: SM64Model,
    obj: bpy.types.Object,
    vertex_group: str,
    parent_group: None | str,
    armature_obj,
    material_overrides,
    name_prefix,
    info_dict,
    convert_texture_data,
    tri_converter_info,
    drawLayerField,
):
    # TODO: Implement last_material_name optimization
    last_material_name = None

    mesh = obj.data
    currentGroupIndex = getGroupIndexFromname(obj, vertex_group)
    parentGroupIndex = getGroupIndexFromname(obj, parent_group) if parent_group is not None else -1

    vertex_indices = [
        vert.index for vert in obj.data.vertices if getGroupIndex(vert, armature_obj, obj) == currentGroupIndex
    ]
    if len(vertex_indices) == 0:
        print(f"No vert indices in {vertex_group}")
        return None, None, None

    transformMatrix = mathutils.Matrix.Scale(bpy.context.scene.fast64.sm64.blender_to_sm64_scale, 4)
    if parent_group is None:
        parentMatrix = transformMatrix
    else:
        parentBone = armature_obj.data.bones[parent_group]
        parentMatrix = transformMatrix @ parentBone.matrix_local.inverted()

    groupFaces: dict[int : dict[int:list]] = {}  # draw layer : {material_index : [faces]}
    skinned_faces: dict[int : dict[int:list]] = {}  # draw layer : {material_index : [skinned faces]}
    ancestorGroups = {}  # vertex_group : ancestor list

    handled_faces = []
    used_draw_layers = set()

    for vertex_index in vertex_indices:
        if vertex_index not in info_dict.vert:
            continue
        for face in info_dict.vert[vertex_index]:
            if face in handled_faces:  # Ignore repeated faces
                continue
            handled_faces.append(face)
            save_face_given_vertex_group(
                ancestorGroups,
                groupFaces,
                used_draw_layers,
                skinned_faces,
                obj,
                armature_obj,
                parent_group,
                parentGroupIndex,
                vertex_group,
                currentGroupIndex,
                face,
                drawLayerField,
            )

    if len(groupFaces) == 0 and len(skinned_faces) == 0:
        print(f"No faces in {vertex_group}")
        return None, None, used_draw_layers

    # Save skinned mesh
    fMeshes = {}
    fSkinnedMeshes = {}
    for draw_layer, materialFaces in skinned_faces.items():

        meshName = getFMeshName(vertex_group, name_prefix, draw_layer, False)
        checkUniqueBoneNames(f_model, meshName, vertex_group)
        skinnedMeshName = getFMeshName(vertex_group, name_prefix, draw_layer, True)
        checkUniqueBoneNames(f_model, skinnedMeshName, vertex_group)

        f_mesh, f_skinned_mesh = saveSkinnedMeshByMaterial(
            materialFaces,
            f_model,
            meshName,
            skinnedMeshName,
            obj,
            parentMatrix,
            vertex_group,
            draw_layer,
            convert_texture_data,
            tri_converter_info,
        )
    
        fSkinnedMeshes[draw_layer] = f_skinned_mesh
        fMeshes[draw_layer] = f_mesh

        f_model.meshes[skinnedMeshName] = fSkinnedMeshes[draw_layer]
        f_model.meshes[meshName] = fMeshes[draw_layer]

        if draw_layer not in groupFaces:
            fMeshes[draw_layer].draw.commands.append(SPEndDisplayList())

    # Save unskinned mesh
    for draw_layer, materialFaces in groupFaces.items():
        if draw_layer not in fMeshes:
            f_mesh = f_model.addMesh(vertex_group, name_prefix, draw_layer, False, None)
            fMeshes[draw_layer] = f_mesh

        for material_index, bFaces in materialFaces.items():
            material = obj.material_slots[material_index].material
            checkForF3dMaterialInFaces(obj, material)
            fMaterial, texDimensions = saveOrGetF3DMaterial(material, f_model, obj, draw_layer, convert_texture_data)
            if fMaterial.isTexLarge[0] or fMaterial.isTexLarge[1]:
                currentGroupIndex = saveMeshWithLargeTexturesByFaces(
                    material,
                    bFaces,
                    f_model,
                    fMeshes[draw_layer],
                    obj,
                    draw_layer,
                    convert_texture_data,
                    None,
                    tri_converter_info,
                    None,
                    None,
                    last_material_name,
                )
            else:
                saveMeshByFaces(
                    material,
                    bFaces,
                    f_model,
                    fMeshes[draw_layer],
                    obj,
                    draw_layer,
                    convert_texture_data,
                    None,
                    tri_converter_info,
                    None,
                    None,
                    last_material_name,
                )

        fMeshes[draw_layer].draw.commands.append(SPEndDisplayList())

    # Must be done after all geometry saved
    for (material, specific_material, override_type) in material_overrides:
        for draw_layer, f_mesh in fMeshes.items():
            saveOverrideDraw(
                obj, f_model, material, specific_material, override_type, f_mesh, draw_layer, convert_texture_data
            )
        for draw_layer, f_mesh in fSkinnedMeshes.items():
            saveOverrideDraw(
                obj, f_model, material, specific_material, override_type, f_mesh, draw_layer, convert_texture_data
            )

    return fMeshes, fSkinnedMeshes, used_draw_layers


def saveOverrideDraw(
    obj: bpy.types.Object,
    f_model: FModel,
    material: bpy.types.Material,
    specific_material: tuple[bpy.types.Material],
    override_type: str,
    f_mesh: FMesh,
    draw_layer: int,
    convert_texture_data: bool,
):
    fOverrideMat, texDimensions = saveOrGetF3DMaterial(material, f_model, obj, draw_layer, convert_texture_data)
    overrideIndex = str(len(f_mesh.drawMatOverrides))
    if (material, specific_material, override_type) in f_mesh.drawMatOverrides:
        overrideIndex = f_mesh.drawMatOverrides[(material, specific_material, override_type)].name[-1]
    meshMatOverride = GfxList(
        f_mesh.name + "_mat_override_" + toAlnum(material.name) + "_" + overrideIndex, GfxListTag.Draw, f_model.DLFormat
    )
    meshMatOverride.commands = [copy.copy(cmd) for cmd in f_mesh.draw.commands]
    f_mesh.drawMatOverrides[(material, specific_material, override_type)] = meshMatOverride
    prev_material = None
    last_replaced = None
    command_index = 0

    def find_material_from_jump_cmd(
        material_list: tuple[tuple[bpy.types.Material, str, FAreaData], tuple[FMaterial, Tuple[int, int]]],
        dl_jump: SPDisplayList,
    ):
        if dl_jump.displayList.tag == GfxListTag.Geometry:
            return None, None
        for mat in material_list:
            fmaterial = mat[1][0]
            bpy_material = mat[0][0]
            if dl_jump.displayList.tag == GfxListTag.MaterialRevert and fmaterial.revert == dl_jump.displayList:
                return bpy_material, fmaterial
            elif fmaterial.material == dl_jump.displayList:
                return bpy_material, fmaterial
        return None, None

    while command_index < len(meshMatOverride.commands):
        command = meshMatOverride.commands[command_index]
        if not isinstance(command, SPDisplayList):
            command_index += 1
            continue
        # get the material referenced, and then check if it should be overriden
        # a material override will either have a list of mats it overrides, or a mask of mats it doesn't based on type
        bpy_material, fmaterial = find_material_from_jump_cmd(f_model.getAllMaterials().items(), command)
        if override_type == "Specific" and bpy_material in specific_material:
            shouldModify = True
        elif override_type == "All" and bpy_material not in specific_material:
            shouldModify = True
        else:
            shouldModify = False

        # replace the material load if necessary
        # if we replaced the previous load with the same override, then remove the cmd to optimize DL
        if command.displayList.tag == GfxListTag.Material:
            curMaterial = fmaterial
            if shouldModify:
                last_replaced = fmaterial
                curMaterial = fOverrideMat
                command.displayList = fOverrideMat.material
            # remove cmd if it is a repeat load
            if prev_material == curMaterial:
                meshMatOverride.commands.pop(command_index)
                command_index -= 1
                # if we added a revert for our material redundant load, remove that as well
                prevIndex = command_index - 1
                prev_command = meshMatOverride.commands[prevIndex]
                if (
                    prevIndex > 0
                    and isinstance(prev_command, SPDisplayList)
                    and prev_command.displayList == curMaterial.revert
                ):
                    meshMatOverride.commands.pop(prevIndex)
                    command_index -= 1
            # update the last loaded material
            prev_material = curMaterial

        # replace the revert if the override has a revert, otherwise remove the command
        if command.displayList.tag == GfxListTag.MaterialRevert and shouldModify:
            if fOverrideMat.revert is not None:
                command.displayList = fOverrideMat.revert
            else:
                meshMatOverride.commands.pop(command_index)
                command_index -= 1

        if not command.displayList.tag == GfxListTag.Geometry:
            command_index += 1
            continue
        # If the previous command was a revert we added, remove it. All reverts must be followed by a load
        prev_index = command_index - 1
        prev_command = meshMatOverride.commands[prev_index]
        if (
            prev_index > 0
            and isinstance(prev_command, SPDisplayList)
            and prev_command.displayList == fOverrideMat.revert
        ):
            meshMatOverride.commands.pop(prev_index)
            command_index -= 1
        # If the override material has a revert and the original material didn't, insert a revert after this command.
        # This is needed to ensure that override materials that need a revert get them.
        # Reverts are only needed if the next command is a different material load
        if (
            last_replaced
            and last_replaced.revert is None
            and fOverrideMat.revert is not None
            and prev_material == fOverrideMat
        ):
            next_command = meshMatOverride.commands[command_index + 1]
            if (
                isinstance(next_command, SPDisplayList)
                and next_command.displayList.tag == GfxListTag.Material
                and next_command.displayList != prev_material.material
            ) or (isinstance(next_command, SPEndDisplayList)):
                meshMatOverride.commands.insert(command_index + 1, SPDisplayList(fOverrideMat.revert))
                command_index += 1
        # iterate to the next cmd
        command_index += 1


def findVertIndexInBuffer(loop, buffer, loop_dict):
    i = 0
    for material_index, vertex_data in buffer:
        for f3d_vertex in vertex_data:
            if f3d_vertex == loop_dict[loop]:
                return i
            i += 1
    # print("Can't find " + str(loop))
    return -1


def convertVertDictToArray(vertDict):
    data = []
    matRegions = {}
    for material_index, vertex_data in vertDict:
        start = len(data)
        data.extend(vertex_data)
        end = len(data)
        matRegions[material_index] = (start, end)
    return data, matRegions


# This collapses similar loops together IF they are in the same material.
def splitSkinnedFacesIntoTwoGroups(skinned_faces, f_model, obj, uv_data, draw_layer, convert_texture_data):
    in_group_vertices = []
    no_group_vertices = []

    # For selecting on error
    not_in_group_blender_vertices = []
    loop_dict = {}
    for material_index, skinnedFaceArray in skinned_faces.items():
        # These MUST be arrays (not dicts) as order is important
        material_in_group_vertices = []
        in_group_vertices.append([material_index, material_in_group_vertices])

        material_no_group_vertices = []
        no_group_vertices.append([material_index, material_no_group_vertices])

        material = obj.material_slots[material_index].material

        # Called to update f_model
        saveOrGetF3DMaterial(material, f_model, obj, draw_layer, convert_texture_data)

        exportVertexColors = isLightingDisabled(material)
        loop_convert_info = LoopConvertInfo(uv_data, obj, exportVertexColors)
        for skinnedFace in skinnedFaceArray:
            for (face, loop) in skinnedFace.loopsInGroup:
                f3d_vertex = getF3DVert(loop, face, loop_convert_info, obj.data)
                buffer_vertex = BufferVertex(f3d_vertex, None, material_index)
                if buffer_vertex not in material_in_group_vertices:
                    material_in_group_vertices.append(buffer_vertex)
                loop_dict[loop] = f3d_vertex
            for (face, loop) in skinnedFace.loopsNotInGroup:
                vert = obj.data.vertices[loop.vertex_index]
                if vert not in not_in_group_blender_vertices:
                    not_in_group_blender_vertices.append(vert)
                f3d_vertex = getF3DVert(loop, face, loop_convert_info, obj.data)
                buffer_vertex = BufferVertex(f3d_vertex, None, material_index)
                if buffer_vertex not in material_no_group_vertices:
                    material_no_group_vertices.append(buffer_vertex)
                loop_dict[loop] = f3d_vertex

    return in_group_vertices, no_group_vertices, loop_dict, not_in_group_blender_vertices


def getGroupVertCount(group):
    count = 0
    for material_index, vertex_data in group:
        count += len(vertex_data)
    return count


def saveSkinnedMeshByMaterial(
    skinned_faces: dict[int, list[SimpleSkinnedFace]],
    f_model: SM64Model,
    meshName: str,
    skinnedMeshName: str,
    obj: bpy.types.Object,
    parentMatrix: mathutils.Matrix,
    vertex_group: str,
    draw_layer: int,
    convert_texture_data: bool,
    tri_converter_info: TriangleConverterInfo,
):
    # We choose one or more loops per vert to represent a material from which
    # texDimensions can be found, since it is required for UVs.
    uv_data = obj.data.uv_layers["UVMap"].data
    in_group_vertices, not_in_group_vertices, loop_dict, not_in_group_blender_vertices = splitSkinnedFacesIntoTwoGroups(
        skinned_faces, f_model, obj, uv_data, draw_layer, convert_texture_data
    )

    notInGroupCount = getGroupVertCount(not_in_group_vertices)
    if notInGroupCount > f_model.f3d.vert_load_size - 2:
        highlightWeightErrors(obj, not_in_group_blender_vertices, "VERT")
        raise VertexWeightError(
            f"Too many connecting vertices in skinned triangles for bone '{vertex_group}'. \
            Max is {f_model.f3d.vert_load_size - 2} on parent bone, currently at {notInGroupCount}. \
            Note that a vertex with different UVs/normals/materials in connected faces will count more than once. \
            Try keeping UVs contiguous, and avoid using split normals."
        )

    # TODO: Implement last_material_name optimization
    last_material_name = None

    # Load parent group vertices
    f_skinned_mesh = FMesh(skinnedMeshName, f_model.DLFormat)

    # Load verts into buffer by material.
    # It seems like material setup must be done BEFORE triangles are drawn.
    # Because of this we cannot share verts between materials (?)
    cur_index = 0
    for material_index, vertex_data in not_in_group_vertices:
        material = obj.material_slots[material_index].material
        checkForF3dMaterialInFaces(obj, material)
        f3d_material = material.f3d_mat

        if f3d_material.rdp_settings.set_rendermode:
            draw_layer_key = draw_layer
        else:
            draw_layer_key = None

        materialKey = (material, draw_layer_key, f_model.global_data.getCurrentAreaKey(material))
        fMaterial, texDimensions = f_model.getMaterialAndHandleShared(materialKey)

        skinned_tri_group = f_skinned_mesh.tri_group_new(fMaterial)
        f_skinned_mesh.draw.commands.append(SPDisplayList(fMaterial.material))
        f_skinned_mesh.draw.commands.append(SPDisplayList(skinned_tri_group.triList))
        skinned_tri_group.triList.commands.append(
            SPVertex(
                skinned_tri_group.vertexList, len(skinned_tri_group.vertexList.vertices), len(vertex_data), cur_index
            )
        )
        cur_index += len(vertex_data)

        for buffer_vertex in vertex_data:
            skinned_tri_group.vertexList.vertices.append(
                convertVertexData(
                    obj.data,
                    buffer_vertex.f3dVert.position,
                    buffer_vertex.f3dVert.uv,
                    buffer_vertex.f3dVert.stOffset,
                    buffer_vertex.f3dVert.getColorOrNormal(),
                    texDimensions,
                    parentMatrix,
                    isTexturePointSampled(material),
                    isLightingDisabled(material),
                )
            )

        skinned_tri_group.triList.commands.append(SPEndDisplayList())
        if fMaterial.revert is not None:
            f_skinned_mesh.draw.commands.append(SPDisplayList(fMaterial.revert))

    # End skinned mesh vertices.
    f_skinned_mesh.draw.commands.append(SPEndDisplayList())

    f_mesh = FMesh(meshName, f_model.DLFormat)

    # Load current group vertices, then draw commands by material
    existing_vert_data, mat_region_dict = convertVertDictToArray(not_in_group_vertices)

    for material_index, skinnedFaceArray in skinned_faces.items():
        material = obj.material_slots[material_index].material
        faces = [skinnedFace.bFace for skinnedFace in skinnedFaceArray]
        fMaterial, texDimensions = saveOrGetF3DMaterial(material, f_model, obj, draw_layer, convert_texture_data)
        if fMaterial.isTexLarge[0] or fMaterial.isTexLarge[1]:
            saveMeshWithLargeTexturesByFaces(
                material,
                faces,
                f_model,
                f_mesh,
                obj,
                draw_layer,
                convert_texture_data,
                None,
                tri_converter_info,
                copy.deepcopy(existing_vert_data),
                copy.deepcopy(mat_region_dict),
                last_material_name,
            )
        else:
            saveMeshByFaces(
                material,
                faces,
                f_model,
                f_mesh,
                obj,
                draw_layer,
                convert_texture_data,
                None,
                tri_converter_info,
                copy.deepcopy(existing_vert_data),
                copy.deepcopy(mat_region_dict),
                last_material_name,
            )

    return f_mesh, f_skinned_mesh


def sm64_geo_writer_register():
    bpy.types.Scene.geoIsSegPtr = bpy.props.BoolProperty(name="Is Segmented Address")


def sm64_geo_writer_unregister():
    del bpy.types.Scene.geoIsSegPtr
