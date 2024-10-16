import copy
import typing
import dataclasses
import numpy as np

import bpy
from bpy.types import (
    Mesh,
    MeshUVLoopLayer,
    Object,
    Material,
    ShaderNodeOutputMaterial,
    ShaderNodeBsdfPrincipled,
    ShaderNodeMixShader,
    ShaderNodeBsdfTransparent,
    ShaderNodeBackground,
    ShaderNodeMath,
    ShaderNodeMixRGB,
    ShaderNodeVertexColor,
    ShaderNodeTexCoord,
    ShaderNodeUVMap,
    ShaderNodeTexImage,
    ShaderNodeMapping,
    ShaderNode,
)

from ...utility import get_clean_color, PluginError
from ..f3d_material import (
    combiner_uses,
    createF3DMat,
    get_output_method,
    getDefaultMaterialPreset,
    is_mat_f3d,
    all_combiner_uses,
    set_blend_to_output_method,
    trunc_10_2,
    update_all_node_values,
    F3DMaterialProperty,
    RDPSettings,
    TextureProperty,
    TextureFieldProperty,
    CombinerProperty,
)
from ..f3d_writer import getColorLayer

# TODO: Vertex colors


# Ideally we'd use mathutils.Color here but it does not support alpha (and mul for some reason)
@dataclasses.dataclass
class Color:
    r: float = 0.0
    g: float = 0.0
    b: float = 0.0
    a: float = 0.0

    def wrap(self, min_value: float, max_value: float):
        def wrap_value(value, min_value=min_value, max_value=max_value):
            range_width = max_value - min_value
            return ((value - min_value) % range_width) + min_value

        return Color(wrap_value(self.r), wrap_value(self.g), wrap_value(self.b), wrap_value(self.a))

    def to_clean_list(self):
        def round_and_clamp(value):
            return round(max(min(value, 1.0), 0.0), 4)

        return [
            round_and_clamp(self.r),
            round_and_clamp(self.g),
            round_and_clamp(self.b),
            round_and_clamp(self.a),
        ]

    def __sub__(self, other):
        return Color(self.r - other.r, self.g - other.g, self.b - other.b, self.a - other.a)

    def __add__(self, other):
        return Color(self.r + other.r, self.g + other.g, self.b + other.b, self.a + other.a)

    def __mul__(self, other):
        return Color(self.r * other.r, self.g * other.g, self.b * other.b, self.a * other.a)

    def __iter__(self):
        yield self.r
        yield self.g
        yield self.b
        yield self.a


def get_color_component(inp: str, f3d_mat: F3DMaterialProperty, previous_alpha: float) -> float:
    if inp == "0":
        return 0.0
    elif inp == "1":
        return 1.0
    elif inp.startswith("COMBINED"):
        return previous_alpha
    elif inp == "LOD_FRACTION":
        return 0.0  # Fast64 always uses black, let's do that for now
    elif inp == "PRIM_LOD_FRAC":
        return f3d_mat.prim_lod_frac
    elif inp == "PRIMITIVE_ALPHA":
        return f3d_mat.prim_color[3]
    elif inp == "ENV_ALPHA":
        return f3d_mat.env_color[3]
    elif inp == "K4":
        return f3d_mat.k4
    elif inp == "K5":
        return f3d_mat.k5


def get_color_from_input(inp: str, previous_color: Color, f3d_mat: F3DMaterialProperty, is_alpha: bool) -> Color:
    if inp == "COMBINED" and not is_alpha:
        return previous_color
    elif inp == "CENTER":
        return Color(*get_clean_color(f3d_mat.key_center), previous_color.a)
    elif inp == "SCALE":
        return Color(*list(f3d_mat.key_scale), previous_color.a)
    elif inp == "PRIMITIVE":
        return Color(*get_clean_color(f3d_mat.prim_color, True))
    elif inp == "ENVIRONMENT":
        return Color(*get_clean_color(f3d_mat.env_color, True))
    elif inp == "SHADE":
        if f3d_mat.rdp_settings.g_lighting and f3d_mat.set_lights and f3d_mat.use_default_lighting:
            return Color(*get_clean_color(f3d_mat.default_light_color), previous_color.a)
        return Color(1.0, 1.0, 1.0, previous_color.a)
    else:
        value = get_color_component(inp, f3d_mat, previous_color.a)
        if value is not None:
            return Color(value, value, value, value)
        return Color(1.0, 1.0, 1.0, 1.0)


