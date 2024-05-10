from .panels import collision_panels_register, collision_panels_unregister
from .operators import operator_register, operator_unregister
from .properties import properties_register, properties_unregister, SM64_MaterialCollisionProps

def collision_register():
    operator_register()
    properties_register()


def collision_unregister():
    operator_unregister()
    properties_unregister()
