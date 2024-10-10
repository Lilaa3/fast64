import bpy
from bpy.types import Object, Material

import dataclasses

from ...utility import get_clean_color, PluginError
from ..f3d_material import (
    combiner_uses,
    get_output_method,
    is_mat_f3d,
    all_combiner_uses,
    set_blend_to_output_method,
    trunc_10_2,
    F3DMaterialProperty,
    RDPSettings,
    TextureProperty,
    CombinerProperty,
)


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


def get_color_from_input(
    inp: str, previous_color: Color, f3d_mat: F3DMaterialProperty, is_alpha: bool, default_color: Color
) -> Color:
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
        return default_color


def fake_color_from_cycle(cycle: list[str], previous_color: Color, f3d_mat: F3DMaterialProperty, is_alpha=False):
    default_colors = [Color(1.0, 1.0, 1.0, 1.0), Color(), Color(1.0, 1.0, 1.0, 1.0), Color()]
    a, b, c, d = [
        get_color_from_input(inp, previous_color, f3d_mat, is_alpha, default_color)
        for inp, default_color in zip(cycle, default_colors)
    ]
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


@dataclasses.dataclass
class AbstractedN64Material:
    """Very abstracted representation of a N64 material"""

    lighting: bool = False
    uv_geo: bool = False
    point_filtering: bool = False
    output_method: str = "OPA"
    backface_culling: bool = False
    color: Color = dataclasses.field(default_factory=Color)
    textures: list[AbstractedN64Texture] = dataclasses.field(default_factory=list)
    texture_sets_col: bool = False
    texture_sets_alpha: bool = False

    @property
    def main_texture(self):
        return self.textures[0] if self.textures else None


def f3d_tex_to_abstracted(f3d_tex: TextureProperty):
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

    return abstracted_tex


def f3d_mat_to_abstracted(material: Material):
    f3d_mat: F3DMaterialProperty = material.f3d_mat
    rdp: RDPSettings = f3d_mat.rdp_settings
    use_dict = all_combiner_uses(f3d_mat)
    textures = [f3d_mat.tex0] if use_dict["Texture 0"] and f3d_mat.tex0.tex_set else []
    textures += [f3d_mat.tex1] if use_dict["Texture 1"] and f3d_mat.tex1.tex_set else []

    abstracted_mat = AbstractedN64Material(
        rdp.g_lighting,
        rdp.g_tex_gen,
        rdp.g_mdsft_text_filt == "G_TF_POINT",
        get_output_method(material, True),
        rdp.g_cull_back,
        get_fake_color(f3d_mat),
    )
    for i in range(2):
        tex_prop = getattr(f3d_mat, f"tex{i}")
        check_list = [f"TEXEL{i}", f"TEXEL{i}_ALPHA"]
        sets_color = combiner_uses(f3d_mat, check_list, checkColor=True, checkAlpha=False)
        sets_alpha = combiner_uses(f3d_mat, check_list, checkColor=False, checkAlpha=True)
        if sets_color or sets_alpha:
            abstracted_mat.textures.append(f3d_tex_to_abstracted(tex_prop))
        abstracted_mat.texture_sets_col |= sets_color
        abstracted_mat.texture_sets_alpha |= sets_alpha
    return abstracted_mat


def material_to_bsdf(material: Material):
    abstracted_mat = f3d_mat_to_abstracted(material)

    new_material = bpy.data.materials.new(name=material.name)
    new_material.use_nodes = True
    node_tree = new_material.node_tree
    nodes = node_tree.nodes
    links = node_tree.links
    nodes.clear()

    set_blend_to_output_method(new_material, abstracted_mat.output_method)
    new_material.use_backface_culling = abstracted_mat.backface_culling

    node_x = node_y = 0

    output_node = nodes.new(type="ShaderNodeOutputMaterial")
    node_x -= 300
    node_y -= 25

    # final shader node
    if abstracted_mat.lighting:
        shader_node = nodes.new(type="ShaderNodeBsdfPrincipled")
    else:
        shader_node = nodes.new(type="ShaderNodeEmission")
    shader_node.location = (node_x, node_y)
    node_x -= 300
    links.new(shader_node.outputs[0], output_node.inputs[0])

    # texture nodes
    tex_node_y = node_y
    if abstracted_mat.textures:
        if abstracted_mat.uv_geo:
            uvmap_node = nodes.new(type="ShaderNodeTexCoord")
            uvmap_output = uvmap_node.outputs["Camera"]
        else:
            uvmap_node = nodes.new(type="ShaderNodeUVMap")
            uvmap_node.uv_map = "UVMap"
            uvmap_output = uvmap_node.outputs["UV"]
        uvmap_node.location = (node_x - 200, tex_node_y)

    texture_nodes = []
    for abstracted_tex in abstracted_mat.textures:
        tex_node = nodes.new(type="ShaderNodeTexImage")
        tex_node.location = (node_x, tex_node_y)
        tex_node.image = abstracted_tex.tex
        tex_node.extension = "REPEAT" if abstracted_tex.repeat else "EXTEND"
        tex_node.interpolation = "Closest" if abstracted_mat.point_filtering else "Linear"
        texture_nodes.append(tex_node)

        if abstracted_tex.offset != (0.0, 0.0) or abstracted_tex.scale != (1.0, 1.0):
            uvmap_node.location = (node_x - 400, uvmap_node.location[1])

            mapping_node = nodes.new(type="ShaderNodeMapping")
            mapping_node.vector_type = "POINT"
            mapping_node.location = (node_x - 200, tex_node_y)
            mapping_node.inputs["Location"].default_value = abstracted_tex.offset + (0.0,)
            mapping_node.inputs["Scale"].default_value = abstracted_tex.scale + (1.0,)
            links.new(uvmap_output, mapping_node.inputs[0])
            links.new(mapping_node.outputs[0], tex_node.inputs[0])
        else:
            links.new(uvmap_output, tex_node.inputs[0])

        tex_node_y -= 300

    if abstracted_mat.texture_sets_col:
        links.new(texture_nodes[0].outputs[0], shader_node.inputs["Base Color"])
    else:
        shader_node.inputs["Base Color"].default_value = abstracted_mat.color[:3] + [1.0]
    if abstracted_mat.texture_sets_alpha:
        links.new(texture_nodes[0].outputs[1], shader_node.inputs["Alpha"])
    else:
        shader_node.inputs["Alpha"].default_value = abstracted_mat.color[3]

    return new_material


def material_to_f3d(material: Material):
    pass


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
            obj.material_slots[index].material = material_to_f3d(material)


def obj_to_bsdf(obj: Object, materials: dict[Material, Material]):
    assert obj.type == "MESH"
    print(f"Converting F3D materials in {obj.name}")
    for index, material_slot in enumerate(obj.material_slots):
        material = material_slot.material
        if material is None or not is_mat_f3d(material):
            continue
        if material in materials:
            obj.material_slots[index].material = materials[material]
        else:
            obj.material_slots[index].material = material_to_bsdf(material)