def fake_color_from_cycle(cycle: list[str], previous_color: Color, f3d_mat: F3DMaterialProperty, is_alpha=False):
    default_colors = [Color(), Color(), Color(), Color(1.0, 1.0, 1.0, 1.0)]
    a, b, c, d = [get_color_from_input(inp, previous_color, f3d_mat, is_alpha) for inp in cycle]
    sign_extended_c = c.wrap(-1.0, 1.0001)
    unwrapped_result = (a - b) * sign_extended_c + d
    result = unwrapped_result.wrap(-0.5, 1.5)
    if is_alpha:
        result = Color(previous_color.r, previous_color.g, previous_color.b, result.a)
    return result


def get_fake_color(f3d_mat: F3DMaterialProperty):
    """Try to emulate solid colors"""
    fake_color = Color()
    cycle: CombinerProperty
    combiners = [f3d_mat.combiner1]
    if f3d_mat.rdp_settings.g_mdsft_cycletype == "G_CYC_2CYCLE":
        combiners.append(f3d_mat.combiner2)
    for cycle in combiners:
        fake_color = fake_color_from_cycle([cycle.A, cycle.B, cycle.C, cycle.D], fake_color, f3d_mat)
        fake_color = fake_color_from_cycle(
            [cycle.A_alpha, cycle.B_alpha, cycle.C_alpha, cycle.D_alpha], fake_color, f3d_mat, True
        )
    return fake_color.to_clean_list()


@dataclasses.dataclass
class AbstractedN64Texture:
    """Very abstracted representation of a N64 texture"""

    tex: bpy.types.Image
    offset: tuple[float, float] = (0.0, 0.0)
    scale: tuple[float, float] = (1.0, 1.0)
    repeat: bool = False
    set_color: bool = False
    set_alpha: bool = False
    color_is_alpha: bool = False


@dataclasses.dataclass
class AbstractedN64Material:
    """Very abstracted representation of a N64 material"""

    lighting: bool = False
    uv_gen: bool = False
    point_filtering: bool = False
    vertex_color: bool = False
    vertex_alpha: bool = False
    backface_culling: bool = False
    output_method: str = "OPA"
    color: Color = dataclasses.field(default_factory=Color)
    textures: list[AbstractedN64Texture] = dataclasses.field(default_factory=list)
    texture_sets_col: bool = False
    texture_sets_alpha: bool = False

    @property
    def main_texture(self):
        return self.textures[0] if self.textures else None


def f3d_tex_to_abstracted(f3d_tex: TextureProperty, set_color: bool, set_alpha: bool):
    def to_offset(low: float, tex_size: int):
        offset = -trunc_10_2(low) * (1.0 / tex_size)
        if offset == -0.0:
            offset = 0.0
        return offset

    if f3d_tex.tex is None:
        raise PluginError("No texture set")

    abstracted_tex = AbstractedN64Texture(f3d_tex.tex, repeat=not f3d_tex.S.clamp or not f3d_tex.T.clamp)
    size = f3d_tex.get_tex_size()
    if size != [0, 0]:
        abstracted_tex.offset = (to_offset(f3d_tex.S.low, size[0]), to_offset(f3d_tex.T.low, size[1]))
    abstracted_tex.scale = (2.0 ** (f3d_tex.S.shift * -1.0), 2.0 ** (f3d_tex.T.shift * -1.0))
    abstracted_tex.set_color, abstracted_tex.set_alpha = set_color, set_alpha
    abstracted_tex.color_is_alpha = f3d_tex.tex_format in {"I4", "I8"}

    return abstracted_tex


