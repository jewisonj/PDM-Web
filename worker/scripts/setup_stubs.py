"""
FreeCAD Module Stubs for CLI environments
Creates stub modules for TechDraw/Drawing that may not be available
in stripped-down FreeCAD CLI builds.
"""

import sys
from types import ModuleType


def setup_stubs():
    """Set up stub modules for missing FreeCAD workbenches"""

    # Create TechDraw stub
    if 'TechDraw' not in sys.modules:
        techdraw = ModuleType('TechDraw')

        def projectEx(*args, **kwargs):
            """Stub for TechDraw.projectEx - not used in unfold operations"""
            raise NotImplementedError(
                "TechDraw.projectEx is not available in this FreeCAD build. "
                "This function is not needed for basic unfold operations."
            )

        techdraw.projectEx = projectEx
        sys.modules['TechDraw'] = techdraw

    # Create Drawing stub (deprecated, but some code still references it)
    if 'Drawing' not in sys.modules:
        drawing = ModuleType('Drawing')

        def projectEx(*args, **kwargs):
            """Stub for Drawing.projectEx - not used in unfold operations"""
            raise NotImplementedError(
                "Drawing.projectEx is not available in this FreeCAD build. "
                "This function is not needed for basic unfold operations."
            )

        drawing.projectEx = projectEx
        sys.modules['Drawing'] = drawing


# Auto-setup when imported
setup_stubs()
