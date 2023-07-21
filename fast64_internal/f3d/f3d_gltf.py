from dataclasses import dataclass
import bpy
from ..gltf_utility import FlagAttrToGlTFInfo, appendGlTF2Extension, blenderColorToGlTFColor, flagAttrsToGlTFArray
from .f3d_writer import getRenderModeFlagList
from ..utility import getObjDirectionVec
from .f3d_material import all_combiner_uses

fast64_extension_name = "EXT_fast64"

from io_scene_gltf2.io.com import gltf2_io
from io_scene_gltf2.io.com.gltf2_io_constants import TextureFilter, TextureWrap
from io_scene_gltf2.blender.exp.material.extensions.gltf2_blender_image import ExportImage
from io_scene_gltf2.blender.exp.material.gltf2_blender_gather_image import (
    __gather_name,
    __gather_uri,
    __gather_original_uri,
    __gather_buffer_view,
    __make_image,
)
from io_scene_gltf2.blender.exp.gltf2_blender_gather_sampler import __sampler_by_value
from io_scene_gltf2.blender.exp.gltf2_blender_gather_cache import cached
from io_scene_gltf2.io.com.gltf2_io_extensions import Extension
import traceback


def add_fast64_f3d_light_to_list(blenderLight: bpy.types.Light, lights: list[dict[str, list[float]]]):
    if blenderLight is None:
        return

    for obj in bpy.context.scene.objects:
        if obj.data == blenderLight.original:
            lights.append({"color": list(blenderLight.color), "direction": list(getObjDirectionVec(obj, True))})


def blender_image_to_gltf2_image(extension, bl_image, f3d_tex, export_settings):
    image_data = ExportImage.from_blender_image(bl_image)
    mime_type = "image/png"
    name = __gather_name(image_data, export_settings)
    buffer_view, factor_buffer_view = __gather_buffer_view(image_data, mime_type, name, export_settings)
    buffer_view = None  # FIX
    if image_data.original is None:
        uri, factor_uri = __gather_uri(image_data, mime_type, name, export_settings)
    else:
        # Retrieve URI relative to exported glTF files
        uri = __gather_original_uri(image_data.original.filepath, export_settings)
        # In case we can't retrieve image (for example packed images, with original moved)
        # We don't create invalid image without uri
        factor_uri = None
        if uri is None:
            return None

    image = __make_image(buffer_view, None, None, mime_type, name, uri, export_settings)

    return image


def sampler_from_f3d(extension, f3dMat, f3d_tex, export_settings):
    use_nearest = f3dMat.rdp_settings.g_mdsft_text_filt == "G_TF_POINT"
    mag_filter = TextureFilter.Nearest if use_nearest else TextureFilter.Linear
    min_filter = TextureFilter.NearestMipmapNearest if use_nearest else TextureFilter.LinearMipmapLinear

    clampS = f3d_tex.S.clamp
    clampT = f3d_tex.T.clamp
    mirrorS = f3d_tex.S.mirror
    mirrorT = f3d_tex.T.mirror
    maskS = f3d_tex.S.mask
    maskT = f3d_tex.T.mask
    shiftS = f3d_tex.S.shift
    shiftT = f3d_tex.T.shift

    wrap_s = TextureWrap.ClampToEdge if clampS else (TextureWrap.MirroredRepeat if mirrorS else TextureWrap.Repeat)
    wrap_t = TextureWrap.ClampToEdge if clampT else (TextureWrap.MirroredRepeat if mirrorT else TextureWrap.Repeat)

    sampler = __sampler_by_value(mag_filter, min_filter, wrap_s, wrap_t, export_settings)

    if sampler.extensions is None:
        sampler.extensions = {}

    extensionData = {}

    if not f3d_tex.autoprop:
        extensionData["maskS"] = maskS
        extensionData["maskT"] = maskT
        extensionData["shiftS"] = shiftS
        extensionData["shiftT"] = shiftT

    extensionData["format"] = f3d_tex.tex_format

    sampler.extensions[fast64_extension_name] = extension(
        name=fast64_extension_name, extension=extensionData, required=False
    )

    return sampler


def texture_by_value(sampler: gltf2_io.Sampler, image: gltf2_io.Image, export_settings: dict) -> gltf2_io.Texture:
    return gltf2_io.Texture(extensions={}, extras=None, name=None, sampler=sampler, source=image)


def fogToGlTF(f3dMat):
    if f3dMat.set_fog:
        return {"color": blenderColorToGlTFColor(f3dMat.fog_color), "range": list(f3dMat.fog_position)}


def textureSettingsToGlTF(f3dMat):
    textureSettingsData = {}
    if not f3dMat.scale_autoprop:
        textureSettingsData["scale"] = [f3dMat.tex_scale[0], f3dMat.tex_scale[1]]

    rdpSettings = f3dMat.rdp_settings
    if rdpSettings.g_mdsft_textlod == "G_TL_LOD":
        textureSettingsData["mipmapAmount"] = rdpSettings.num_textures_mipmapped

    return textureSettingsData