def f3d_mat_to_abstracted(material: Material):
    f3d_mat: F3DMaterialProperty = material.f3d_mat
    rdp: RDPSettings = f3d_mat.rdp_settings
    use_dict = all_combiner_uses(f3d_mat)
    textures = [f3d_mat.tex0] if use_dict["Texture 0"] and f3d_mat.tex0.tex_set else []
    textures += [f3d_mat.tex1] if use_dict["Texture 1"] and f3d_mat.tex1.tex_set else []
    g_packed_normals = rdp.g_packed_normals if bpy.context.scene.f3d_type == "F3DEX3" else False
    abstracted_mat = AbstractedN64Material(
        rdp.g_lighting and use_dict["Shade"],
        rdp.g_tex_gen and rdp.g_lighting,
        rdp.g_mdsft_text_filt == "G_TF_POINT",
        (not rdp.g_lighting or g_packed_normals) and combiner_uses(f3d_mat, ["SHADE"], checkAlpha=False),
        not rdp.g_fog and combiner_uses(f3d_mat, ["SHADE"], checkColor=False),
        rdp.g_cull_back,
        get_output_method(material, True),
        get_fake_color(f3d_mat),
    )
    for i in range(2):
        tex_prop = getattr(f3d_mat, f"tex{i}")
        check_list = [f"TEXEL{i}", f"TEXEL{i}_ALPHA"]
        sets_color = combiner_uses(f3d_mat, check_list, checkColor=True, checkAlpha=False)
        sets_alpha = combiner_uses(f3d_mat, check_list, checkColor=False, checkAlpha=True)
        if sets_color or sets_alpha:
            abstracted_mat.textures.append(f3d_tex_to_abstracted(tex_prop, sets_color, sets_alpha))
        abstracted_mat.texture_sets_col |= sets_color
        abstracted_mat.texture_sets_alpha |= sets_alpha
    # print(abstracted_mat)
    return abstracted_mat


