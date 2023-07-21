from .operators import sm64_expansion_operator_register, sm64_expansion_operator_unregister
from .properties import sm64_expansion_properties_register, sm64_expansion_properties_unregister


def sm64_expansion_register():
    sm64_expansion_properties_register()
    sm64_expansion_operator_register()


def sm64_expansion_unregister():
    sm64_expansion_properties_unregister()
    sm64_expansion_operator_unregister()
