import bpy
from bpy.types import Image

from ..gltf_utility import GlTF2SubExtension
from .f3d_gbi import F3D, get_F3D_GBI
from .f3d_material import all_combiner_uses, update_node_values_with_preset, update_preset_manual_v4, createScenePropertiesForMaterial, F3DMaterialProperty, TextureProperty, link_f3d_material_library

# TODO: Check glTF addon version instead
if bpy.app.version >= (3, 6, 0):
    if bpy.app.version >= (3, 6, 5):
        from io_scene_gltf2.blender.exp.material.gltf2_blender_gather_image import __is_blender_image_a_webp
    from io_scene_gltf2.blender.exp.material.gltf2_blender_gather_image import (
        __gather_name,
        __make_image,
        __gather_uri,
        __gather_buffer_view,
        __is_blender_image_a_jpeg,
    )
    from io_scene_gltf2.blender.exp.material.extensions.gltf2_blender_image import ExportImage
else:
    from io_scene_gltf2.blender.exp.gltf2_blender_gather_image import (
        __gather_name,
        __make_image,
        __gather_uri,
        __gather_buffer_view,
        __is_blender_image_a_jpeg,
    )
    from io_scene_gltf2.blender.exp.gltf2_blender_image import ExportImage

from io_scene_gltf2.io.com import gltf2_io
from io_scene_gltf2.blender.imp.gltf2_blender_image import BlenderImage
from io_scene_gltf2.io.com.gltf2_io_constants import TextureFilter, TextureWrap


def is_blender_image_a_webp(image: Image) -> bool:
    if bpy.data.version < (3, 6, 5):
        return False
    return __is_blender_image_a_webp(image)


def __get_mime_type_of_image(name: str, export_settings: dict):
    image = bpy.data.images[name]
    if image.channels == 4:  # Has alpha channel, doesn´t actually check for transparency
        if is_blender_image_a_webp(image):
            return "image/webp"
        return "image/png"

    if export_settings["gltf_image_format"] == "AUTO":
        if __is_blender_image_a_jpeg(image):
            return "image/jpeg"
        elif is_blender_image_a_webp(image):
            return "image/webp"
        return "image/png"

    elif export_settings["gltf_image_format"] == "JPEG":
        return "image/jpeg"


def get_gltf_image_from_blender_image(blender_image_name: str, export_settings: dict):
    image_data = ExportImage.from_blender_image(bpy.data.images[blender_image_name])

    if bpy.app.version > (4, 1, 0):
        name = __gather_name(image_data, None, export_settings)
    else:
        name = __gather_name(image_data, export_settings)
    mime_type = __get_mime_type_of_image(blender_image_name, export_settings)

    uri = __gather_uri(image_data, mime_type, name, export_settings)
    buffer_view = __gather_buffer_view(image_data, mime_type, name, export_settings)

    image = __make_image(buffer_view, None, None, mime_type, name, uri, export_settings)
    return image


