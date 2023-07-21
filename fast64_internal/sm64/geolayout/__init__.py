from .sm64_geolayout_writer import sm64_geo_writer_register, sm64_geo_writer_unregister
from .operators import operatorRegister, operatorUnregister
from .properties import propertiesRegister, propertiesUnregister

def sm64_geolayout_register():
    operatorRegister()
    propertiesRegister()
    sm64_geo_writer_register()


def sm64_geolayout_unregister():
    operatorUnregister()
    propertiesUnregister()
    sm64_geo_writer_unregister()
