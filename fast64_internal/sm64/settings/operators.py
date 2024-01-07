from bpy.utils import register_class, unregister_class
from bpy.types import Context, Operator
from bpy.props import StringProperty
from ...utility import (
    raisePluginError,
)

from ...repo_settings import load_repo_settings, save_repo_settings


class SM64_SaveRepoSettings(Operator):
    bl_idname = "scene.sm64_save_repo_settings"
    bl_label = "Save Repo Settings"
    bl_options = {"REGISTER", "UNDO", "PRESET"}
    bl_description = "Save repo settings to a file, by default to YOUR_DECOMP_PATH/fast64.json"

    path: StringProperty(name="Settings File Path", subtype="FILE_PATH")

    def execute(self, context: Context):
        try:
            save_repo_settings(context.scene, self.path)
            return {"FINISHED"}
        except Exception as e:
            raisePluginError(self, e)
            return {"CANCELLED"}


class SM64_LoadRepoSettings(Operator):
    bl_idname = "scene.sm64_load_repo_settings"
    bl_label = "Load Repo Settings"
    bl_options = {"REGISTER", "UNDO", "PRESET"}
    bl_description = "Load repo settings to a file, by default to YOUR_DECOMP_PATH/fast64.json"

    path: StringProperty(name="Settings File Path", subtype="FILE_PATH")

    def execute(self, context: Context):
        try:
            load_repo_settings(context.scene, self.path)
            return {"FINISHED"}
        except Exception as e:
            raisePluginError(self, e)
            return {"CANCELLED"}


classes = (
    SM64_SaveRepoSettings,
    SM64_LoadRepoSettings,
)


def settings_operators_register():
    for cls in classes:
        register_class(cls)


def settings_operators_unregister():
    for cls in classes:
        unregister_class(cls)
