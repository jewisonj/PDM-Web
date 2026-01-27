#!/usr/bin/env python3
"""
FreeCAD Sheet Metal Flattening Script - Docker CLI Compatible
Exports flat pattern OuterWire directly to DXF (no 2D projection needed)
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
print("FreeCAD Sheet Metal Flattening Tool - Docker CLI v2")
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

    # Determine face orientation to get correct 2D coordinates
    face_normal = flat_face.normalAt(0, 0)
    print(f"Face normal: ({face_normal.x:.3f}, {face_normal.y:.3f}, {face_normal.z:.3f})")

    # Determine which axes to use based on face orientation
    if abs(face_normal.z) > 0.9:
        use_axes = ('x', 'y')
        print("Face orientation: XY plane")
    elif abs(face_normal.y) > 0.9:
        use_axes = ('x', 'z')
        print("Face orientation: XZ plane")
    else:
        use_axes = ('y', 'z')
        print("Face orientation: YZ plane")

    def get_2d_coords(point):
        """Extract 2D coordinates based on face orientation"""
        if use_axes == ('x', 'y'):
            return FreeCAD.Vector(point.x, point.y, 0)
        elif use_axes == ('x', 'z'):
            return FreeCAD.Vector(point.x, point.z, 0)
        else:  # ('y', 'z')
            return FreeCAD.Vector(point.y, point.z, 0)

    # Get all points for bounding box calculation
    all_points = []
    for edge in flat_face.OuterWire.Edges:
        for vertex in edge.Vertexes:
            all_points.append(get_2d_coords(vertex.Point))

    min_x = min(p.x for p in all_points)
    max_x = max(p.x for p in all_points)
    min_y = min(p.y for p in all_points)
    max_y = max(p.y for p in all_points)

    part_width = max_x - min_x
    part_height = max_y - min_y

    print(f"\nFlat pattern dimensions:")
    print(f"  {part_width:.3f} mm x {part_height:.3f} mm")
    print(f"  ({part_width / 25.4:.3f}\" x {part_height / 25.4:.3f}\")")

    # Create 2D edges from the flat face outline
    print("\nCreating 2D geometry for DXF export...")

    edges_2d = []

    # Process outer wire
    for edge in flat_face.OuterWire.Edges:
        if hasattr(edge, 'Curve'):
            curve_type = edge.Curve.TypeId

            if 'Line' in curve_type:
                p1 = get_2d_coords(edge.Vertexes[0].Point)
                p2 = get_2d_coords(edge.Vertexes[1].Point)
                edges_2d.append(Part.makeLine(p1, p2))

            elif 'Circle' in curve_type:
                # Handle arcs and circles
                center = edge.Curve.Center
                radius = edge.Curve.Radius
                center_2d = get_2d_coords(center)

                if len(edge.Vertexes) == 2:
                    # Arc
                    p1 = get_2d_coords(edge.Vertexes[0].Point)
                    p2 = get_2d_coords(edge.Vertexes[1].Point)

                    # Create arc through 3 points (start, mid, end)
                    mid_param = (edge.FirstParameter + edge.LastParameter) / 2
                    mid_point = edge.valueAt(mid_param)
                    mid_2d = get_2d_coords(mid_point)

                    try:
                        arc = Part.Arc(p1, mid_2d, p2)
                        edges_2d.append(arc.toShape())
                    except:
                        # Fallback to line if arc creation fails
                        edges_2d.append(Part.makeLine(p1, p2))
                else:
                    # Full circle
                    circle = Part.makeCircle(radius, center_2d)
                    edges_2d.append(circle)

    # Process inner wires (holes)
    inner_wires = [w for w in flat_face.Wires if w.hashCode() != flat_face.OuterWire.hashCode()]
    for wire in inner_wires:
        for edge in wire.Edges:
            if hasattr(edge, 'Curve'):
                curve_type = edge.Curve.TypeId

                if 'Line' in curve_type:
                    p1 = get_2d_coords(edge.Vertexes[0].Point)
                    p2 = get_2d_coords(edge.Vertexes[1].Point)
                    edges_2d.append(Part.makeLine(p1, p2))

                elif 'Circle' in curve_type:
                    center = edge.Curve.Center
                    radius = edge.Curve.Radius
                    center_2d = get_2d_coords(center)

                    if len(edge.Vertexes) == 2:
                        p1 = get_2d_coords(edge.Vertexes[0].Point)
                        p2 = get_2d_coords(edge.Vertexes[1].Point)
                        mid_param = (edge.FirstParameter + edge.LastParameter) / 2
                        mid_point = edge.valueAt(mid_param)
                        mid_2d = get_2d_coords(mid_point)

                        try:
                            arc = Part.Arc(p1, mid_2d, p2)
                            edges_2d.append(arc.toShape())
                        except:
                            edges_2d.append(Part.makeLine(p1, p2))
                    else:
                        circle = Part.makeCircle(radius, center_2d)
                        edges_2d.append(circle)

    print(f"Created {len(edges_2d)} 2D edges")

    if not edges_2d:
        raise RuntimeError("No edges created for DXF export")

    # Create compound from edges
    compound = Part.makeCompound(edges_2d)

    # Apply scale for DXF export (mm to inches compensation)
    # DXF importers often assume inches, so we pre-scale by 1/25.4
    scale_factor = 1.0 / 25.4
    matrix = FreeCAD.Matrix()
    matrix.scale(scale_factor, scale_factor, scale_factor)
    scaled_compound = compound.transformGeometry(matrix)

    # Create object for export
    export_obj = doc.addObject("Part::Feature", "FlatPattern2D")
    export_obj.Shape = scaled_compound
    doc.recompute()

    # Export to DXF
    print(f"\nExporting to: {output_dxf}")
    importDXF.export([export_obj], output_dxf)

    if os.path.exists(output_dxf):
        size = os.path.getsize(output_dxf)
        print(f"SUCCESS: Created {output_dxf} ({size} bytes)")
        print(f"\nDXF dimensions (after scaling back ×25.4):")
        print(f"  {part_width:.3f} mm x {part_height:.3f} mm")
        print(f"  ({part_width / 25.4:.3f}\" x {part_height / 25.4:.3f}\")")
    else:
        raise RuntimeError("DXF file was not created")

    FreeCAD.closeDocument(doc.Name)
    return output_dxf


# Main execution
if __name__ == "__main__":
    args = sys.argv[1:]

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
