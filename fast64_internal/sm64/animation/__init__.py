from .operators import (
    anim_ops_register,
    anim_ops_unregister,
)
from .properties import (
    anim_props_register,
    anim_props_unregister,
    SM64_ArmatureAnimProperties,
)
from .panels import (
    anim_panel_register,
    anim_panel_unregister,
)


def anim_register():
    anim_ops_register()
    anim_props_register()


def anim_unregister():
    anim_ops_unregister()
    anim_props_unregister()
