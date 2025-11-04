from typing import TYPE_CHECKING
import numpy as np

import bpy
from mathutils import Matrix, Vector
from bpy.types import Mesh, Object

from ...utility import create_or_get_world, PluginError
from ..f3d_gbi import (
    SPClearGeometryMode,
    SPDisplayList,
    SPVertex,
    SPSetGeometryMode,
    SPCullDisplayList,
    SP1Triangle,
    SPEndDisplayList,
    FMesh,
    FModel,
    FMaterial,
    GfxMatWriteMethod,
    Vtx,
)

from .convex_hull import create_convex_hull
from .rotated_bounds import get_rotated_bounding_box

if TYPE_CHECKING:
    from .properties import F3D_DefaultCullingProperties, F3D_CullingProperties


def find_vertices_by_draw_layer(obj: Object, draw_layer_field: str | None, draw_layer: str):
    mesh = obj.data
    selected_verts = set()  # avoid duplicates

    for poly in mesh.polygons:
        mat_index = poly.material_index
        if mat_index >= len(obj.material_slots):
            continue

        mat = obj.material_slots[mat_index].material
        if mat is None:
            continue

        if getattr(mat.f3d_mat.draw_layer, draw_layer_field) == draw_layer:
            for vid in poly.vertices:
                selected_verts.add(mesh.vertices[vid])

    return list(selected_verts)


cube_offsets = (
    Vector((-1, -1, -1)),
    Vector((1, -1, -1)),
    Vector((1, 1, -1)),
    Vector((-1, 1, -1)),
    Vector((-1, -1, 1)),
    Vector((1, -1, 1)),
    Vector((1, 1, 1)),
    Vector((-1, 1, 1)),
)

cube_tris = [
    (0, 1, 2),
    (0, 2, 3),  # bottom
    (4, 6, 5),
    (4, 7, 6),  # top
    (0, 4, 5),
    (0, 5, 1),  # front
    (1, 5, 6),
    (1, 6, 2),  # right
    (2, 6, 7),
    (2, 7, 3),  # back
    (3, 7, 4),
    (3, 4, 0),  # left
]


def add_cull_vertices(
    draw_layer_field: str | None,
    layer: str,
    obj: Object,
    default_culling: "F3D_DefaultCullingProperties",
    f_mesh: FMesh,
    transform_matrix: Matrix,
    f_model: FModel,
    convert_texture_data: bool,
):
    assert obj.type == "MESH" and obj.data is not None, f"Object {obj.name} is not a mesh."

    f_mesh.add_cull_vtx()
    cull_commands = []

    culling: F3D_CullingProperties = obj.fast64.f3d.culling
    if not culling.edit_default:
        culling: F3D_DefaultCullingProperties = default_culling

    buffer_size = f_model.f3d.vert_buffer_size
    if culling.type in {"ROTATED_BB", "CONVEX"}:
        vertices = find_vertices_by_draw_layer(obj, draw_layer_field, layer)
        mesh_points = np.array([transform_matrix @ v.co for v in vertices], dtype=np.float64)
        mesh_points_int = np.round(mesh_points).astype(np.int64)
        if culling.type == "ROTATED_BB":
            vertices = get_rotated_bounding_box(mesh_points_int)
        elif culling.type == "CONVEX":
            vertices = create_convex_hull(mesh_points_int, buffer_size, culling.shared.max_geometric_error)
    else:
        culling_obj = culling.obj
        if culling_obj is None:
            raise PluginError("Custom culling object is not set")
        if culling_obj.type != "MESH" or culling_obj.data is None:
            raise PluginError("Custom culling object is not a mesh")
        if culling_obj is obj:
            raise PluginError("Custom culling object cannot be the same as the mesh")
        vertices = np.array([transform_matrix @ v.co for v in culling_obj.data.vertices], dtype=np.int64)

    if default_culling.debug_mode:
        from ..f3d_writer import saveOrGetF3DMaterial

        mat, _tex_dimensions = saveOrGetF3DMaterial(
            default_culling.debug_mat, f_model, obj, layer, convert_texture_data
        )
        mat: FMaterial
        tri_group = f_mesh.tri_group_new(mat)
        tri_group.triList.name = f_mesh.name + "_cull_debug_tri"
        tri_group.vertexList.name = f_mesh.name + "_cull_debug_vtx"

        for base_vert in vertices:
            cube_verts = []
            for off in cube_offsets:
                as_vector = Vector(base_vert) + (transform_matrix @ off * default_culling.cube_size)
                as_int_tuple = (round(x) for x in as_vector)
                cube_verts.append(Vtx(as_int_tuple, (0, 0), (0, 0), 0))
            tri_group.triList.commands.append(
                SPVertex(tri_group.vertexList, len(tri_group.vertexList.vertices), len(cube_verts), 0)
            )
            tri_group.vertexList.vertices.extend(cube_verts)

            for a, b, c in cube_tris:
                tri_group.triList.commands.append(SP1Triangle(a, b, c, 0))
        tri_group.triList.commands.append(SPEndDisplayList())
        cull_commands = [
            SPDisplayList(mat.material),
            SPDisplayList(tri_group.triList),
            SPDisplayList(mat.revert),
        ] + cull_commands

    f_mesh.cullVertexList.vertices = [Vtx(v, (0, 0), (0, 0), 0) for v in vertices]

    vertex_count = len(f_mesh.cullVertexList.vertices)
    if vertex_count > buffer_size:
        raise PluginError(f"Too many vertices in culling vertex list: {vertex_count}")

    load_size = f_model.f3d.vert_load_size  # in < gbi 2 reject microcodes, load size can be smaller than buffer size
    i = 0
    while i < len(f_mesh.cullVertexList.vertices):
        vertices_to_load = max(0, min(load_size, vertex_count - i))
        cull_commands.append(SPVertex(f_mesh.cullVertexList, i, vertices_to_load, i))
        i += vertices_to_load
    cull_commands.append(SPCullDisplayList(0, len(vertices) - 1))

    write_method = f_model.matWriteMethod
    if write_method == GfxMatWriteMethod.WriteDifferingAndRevert:
        assert bpy.context.scene is not None
        defaults = create_or_get_world(bpy.context.scene).rdp_defaults
        if defaults.g_lighting:
            cull_commands = [SPClearGeometryMode({"G_LIGHTING"})] + cull_commands + [SPSetGeometryMode({"G_LIGHTING"})]
    elif write_method == GfxMatWriteMethod.WriteAll:
        cull_commands = [SPClearGeometryMode({"G_LIGHTING"})] + cull_commands + [SPSetGeometryMode({"G_LIGHTING"})]
    else:
        raise PluginError(f"Unhandled material write method for f3d culling: {write_method}")

    f_mesh.draw.commands = cull_commands + f_mesh.draw.commands
