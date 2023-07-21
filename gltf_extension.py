# Original implementation from github.com/Mr-Wiseguy/gltf64-blender
import bpy
from .fast64_internal.f3d.f3d_gltf import (
    gather_material_hook_fast64,
    gather_material_pbr_metallic_roughness_hook_fast64,
)
from .fast64_internal.sm64.sm64_gltf import (
    gather_asset_hook_sm64,
    gather_gltf_extensions_hook_sm64,
    gather_joint_hook_sm64,
    gather_mesh_hook_sm64,
    gather_node_hook_sm64,
    gather_scene_hook_sm64,
    gather_material_hook_sm64,
    gather_skin_hook_sm64,
)
from pprint import pprint

fast64_extension_name = "EXT_fast64"

# Changes made (or being worked on) from original glTF64:
# Property names (keys) will now all use the glTF standard naming, camelCase.
# Rework of geometry modes to better suit different microcodes and for readability.
# Rework of upper modes to use a dictionary of gbi enums for each mode, all fast64 upper modes added.
# Fog added (including sm64 "global" fog)
# Lights (including custom lights) added
# Chroma key and yuv convert values added.
# SM64 support (EXT_sm64).
# Future OOT support.

# TODO:
# Fix texture appending. Wiseguy´s approach will not work.
# Put texture format in the sampler rather than in the image, as image´s in fast64 can be exported into
# different texture types.
# Add options for using fast64/sm64 extensions in the glTF exporting tab. Add an panel for glTF exporting.
# Improve the materials to make them as accurate as glTf allows outside of an n64 rendering context.
# Possibly warn user when a custom c enum has invalid characters and empty functions

oldMaterialWarning = '\
Warning: Unsupported material version. \
Please upgrade your materials using the "Recreate F3D Materials As V5" \
button under the "Fast64" tab. Using outdated materials may lead to bugs and errors.'

from io_scene_gltf2.io.com.gltf2_io_extensions import Extension


import traceback


class glTF2ExportUserExtension:
    def __init__(self):
        # We need to wait until we create the gltf2UserExtension to import the gltf2 modules
        # Otherwise, it may fail because the gltf2 may not be loaded yet
        self.Extension = Extension
        self.sm64 = True
        self.actorExport = False

    def gather_asset_hook(self, gltf2_asset, export_settings):
        try:
            gather_asset_hook_sm64(self, gltf2_asset, export_settings)
        except:
            traceback.print_exc()
            raise

    def gather_gltf_extensions_hook(self, gltf2_plan, export_settings):
        try:
            gather_gltf_extensions_hook_sm64(self, gltf2_plan, export_settings)
        except:
            traceback.print_exc()
            raise

    def gather_scene_hook(self, gltf2_scene, blender_scene, export_settings):
        try:
            gather_scene_hook_sm64(self, gltf2_scene, blender_scene, export_settings)
        except:
            print(f'Exception at scene "{blender_scene.name}".')
            traceback.print_exc()
            raise

    def gather_node_hook(self, gltf2_node, blender_object, export_settings):
        try:
            gather_node_hook_sm64(self, gltf2_node, blender_object, export_settings)
        except:
            print(f'Exception at object "{blender_object.name}".')
            traceback.print_exc()
            raise

    def gather_mesh_hook(
        self, gltf2_mesh, blender_mesh, blender_object, vertex_groups, modifiers, materials, export_settings
    ):
        try:
            gather_mesh_hook_sm64(
                self, gltf2_mesh, blender_mesh, blender_object, vertex_groups, modifiers, materials, export_settings
            )
        except:
            print(f'Exception at mesh "{blender_mesh.name}" from the object "{blender_object.name}".')
            traceback.print_exc()
            raise

    def gather_skin_hook(self, gltf2_skin, blender_object, export_settings):
        try:
            gather_skin_hook_sm64(self, gltf2_skin, blender_object, export_settings)
        except:
            print(f'Exception at armature "{blender_object.name}".')
            traceback.print_exc()
            raise

    def gather_joint_hook(self, gltf2_node, blender_bone, export_settings):
        try:
            gather_joint_hook_sm64(self, gltf2_node, blender_bone, export_settings)
        except:
            print(f'Exception at joint/bone "{blender_bone.name}".')
            traceback.print_exc()
            raise

    def gather_material_pbr_metallic_roughness_hook(
        self, gltf2_material, blender_material, orm_texture, export_settings
    ):
        try:
            gather_material_pbr_metallic_roughness_hook_fast64(
                self, gltf2_material, blender_material, orm_texture, export_settings
            )
        except:
            print(f'Exception at material "{blender_material.name}".')
            traceback.print_exc()
            raise

    def gather_material_hook(self, gltf2_material, blender_material, export_settings):
        try:
            if blender_material.is_f3d and blender_material.mat_ver < 5:
                print(oldMaterialWarning)  # TODO: Maybe use some kind of warning pop-up.
            gather_material_hook_sm64(self, gltf2_material, blender_material, export_settings)
            gather_material_hook_fast64(self, gltf2_material, blender_material, export_settings)
        except:
            print(f'Exception at material "{blender_material.name}".')
            traceback.print_exc()
            raise
