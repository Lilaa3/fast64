from .operators import operator_register, operator_unregister
from .properties import propertiesRegister, propertiesUnregister

def sm64_collision_register():
    operator_register()
    propertiesRegister()


def sm64_collision_unregister():
    operator_unregister()
    propertiesUnregister()