def material_to_bsdf(material: Material, put_alpha_into_color=False):
    abstracted_mat = f3d_mat_to_abstracted(material)

    new_material = bpy.data.materials.new(name=material.name)
    new_material.use_nodes = True
    nodes = new_material.node_tree.nodes
    links = new_material.node_tree.links
    nodes.clear()

    set_blend_to_output_method(new_material, abstracted_mat.output_method)
    new_material.use_backface_culling = abstracted_mat.backface_culling
    new_material.alpha_threshold = 0.125

    node_x = node_y = alpha_y_offset = 0

    def set_location(node, set_x=False, x_offset=0, y_offset=0):
        nonlocal node_x, node_y
        node.location = (node_x - node.width + x_offset, node_y + y_offset)
        if set_x:
            node_x -= padded_from_node(node)

    def padded_from_node(node):
        return node.width + 50

    T = typing.TypeVar("T")

    def create_node(typ: T, name: str, location=False, x_offset=0, y_offset=0):
        node: T = nodes.new(typ.__name__)
        node.name = node.label = name
        set_location(node, location, x_offset=x_offset, y_offset=y_offset)
        return node

    # output
    output_node = create_node(ShaderNodeOutputMaterial, "Output", True)
    node_y -= 25

    # final shader node
    if abstracted_mat.lighting:
        print("Creating bsdf principled shader node")
        shader_node = create_node(ShaderNodeBsdfPrincipled, "Shader", True)
        links.new(shader_node.outputs[0], output_node.inputs[0])
        alpha_input = shader_node.inputs["Alpha"]
        color_input = shader_node.inputs["Base Color"]
        if bpy.data.version >= (4, 2, 0):
            node_y -= 22
            alpha_y_offset -= 88
        else:
            node_y -= 80
            alpha_y_offset -= 462
    else:
        print("Creating unlit shader node")
        mix_shader = create_node(ShaderNodeMixShader, "Mix Shader", True)
        links.new(mix_shader.outputs[0], output_node.inputs[0])
        alpha_input = mix_shader.inputs["Fac"]

        # transparent bsdf shader
        transparent_node = create_node(ShaderNodeBsdfTransparent, "Transparency Shader", y_offset=-47)
        links.new(transparent_node.outputs[0], mix_shader.inputs[1])
        alpha_y_offset += transparent_node.height + 47

        # background shader
        background_node = create_node(
            ShaderNodeBackground, "Background Shader", True, y_offset=-47 - transparent_node.height
        )
        links.new(background_node.outputs[0], mix_shader.inputs[2])
        color_input = background_node.inputs["Color"]
        node_y -= 172

    # cutout is removed in 4.2, it relies on the math node, glTF exporter supports this of course.
    if bpy.app.version >= (4, 2, 0) and abstracted_mat.output_method == "CLIP":
        print("Creating alpha clip node")
        alpha_clip = create_node(ShaderNodeMath, "Alpha Clip", True, y_offset=alpha_y_offset)
        alpha_clip.operation = "GREATER_THAN"
        alpha_clip.use_clamp = True
        alpha_clip.inputs[1].default_value = 0.125
        links.new(alpha_clip.outputs[0], alpha_input)
        alpha_input = alpha_clip.inputs[0]

    vertex_color = None
    vertex_color_mul = None
    if abstracted_mat.vertex_color:  # create vertex color mul node
        print("Creating vertex color node, mix rgb node and setting color input")
        vertex_color_mul = create_node(ShaderNodeMixRGB, "Vertex Color Mul", True)
        vertex_color_mul.use_clamp, vertex_color_mul.blend_type = True, "MULTIPLY"
        vertex_color_mul.inputs[0].default_value = 1
        links.new(vertex_color_mul.outputs[0], color_input)
        color_input = vertex_color_mul.inputs[2]
    if abstracted_mat.vertex_alpha:  # create vertex alpha mul node
        print("Creating vertex alpha node, mul node and setting color input")
        vertex_alpha_mul = create_node(ShaderNodeMath, "Vertex Alpha Mul", True, y_offset=alpha_y_offset)
        vertex_alpha_mul.use_clamp, vertex_alpha_mul.operation = True, "MULTIPLY"
        links.new(vertex_alpha_mul.outputs[0], alpha_input)
        alpha_input = vertex_alpha_mul.inputs[1]

    if abstracted_mat.vertex_color or (
        put_alpha_into_color and abstracted_mat.vertex_alpha
    ):  # create vertex color node
        vertex_color = create_node(
            ShaderNodeVertexColor, "Vertex Color", True, y_offset=0 if abstracted_mat.vertex_color else alpha_y_offset
        )
        vertex_color.layer_name = "Col"
    if abstracted_mat.vertex_color:  # link vertex color to vertex color mul
        links.new(vertex_color.outputs[0], vertex_color_mul.inputs[1])
    if abstracted_mat.vertex_alpha:
        if put_alpha_into_color:  # link vertex color's alpha to vertex alpha mul
            links.new(vertex_color.outputs[1], vertex_alpha_mul.inputs[0])
        else:  # create vertex alpha
            vertex_alpha = create_node(ShaderNodeVertexColor, "Vertex Alpha", True, y_offset=alpha_y_offset)
            vertex_alpha.layer_name = "Alpha"
            links.new(vertex_alpha.outputs[0], vertex_alpha_mul.inputs[0])

    mix_rgb = False
    if abstracted_mat.texture_sets_col and abstracted_mat.color[:3] != [1.0, 1.0, 1.0]:
        print(f"Creating color mul node {abstracted_mat.color} and setting color input")
        color_mul = create_node(ShaderNodeMixRGB, "Color Mul")
        color_mul.use_clamp, color_mul.blend_type = True, "MULTIPLY"
        color_mul.inputs[0].default_value = 1
        color_mul.inputs[1].default_value = abstracted_mat.color
        links.new(color_mul.outputs[0], color_input)
        color_input = color_mul.inputs[2]
        mix_rgb = True

    if abstracted_mat.texture_sets_alpha and abstracted_mat.color[3] != 1.0 and abstracted_mat.output_method != "OPA":
        print(f"Setting alpha mul node {abstracted_mat.color[3]} and setting alpha input")
        alpha_mul = create_node(ShaderNodeMath, "Alpha Mul", y_offset=alpha_y_offset)
        alpha_mul.use_clamp, alpha_mul.operation = True, "MULTIPLY"
        alpha_mul.inputs[0].default_value = abstracted_mat.color[3]
        links.new(alpha_mul.outputs[0], alpha_input)
        alpha_input = alpha_mul.inputs[1]
        mix_rgb = True
    if mix_rgb:
        node_x -= 140 + 50

    uvmap_output = None
    if abstracted_mat.textures:  # create uvmap
        if abstracted_mat.uv_gen:
            print("Creating UVmap node")
            uvmap_node = create_node(ShaderNodeTexCoord, "UVMap")
            uvmap_output = uvmap_node.outputs["Camera"]
        else:
            print("Creating generated UVmap node (Camera output)")
            uvmap_node = create_node(ShaderNodeUVMap, "UVMap")
            uvmap_node.uv_map = "UVMap"
            uvmap_output = uvmap_node.outputs["UV"]

    tex_x_offset = tex_y_offset = 0
    texture_nodes = []
    for abstracted_tex in abstracted_mat.textures:  # create textures
        tex_node = create_node(ShaderNodeTexImage, "Texture", y_offset=tex_y_offset)
        tex_node.image = abstracted_tex.tex
        tex_node.extension = "REPEAT" if abstracted_tex.repeat else "EXTEND"
        tex_node.interpolation = "Closest" if abstracted_mat.point_filtering else "Linear"
        texture_nodes.append(tex_node)
        new_x_offset = -padded_from_node(tex_node)
        tex_y_offset -= (tex_node.height * 2) + 125

        assert uvmap_output
        if abstracted_tex.offset != (0.0, 0.0) or abstracted_tex.scale != (1.0, 1.0):
            mapping_node = create_node(ShaderNodeMapping, "Mapping", x_offset=new_x_offset, y_offset=tex_y_offset + 98)
            mapping_node.vector_type = "POINT"
            tex_y_offset -= mapping_node.height
            mapping_node.inputs["Location"].default_value = abstracted_tex.offset + (0.0,)
            mapping_node.inputs["Scale"].default_value = abstracted_tex.scale + (1.0,)
            links.new(uvmap_output, mapping_node.inputs[0])
            links.new(mapping_node.outputs[0], tex_node.inputs[0])

            new_x_offset -= padded_from_node(mapping_node)
        else:
            links.new(uvmap_output, tex_node.inputs[0])
        if new_x_offset < tex_x_offset:
            tex_x_offset = new_x_offset
    node_x += tex_x_offset  # update node location

    if abstracted_mat.textures:  # update uvmap node location
        if len(abstracted_mat.textures) > 1:
            node_y += tex_y_offset / len(texture_nodes)
        else:
            node_y -= 30
        set_location(uvmap_node, True)

    color_input.default_value = abstracted_mat.color[:3] + [1.0]
    if abstracted_mat.texture_sets_col:
        links.new(texture_nodes[0].outputs[0], color_input)

    alpha_input.default_value = abstracted_mat.color[3]
    if abstracted_mat.texture_sets_alpha:
        if abstracted_mat.main_texture.color_is_alpha:  # i4/i8
            links.new(texture_nodes[0].outputs[0], alpha_input)
        else:
            links.new(texture_nodes[0].outputs[1], alpha_input)

    return new_material


