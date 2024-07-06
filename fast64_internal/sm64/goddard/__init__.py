from .panels import (
    goddard_panels_register,
    goddard_panels_unregister,
)
from .properties import (
    goddard_props_register,
    goddard_props_unregister,
    SM64_GoddardProperties,
    SM64_DynListProperties,
)

from .operators import (
    goddard_operators_register,
    goddard_operators_unregister,
)


def goddard_register():
    goddard_props_register()
    goddard_operators_register()


def goddard_unregister():
    goddard_props_unregister()
    goddard_operators_unregister()
