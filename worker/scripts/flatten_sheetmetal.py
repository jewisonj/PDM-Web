#!/usr/bin/env python3
"""
FreeCAD Sheet Metal Flattening Script - Docker CLI Compatible
Uses Shape.transformGeometry() + Draft.makeShape2DView() for reliable output.
(Restored from WORKING FIX version - manual edge extraction was producing
 incorrect dimensions on some parts.)
"""

import sys
import os

# Add the scripts directory to path for setup_stubs
scripts_dir = os.path.dirname(os.path.abspath(__file__))
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

# Set up stubs for missing modules BEFORE importing FreeCAD
import setup_stubs

# Add FreeCAD lib to path
if '/usr/local/lib' not in sys.path:
    sys.path.insert(0, '/usr/local/lib')

# Add SheetMetal addon to path
sheetmetal_path = '/root/.FreeCAD/Mod/sheetmetal'
if sheetmetal_path not in sys.path:
    sys.path.insert(0, sheetmetal_path)

# Disable GUI
try:
    import FreeCAD
    FreeCAD.GuiUp = False
except:
    pass

print("=" * 60)
print("FreeCAD Sheet Metal Flattening Tool - Docker CLI (Working Fix)")
print("=" * 60)

import FreeCAD
import Part
import Import
import importDXF


def flatten_sheetmetal(step_file, output_dxf=None, k_factor=0.35):
    """Flatten a sheet metal STEP file to DXF"""

    step_file = os.path.abspath(step_file)

    if not os.path.exists(step_file):
        raise FileNotFoundError(f"Input file not found: {step_file}")

    if output_dxf is None:
        base_name = os.path.splitext(step_file)[0]
        output_dxf = f"{base_name}_flat.dxf"
    else:
        output_dxf = os.path.abspath(output_dxf)

    print(f"\nProcessing: {step_file}")
    print(f"Output: {output_dxf}")

    doc = FreeCAD.newDocument("SheetMetalFlatten")

    # Import STEP
    Import.insert(step_file, doc.Name)
    imported_obj = doc.Objects[0]
    print(f"Imported: {imported_obj.Label}")

    # Unfold with SheetMetal
    import SheetMetalUnfolder

    faces = imported_obj.Shape.Faces
    largest_face = max(faces, key=lambda f: f.Area)
    largest_face_index = faces.index(largest_face)
    face_name = f"Face{largest_face_index + 1}"

    print(f"Using face: {face_name} (largest by area)")

    k_factor_lookup = {0.0: k_factor, 1.0: k_factor, 10.0: k_factor}
    unfold_result = SheetMetalUnfolder.getUnfold(
        k_factor_lookup,
        imported_obj,
        face_name,
        k_factor
    )

    unfold_shape = unfold_result[0] if isinstance(unfold_result, tuple) else unfold_result

    unfold_obj = doc.addObject("Part::Feature", "Unfold")
    unfold_obj.Shape = unfold_shape
    doc.recompute()

    # Get flat face (largest face of unfolded shape)
    flat_faces = sorted(unfold_obj.Shape.Faces, key=lambda f: f.Area, reverse=True)
    flat_face = flat_faces[0]

    bbox = flat_face.BoundBox
    print(f"\nOriginal dimensions:")
    print(f"  {bbox.XLength:.3f} mm x {bbox.YLength:.3f} mm")
    print(f"  ({bbox.XLength/25.4:.3f}\" x {bbox.YLength/25.4:.3f}\")")

    # Create flat face object
    flat_obj = doc.addObject("Part::Feature", "FlatFace")
    flat_obj.Shape = flat_face
    doc.recompute()

    # ===========================================
    # Use Matrix transformation to scale mm -> inches
    # (transformGeometry converts arcs to BSplines but preserves
    #  correct dimensions, which is the priority)
    # ===========================================
    print("\nApplying 1/25.4 scale compensation...")

    scale_factor = 1.0 / 25.4

    # Create scaling matrix
    matrix = FreeCAD.Matrix()
    matrix.scale(scale_factor, scale_factor, scale_factor)

    # Apply transformation to a COPY of the shape
    scaled_shape = flat_obj.Shape.transformGeometry(matrix)

    scaled_obj = doc.addObject("Part::Feature", "ScaledFlat")
    scaled_obj.Shape = scaled_shape
    doc.recompute()

    scaled_bbox = scaled_obj.Shape.BoundBox
    print(f"Scaled to: {scaled_bbox.XLength:.3f} x {scaled_bbox.YLength:.3f}")
    print(f"After DXF export (x25.4): {scaled_bbox.XLength*25.4:.3f} x {scaled_bbox.YLength*25.4:.3f} mm")

    # Create 2D projection from scaled geometry
    print("\nCreating 2D projection...")
    import Draft

    face_normal = scaled_shape.Faces[0].normalAt(0, 0)
    projection = Draft.makeShape2DView(scaled_obj, face_normal)
    doc.recompute()

    print(f"Projection created with {len(projection.Shape.Edges)} edges")

    # Export
    print(f"\nExporting to: {output_dxf}")
    importDXF.export([projection], output_dxf)

    if os.path.exists(output_dxf):
        size = os.path.getsize(output_dxf)
        print(f"SUCCESS: Created {output_dxf} ({size} bytes)")
        print(f"\nDXF dimensions (inches):")
        print(f"  {bbox.XLength/25.4:.3f}\" x {bbox.YLength/25.4:.3f}\"")
    else:
        raise RuntimeError("DXF file was not created")

    FreeCAD.closeDocument(doc.Name)
    return output_dxf


# Main execution - check for both direct python and FreeCADCmd invocation
# FreeCADCmd sets __name__ to the module name, not "__main__"
if __name__ == "__main__" or __name__ == "flatten_sheetmetal":
    # FreeCADCmd includes the script path in sys.argv, strip it
    args = sys.argv[1:]
    args = [a for a in args if not a.endswith('.py')]

    if len(args) < 1:
        print("\nUsage: python flatten_sheetmetal.py input.step [output.dxf] [k_factor]")
        sys.exit(1)

    step_file = args[0]
    output_dxf = args[1] if len(args) > 1 else None
    k_factor = float(args[2]) if len(args) > 2 else 0.35

    try:
        result = flatten_sheetmetal(step_file, output_dxf, k_factor)
        print("\n" + "=" * 60)
        print(f"SUCCESS! DXF created: {result}")
        print("=" * 60)
    except Exception as e:
        print("\n" + "=" * 60)
        print(f"FAILED: {str(e)}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        sys.exit(1)