def apply_alpha(blender_mesh: Mesh):
    color_layer = getColorLayer(blender_mesh, layer="Col")
    alpha_layer = getColorLayer(blender_mesh, layer="Alpha")
    if not color_layer or not alpha_layer:
        return
    color = np.empty(len(blender_mesh.loops) * 4, dtype=np.float32)
    alpha = np.empty(len(blender_mesh.loops) * 4, dtype=np.float32)
    color_layer.foreach_get("color", color)
    alpha_layer.foreach_get("color", alpha)
    alpha = alpha.reshape(-1, 4)
    color = color.reshape(-1, 4)

    # Calculate alpha from the median of the alpha layer RGB
    alpha_median = np.median(alpha[:, :3], axis=1)
    color[:, 3] = alpha_median

    color = color.flatten()
    color_layer.foreach_set("color", color)


def material_to_f3d(
    obj: Object, material: Material, uv_map: MeshUVLoopLayer | None = None, use_lights_for_colors=False
):
    def find_output_node(material: Material):
        for node in material.node_tree.nodes:
            if isinstance(node, ShaderNodeOutputMaterial):
                return node
        return None

    def find_linked_nodes(
        starting_node: ShaderNode, node_check: callable, specific_input_sockets=None, specific_output_sockets=None
    ):
        nodes: list[ShaderNode] = []
        for inp in starting_node.inputs:
            if specific_input_sockets is not None and inp.name not in specific_input_sockets:
                continue
            for link in inp.links:
                if link.to_node == starting_node and (
                    specific_output_sockets is None or link.from_socket.name in specific_output_sockets
                ):
                    if node_check(link.from_node):
                        nodes.append(link.from_node)
                        continue
                nodes.extend(
                    find_linked_nodes(link.from_node, node_check, specific_input_sockets, specific_output_sockets)
                )
        return nodes

    print(f"Converting BSDF material {material.name}")

    abstracted_mat = AbstractedN64Material()

    abstracted_mat.color = None
    output_node = find_output_node(material) if material.use_nodes else None
    if output_node is None:
        abstracted_mat.color = material.diffuse_color
    else:
        shaders = find_linked_nodes(
            output_node,
            lambda node: node.bl_idname.startswith("ShaderNodeBsdf")
            or node.bl_idname.removeprefix("ShaderNode")
            in {"Background", "Emission", "SubsurfaceScattering", "VolumeAbsorption", "VolumeScatter"},
            specific_input_sockets={"Surface"},
        )
        if len(shaders) > 1:
            print(f"WARNING: More than 1 shader connected to {material.name}. Using first shader.")
        if len(shaders) == 0:
            abstracted_mat.color = material.diffuse_color
            print(f"WARNING: No shader connected to {material.name}. Using default color.")
        else:
            main_shader = shaders[0]
            if main_shader.bl_idname in {"Background", "Emission"}:  # is unlit
                abstracted_mat.lighting = False
            else:
                abstracted_mat.lighting = True
            alpha_textures = find_linked_nodes(
                main_shader,
                lambda node: node.bl_idname == "ShaderNodeTexImage",
                specific_output_sockets={"Alpha"},
            )
            color_textures = find_linked_nodes(
                main_shader,
                lambda node: node.bl_idname == "ShaderNodeTexImage",
                specific_output_sockets={"Color", "Base Color"},
            )
            textures: list[ShaderNodeTexImage] = list(dict.fromkeys(color_textures + alpha_textures).keys())
            if len(textures) > 2:
                print(f"WARNING: More than 2 textures connected to {material.name}.")
            if len(textures) > 0:
                for tex_node in textures[:2]:
                    abstracted_tex = AbstractedN64Texture(tex_node.image)
                    mapping = find_linked_nodes(tex_node, lambda node: node.bl_idname == "ShaderNodeMapping")
                    if len(mapping) > 1:
                        print(f"WARNING: More than 1 mapping node connected to {tex_node.name}.")
                    elif len(mapping) == 1:
                        mapping = mapping[0]
                        abstracted_tex.offset = tuple(mapping.inputs["Location"].default_value)
                        abstracted_tex.scale = tuple(mapping.inputs["Scale"].default_value)
                    uv_gen = find_linked_nodes(
                        tex_node,
                        lambda node: node.bl_idname == "ShaderNodeTexCoord",
                        specific_input_sockets={"Vector"},
                        specific_output_sockets={"Normal"},
                    )
                    if uv_gen:
                        abstracted_mat.uv_gen = True
                    if tex_node.interpolation == "Closest":
                        abstracted_mat.point_filtering = True
                    abstracted_tex.repeat = tex_node.extension == "REPEAT"
                    abstracted_tex.set_color = tex_node in color_textures
                    abstracted_tex.set_alpha = tex_node in alpha_textures
                    if abstracted_tex.set_color:
                        abstracted_mat.texture_sets_col = True
                    if abstracted_tex.set_alpha:
                        abstracted_mat.texture_sets_alpha = True
                    abstracted_mat.textures.append(abstracted_tex)
            else:
                abstracted_mat.color = Color(*shaders[0].inputs[0].default_value)

    materials = obj.data.materials
    found_uv_map_nodes = find_linked_nodes(output_node, lambda node: node.bl_idname == "ShaderNodeUVMap")
    found_uv_map_names = dict.fromkeys([node.uv_map for node in found_uv_map_nodes]).keys()
    found_uv_maps = [obj.data.uv_layers[name] for name in found_uv_map_names]
    if len(found_uv_maps) > 1:
        print(f"WARNING: More than 1 UV map connected to {material.name}. Using first UV map.")
    if uv_map and len(found_uv_maps) > 0 and not any(found_uv_map.active for found_uv_map in found_uv_maps):
        found_uv_map = found_uv_maps[0]
        # change the material's tris's uvs in the main UV map to the one found
        print(f"Updating main UV map with {found_uv_map.name} UVs")
        for poly in obj.data.polygons:
            for loop_idx in poly.loop_indices:
                if poly.material_index < len(materials) and materials[poly.material_index] == material:
                    uv_map.data[loop_idx].uv = found_uv_map.data[loop_idx].uv

    preset = getDefaultMaterialPreset("Shaded Solid")
    new_material = createF3DMat(obj, preset=preset, append=False)
    new_material.name = material.name
    f3d_mat: F3DMaterialProperty = new_material.f3d_mat
    rdp: RDPSettings = f3d_mat.rdp_settings

    rdp.g_tex_gen = abstracted_mat.uv_gen
    rdp.g_mdsft_text_filt = "G_TF_POINT" if abstracted_mat.point_filtering else "G_TF_BILERP"

    if abstracted_mat.color is not None:
        f3d_mat.default_light_color = tuple(abstracted_mat.color)
        f3d_mat.prim_color = tuple(abstracted_mat.color)
    for i, abstracted_tex in enumerate(abstracted_mat.textures):
        f3d_tex: TextureProperty = getattr(f3d_mat, f"tex{i}")
        f3d_tex.tex = abstracted_tex.tex
        f3d_tex.tex_set = True
        f3d_tex.autoprop = abstracted_tex.offset == (0, 0) and abstracted_tex.scale == (1, 1)
        s: TextureFieldProperty = f3d_tex.S
        t: TextureFieldProperty = f3d_tex.T
        s.low = abstracted_tex.offset[0]
        t.low = abstracted_tex.offset[1]
        s.shift = int(abstracted_tex.scale[0] // 2)  # TODO
        t.shift = int(abstracted_tex.scale[1] // 2)

    with bpy.context.temp_override(material=new_material):
        update_all_node_values(new_material, bpy.context)  # Reload everything

    return new_material


def obj_to_f3d(obj: Object, materials: dict[Material, Material]):
    assert obj.type == "MESH"
    print(f"Converting BSDF materials in {obj.name}")
    for index, material_slot in enumerate(obj.material_slots):
        material = material_slot.material
        if material is None or is_mat_f3d(material):
            continue
        if material in materials:
            obj.material_slots[index].material = materials[material]
        else:
            obj.material_slots[index].material = material_to_f3d(obj, material, obj.data.uv_layers.active)
    for uv_map in copy.copy(obj.data.uv_layers.values()):
        if uv_map.active:
            uv_map.name = "UVMap"
        else:
            obj.data.uv_layers.remove(uv_map)


def obj_to_bsdf(obj: Object, materials: dict[Material, Material], put_alpha_into_color: bool):
    assert obj.type == "MESH"
    print(f"Converting F3D materials in {obj.name}")
    if put_alpha_into_color:
        apply_alpha(obj.data)
    for index, material_slot in enumerate(obj.material_slots):
        material = material_slot.material
        if material is None or not is_mat_f3d(material):
            continue
        if material in materials:
            obj.material_slots[index].material = materials[material]
        else:
            obj.material_slots[index].material = material_to_bsdf(material, put_alpha_into_color)