def largeTextureModeToGlTF(f3dMat):
    if f3dMat.use_large_textures:
        return {"largeTextureEdges": f3dMat.large_edges}


def lightsToGlTF(useDict, f3dMat):
    if useDict["Shade"] and f3dMat.rdp_settings.g_lighting and f3dMat.set_lights:
        lights: list[dict[str, list[float]]] = []
        ambientColor: list[float] = blenderColorToGlTFColor(f3dMat.ambient_light_color)

        if f3dMat.use_default_lighting:
            lights.append(blenderColorToGlTFColor(f3dMat.default_light_color))
            if f3dMat.set_ambient_from_light:
                ambientColor = None
        else:
            for i in range(1, 8):
                add_fast64_f3d_light_to_list(f3dMat.get(f"f3d_light{str(i)}"), lights)

        lightData = {"lights": lights}
        if ambientColor:
            lightData["ambientColor"] = ambientColor

        return lightData


def yuvConvertToGlTF(useDict, f3dMat):
    if useDict["Convert"] and f3dMat.set_k0_5:
        yuvConvertData = [f3dMat.k0, f3dMat.k1, f3dMat.k2, f3dMat.k3, f3dMat.k4, f3dMat.k5]
        return [round(value, 3) for value in yuvConvertData]


def chromaKeyToGlTF(useDict, f3dMat):
    if useDict["Key"] and f3dMat.set_key:
        return {"center": list(f3dMat.key_center), "scale": list(f3dMat.key_scale), "width": list(f3dMat.key_width)}


def primitiveColorToGlTF(useDict, f3dMat):
    if useDict["Primitive"] and f3dMat.set_prim:
        color = blenderColorToGlTFColor(f3dMat.prim_color, True)

        if f3dMat.prim_lod_min != 0 or f3dMat.prim_lod_frac != 0:
            primativeColorData = {}
            primativeColorData["minLoDRatio"] = f3dMat.prim_lod_min
            primativeColorData["loDFraction"] = f3dMat.prim_lod_frac
            primativeColorData["color"] = color
        else:
            primativeColorData = color

        return primativeColorData


def environmentColorToGlTF(useDict, f3dMat):
    if useDict["Environment"] and f3dMat.set_env:
        return blenderColorToGlTFColor(f3dMat.env_color, True)


def allColorRegistersToGlTF(useDict, f3dMat):
    return {
        "environmentColor": environmentColorToGlTF(useDict, f3dMat),
        "primativeColor": primitiveColorToGlTF(useDict, f3dMat),
        "chromaKey": chromaKeyToGlTF(useDict, f3dMat),
        "yuvConvert": yuvConvertToGlTF(useDict, f3dMat),
    }


@dataclass
class EnumAttrToGlTFInfo:
    gltfKey: str
    materialAttr: str
    default: object


# TODO: Needs better naming
def enum_attributes_to_glTF_dict(materialSettings, enumAttributesInfo: dict[EnumAttrToGlTFInfo]):
    data = {}
    for info in enumAttributesInfo:
        value = getattr(materialSettings, info.materialAttr)

        if value != info.default:
            data[info.gltfKey] = value
    return data


otherModeLAttrsToGlTF = [
    EnumAttrToGlTFInfo("alphaCompare", "g_mdsft_alpha_compare", "G_AC_NONE"),
    EnumAttrToGlTFInfo("zSourceSelection", "g_mdsft_zsrcsel", "G_ZS_PIXEL"),
]


def othermodeLToGlTF(f3dMat):
    rdpSettings = f3dMat.rdp_settings

    mode = enum_attributes_to_glTF_dict(rdpSettings, otherModeLAttrsToGlTF)
    if rdpSettings.g_mdsft_zsrcsel == "G_ZS_PRIM":
        prim_depth = rdpSettings.prim_depth
        primDepthData = {}
        primDepthData["z"] = prim_depth.z
        primDepthData["deltaZ"] = prim_depth.dz
        mode["primDepth"] = primDepthData

    # Render mode and blender
    if rdpSettings.set_rendermode:
        renderMode, colorBlender = getRenderModeFlagList(rdpSettings, f3dMat)
        if colorBlender is None:
            mode["renderMode"] = renderMode
        else:
            mode["renderMode"] = {"flags": renderMode, "blender": colorBlender}

    return mode


