from .operators import sm64_anim_operator_register, sm64_anim_operator_unregister
from .properties import sm64_anim_properties_register, sm64_anim_properties_unregister

def sm64_anim_register():
    sm64_anim_properties_register()
    sm64_anim_operator_register()


def sm64_anim_unregister():
    sm64_anim_properties_unregister()
    sm64_anim_operator_unregister()