class Fast64Extension(GlTF2SubExtension):
    extension_name = "EXT_fast64"

    def post_init(self):
        self.f3d: F3D = get_F3D_GBI()

        if not self.extension.importing:
            return
        previous_obj = bpy.context.view_layer.objects.active
        old_material = previous_obj.active_material if previous_obj is not None else None

        # change current material and make other window's shader editor is updated
        temp_override = get_shader_editor_context()
        temp_object = bpy.data.objects.new("temp", None)
        bpy.context.scene.collection.objects.link(temp_object)
        bpy.context.view_layer.objects.active = temp_object

        link_f3d_material_library()
        f3d_mat = bpy.data.materials["fast64_f3d_material_library_beefwashere"]
        bpy.context.object.active_material = f3d_mat
        temp_override['space'].node_tree = f3d_mat.node_tree
        # select all nodes and copy them to clipboard
        for node in f3d_mat.node_tree.nodes:
            node.select = True
        bpy.ops.node.clipboard_copy(temp_override)
        bpy.data.objects.remove(temp_object)
        bpy.data.materials.remove(f3d_mat)

        # back to original material
        if previous_obj is not None:
            bpy.context.view_layer.objects.active = previous_obj
        if old_material is not None:
            bpy.context.object.active_material = old_material

    def sampler_from_f3d(self, f3d_mat: F3DMaterialProperty, f3d_tex: TextureProperty):
        wrap = []
        for field in ["S", "T"]:
            field_prop = getattr(f3d_tex, field)
            wrap.append(
                TextureWrap.ClampToEdge
                if field_prop.clamp
                else TextureWrap.MirroredRepeat
                if field_prop.mirror
                else TextureWrap.Repeat
            )

        use_nearest = f3d_mat.rdp_settings.g_mdsft_text_filt == "G_TF_POINT"
        mag_filter = TextureFilter.Nearest if use_nearest else TextureFilter.Linear
        min_filter = TextureFilter.NearestMipmapNearest if use_nearest else TextureFilter.LinearMipmapLinear
        sampler = gltf2_io.Sampler(
            extensions=None,
            extras=None,
            mag_filter=mag_filter,
            min_filter=min_filter,
            name=None,
            wrap_s=wrap[0],
            wrap_t=wrap[1],
        )
        self.append_gltf2_extension(sampler, f3d_tex.to_dict())
        return sampler

    def sampler_to_f3d(self, gltf2_sampler, f3d_tex: TextureProperty):
        data = self.get_gltf2_extension(gltf2_sampler)
        if data is None:
            return
        f3d_tex.from_dict(data)

    def f3d_to_gltf2_texture(
        self,
        f3d_mat: F3DMaterialProperty,
        f3d_texture,
        export_settings: dict,
    ):
        source = get_gltf_image_from_blender_image(f3d_texture.tex.name, export_settings)
        sampler = self.sampler_from_f3d(f3d_mat, f3d_texture)
        return gltf2_io.Texture(
            extensions=None,
            extras=None,
            name=None,
            sampler=sampler,
            source=source,
        )

    def gltf2_texture_to_f3d_texture(self, gltf2_texture, gltf, f3d_tex: TextureProperty):
        if gltf2_texture.sampler is not None:
            sampler = gltf.data.samplers[gltf2_texture.sampler]
            self.sampler_to_f3d(sampler, f3d_tex)
        if gltf2_texture.source is not None:
            BlenderImage.create(gltf, gltf2_texture.source)
            img = gltf.data.images[gltf2_texture.source]
            blender_image_name = img.blender_image_name
            if blender_image_name:
                f3d_tex.tex = bpy.data.images[blender_image_name]

    def f3d_to_glTF2_texture_info(
        self,
        f3d_mat: F3DMaterialProperty,
        f3d_texture: TextureProperty,
        export_settings: dict,
    ):
        return gltf2_io.TextureInfo(
            extensions=None,
            extras=None,
            index=self.f3d_to_gltf2_texture(f3d_mat, f3d_texture, export_settings),
            tex_coord=None,  # TODO: Convert high and low to tex_coords
        )

    def gather_material_hook(self, gltf2_material, blender_material, export_settings: dict):
        if not blender_material.is_f3d:
            return
        data = {}

        f3d_mat: F3DMaterialProperty = blender_material.f3d_mat
        use_dict = all_combiner_uses(f3d_mat)

        data["combiner"] = f3d_mat.combiner_to_dict()
        data["colors"] = f3d_mat.colors_to_dict(self.f3d, use_dict)
        data.update(f3d_mat.rdp_settings.to_dict())
        data["textureSettings"] = f3d_mat.extra_texture_settings_to_dict()

        textures = {}
        data["textures"] = textures
        pbr = gltf2_material.pbr_metallic_roughness
        if use_dict["Texture 0"]:
            textures["0"] = self.f3d_to_glTF2_texture_info(f3d_mat, f3d_mat.tex0, export_settings)
        if use_dict["Texture 1"]:
            textures["1"] = self.f3d_to_glTF2_texture_info(f3d_mat, f3d_mat.tex1, export_settings)
        if f3d_mat.is_multi_tex:
            pbr.base_color_texture = textures["0"]
            pbr.metallic_roughness_texture = textures["1"]
        else:
            pbr.base_color_texture = textures.values()[0]
        self.append_gltf2_extension(gltf2_material, data)

    def gather_node_hook(self, gltf2_node, blender_object, _export_settings: dict):
        data = {}
        if self.f3d.F3DEX_GBI or self.f3d.F3DEX_GBI_2:
            data["use_culling"] = blender_object.use_f3d_culling
        self.append_gltf2_extension(gltf2_node, data)

    # Importing

    def gather_import_material_after_hook(
        self,
        gltf_material,
        _vertex_color,
        blender_material,
        gltf,
    ):
        data = self.get_gltf2_extension(gltf_material)
        if data is None:
            return

        # Copy nodes HACK
        temp_override = get_shader_editor_context()
        temp_override['space'].node_tree = blender_material.node_tree
        for node in list(blender_material.node_tree.nodes):
            blender_material.node_tree.nodes.remove(node)
        bpy.ops.node.clipboard_paste(temp_override)

        createScenePropertiesForMaterial(blender_material)
        blender_material.is_f3d = True
        blender_material.mat_ver = 5
        blender_material.f3d_update_flag = True

        f3d_mat: F3DMaterialProperty = blender_material.f3d_mat
        f3d_mat.combiner_from_dict(data.get("combiner", {}))
        f3d_mat.colors_from_dict(data.get("colors", {}))
        f3d_mat.rdp_settings.from_dict(data)
        f3d_mat.extra_texture_settings_from_dict(data.get("textureSettings", {}))

        for num, tex_info in data.get("textures", {}).items():
            gltf2_texture = gltf.data.textures[tex_info.get("index", 0)]
            f3d_tex = f3d_mat.tex0 if num == "0" else f3d_mat.tex1
            self.gltf2_texture_to_f3d_texture(gltf2_texture, gltf, f3d_tex)

        blender_material.f3d_update_flag = False
        f3d_mat.use_default_lighting = f3d_mat.use_default_lighting


    def gather_import_node_after_hook(self, _vnode, gltf_node, blender_object, _gltf):
        data = self.get_gltf2_extension(gltf_node)
        if data is None:
            return
        blender_object.use_f3d_culling = data.get("use_culling", True)

def get_shader_editor_context():
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "NODE_EDITOR":
                for space in area.spaces:
                    if space.tree_type == "ShaderNodeTree":
                        context_override = {"area": area, "space": space, "screen": screen}
                        return context_override