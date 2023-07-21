from .operators import operatorRegister, operatorUnregister
from .properties import propertiesRegister, propertiesUnregister

def sm64_collision_register():
    operatorRegister()
    propertiesRegister()


def sm64_collision_unregister():
    operatorUnregister()
    propertiesUnregister()
