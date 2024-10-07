"""Usually this would be panel.py but there is no actual panel since we only draw in the tools panel."""

from bpy.types import UILayout, Context

from .operators import F3D_ConvertF3DToBSDF, F3D_ConvertBSDFToF3D


def bsdf_converter_panel_draw(layout: UILayout, _context: Context):
    col = layout.column()
    F3D_ConvertF3DToBSDF.draw_props(col)
    F3D_ConvertBSDFToF3D.draw_props(col)
