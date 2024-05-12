from .operators import (
    anim_operator_register,
    anim_operator_unregister,
)
from .properties import (
    anim_props_register,
    anim_props_unregister,
)
from .panels import (
    anim_panel_register,
    anim_panel_unregister,
)


def anim_register():
    anim_operator_register()
    anim_props_register()


def anim_unregister():
    anim_operator_unregister()
    anim_props_unregister()