otherModeHAttrsToGlTF = [
    EnumAttrToGlTFInfo("colorDither", "g_mdsft_color_dither", "G_CD_ENABLE"),  # Hardware V1
    EnumAttrToGlTFInfo("alphaDither", "g_mdsft_alpha_dither", "G_AD_NOISE"),  # Hardware V2
    EnumAttrToGlTFInfo("rgbDither", "g_mdsft_rgb_dither", "G_CD_MAGICSQ"),  # Hardware V2
    EnumAttrToGlTFInfo("chromaKey", "g_mdsft_combkey", "G_CK_NONE"),
    EnumAttrToGlTFInfo("textureConvert", "g_mdsft_textconv", "G_TC_FILT"),
    EnumAttrToGlTFInfo("textureFilterType", "g_mdsft_text_filt", "G_TF_BILERP"),
    EnumAttrToGlTFInfo("textureLut", "g_mdsft_textlut", "G_TT_NONE"),
    EnumAttrToGlTFInfo("textureLoD", "g_mdsft_textlod", "G_TL_TILE"),
    EnumAttrToGlTFInfo("textureDetail", "g_mdsft_textdetail", "G_TD_CLAMP"),
    EnumAttrToGlTFInfo("perspectiveCorrection", "g_mdsft_textpersp", "G_TP_PERSP"),
    EnumAttrToGlTFInfo("cycleType", "g_mdsft_cycletype", "G_CYC_1CYCLE"),
    EnumAttrToGlTFInfo("pipelineMode", "g_mdsft_pipeline", "G_PM_1PRIMITIVE"),
]

geoModesToGlTF = [
    FlagAttrToGlTFInfo("G_ZBUFFER", "g_zbuffer"),
    FlagAttrToGlTFInfo("G_SHADE", "g_shade"),
    FlagAttrToGlTFInfo("G_CULL_FRONT", "g_cull_front"),
    FlagAttrToGlTFInfo("G_CULL_BACK", "g_cull_back"),
    FlagAttrToGlTFInfo("G_FOG", "g_fog"),
    FlagAttrToGlTFInfo("G_LIGHTING", "g_lighting"),
    FlagAttrToGlTFInfo("G_TEXTURE_GEN", "g_tex_gen"),
    FlagAttrToGlTFInfo("G_TEXTURE_GEN_LINEAR", "g_tex_gen_linear"),
    FlagAttrToGlTFInfo("G_SHADING_SMOOTH", "g_shade_smooth"),
    FlagAttrToGlTFInfo("G_CLIPPING", "g_clipping"),  # f3dlx2 only
]


def get_cycle(combiner):
    return [
        combiner.A,
        combiner.B,
        combiner.C,
        combiner.D,
        combiner.A_alpha,
        combiner.B_alpha,
        combiner.C_alpha,
        combiner.D_alpha,
    ]


def combinersToGlTF(f3dMat):
    if f3dMat.set_combiner:
        combiner = get_cycle(f3dMat.combiner1)
        if f3dMat.rdp_settings.g_mdsft_cycletype == "G_CYC_2CYCLE":
            combiner.extend(get_cycle(f3dMat.combiner2))
        return combiner
    return None


def f3d_texture_to_gltf2_texture(extension, f3dMat, f3d_texture, export_settings):
    cur_bl_image = f3d_texture.tex
    cur_image = blender_image_to_gltf2_image(extension.Extension, cur_bl_image, f3d_texture, export_settings)
    cur_sampler = sampler_from_f3d(extension.Extension, f3dMat, f3d_texture, export_settings)
    cur_texture = texture_by_value(cur_sampler, cur_image, export_settings)

    return cur_sampler


def gather_material_pbr_metallic_roughness_hook_fast64(
    extension, gltf2_material, blender_material, orm_texture, export_settings
):
    # Unfinished
    if blender_material.is_f3d:
        if gltf2_material.extensions is None:
            gltf2_material.extensions = {}

        f3dMat = blender_material.f3d_mat
        useDict = all_combiner_uses(f3dMat)

        gltf2_material.metallic_factor = 0.0
        gltf2_material.roughness_factor = 0.5

        return


def gather_material_hook_fast64(extension, gltf2_material, blender_material, export_settings):
    if blender_material.is_f3d:

        extensionData = {}

        f3dMat = blender_material.f3d_mat
        rdpSettings = f3dMat.rdp_settings
        useDict = all_combiner_uses(f3dMat)

        extensionData["combiner"] = combinersToGlTF(f3dMat)

        extensionData["geometryMode"] = flagAttrsToGlTFArray(rdpSettings, geoModesToGlTF)
        extensionData["otherModeH"] = enum_attributes_to_glTF_dict(rdpSettings, otherModeHAttrsToGlTF)
        extensionData["otherModeL"] = othermodeLToGlTF(f3dMat)

        extensionData.update(allColorRegistersToGlTF(useDict, f3dMat))

        extensionData["lightData"] = lightsToGlTF(useDict, f3dMat)

        extensionData["largeTextureMode"] = largeTextureModeToGlTF(f3dMat)

        extensionData["textureSettings"] = textureSettingsToGlTF(f3dMat)
        extensionData["fog"] = fogToGlTF(f3dMat)

        appendGlTF2Extension(extension, fast64_extension_name, gltf2_material, extensionData)
