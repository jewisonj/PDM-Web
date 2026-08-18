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

# Log to file for debugging
_log_file = None
def debug_log(msg):
    global _log_file
    print(msg)
    if _log_file:
        _log_file.write(msg + "\n")
        _log_file.flush()

import FreeCAD
import Part
import Import
import importDXF


def flatten_sheetmetal(step_file, output_dxf=None, k_factor=0.35):
    """Flatten a sheet metal STEP file to DXF"""
    global _log_file

    step_file = os.path.abspath(step_file)

    # Open debug log file
    log_path = step_file.replace('.step', '_flatten_debug.log').replace('.stp', '_flatten_debug.log')
    try:
        _log_file = open(log_path, 'w')
        debug_log(f"Debug log: {log_path}")
    except:
        pass

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

    # Investigate the unfold result thoroughly
    print(f"\n--- UNFOLD RESULT INVESTIGATION ---")
    print(f"Unfold shape type: {unfold_shape.ShapeType}")
    print(f"  Faces: {len(unfold_shape.Faces)}")
    print(f"  Edges: {len(unfold_shape.Edges)}")
    print(f"  Wires: {len(unfold_shape.Wires)}")

    # Find ALL edges in the unfold, categorized by length
    all_unfold_edges = unfold_shape.Edges
    edge_by_length = sorted([(e.Length, e.Curve.TypeId if hasattr(e, 'Curve') else 'None') for e in all_unfold_edges])
    small_unfold_edges = [(l, t) for l, t in edge_by_length if l < 10.0]  # < 10mm
    if small_unfold_edges:
        print(f"  Small edges (<10mm) in entire unfold: {len(small_unfold_edges)}")
        for i, (length, ctype) in enumerate(small_unfold_edges[:10]):
            print(f"    [{i}] {length:.4f}mm - {ctype}")
    else:
        print(f"  No small edges (<10mm) in entire unfold shape")

    # Get flat face (largest face of unfolded shape)
    flat_faces = sorted(unfold_obj.Shape.Faces, key=lambda f: f.Area, reverse=True)
    flat_face = flat_faces[0]
    print(f"\nUsing largest face (area={flat_face.Area:.1f}mm^2)")
    print(f"  Face has {len(flat_face.Wires)} wires, {len(flat_face.Edges)} edges")

    # Examine each wire in detail
    for wi, wire in enumerate(flat_face.Wires):
        is_outer = wire.hashCode() == flat_face.OuterWire.hashCode()
        wire_type = "OUTER" if is_outer else "inner"
        wire_edges = wire.Edges
        edge_lengths = sorted([e.Length for e in wire_edges])
        small_wire_edges = [l for l in edge_lengths if l < 5.0]
        print(f"  Wire[{wi}] ({wire_type}): {len(wire_edges)} edges, "
              f"lengths {min(edge_lengths):.3f}mm to {max(edge_lengths):.3f}mm")
        if small_wire_edges:
            print(f"    Small edges (<5mm): {small_wire_edges}")

    # Determine face orientation and create proper 2D projection
    face_normal = flat_face.normalAt(0, 0)
    print(f"Face normal: ({face_normal.x:.3f}, {face_normal.y:.3f}, {face_normal.z:.3f})")

    # Scale factor: mm to inches
    scale_factor = 1.0 / 25.4

    # Check if face is aligned with a principal plane (within 5 degrees)
    if abs(face_normal.z) > 0.996:  # ~5 degrees from XY
        use_axes = ('x', 'y')
        print("Face orientation: XY plane (aligned)")
        def get_2d_coords(point):
            return FreeCAD.Vector(point.x * scale_factor, point.y * scale_factor, 0)
    elif abs(face_normal.y) > 0.996:  # ~5 degrees from XZ
        use_axes = ('x', 'z')
        print("Face orientation: XZ plane (aligned)")
        def get_2d_coords(point):
            return FreeCAD.Vector(point.x * scale_factor, point.z * scale_factor, 0)
    elif abs(face_normal.x) > 0.996:  # ~5 degrees from YZ
        use_axes = ('y', 'z')
        print("Face orientation: YZ plane (aligned)")
        def get_2d_coords(point):
            return FreeCAD.Vector(point.y * scale_factor, point.z * scale_factor, 0)
    else:
        # Face is tilted - project onto actual face plane
        print("Face orientation: TILTED - using face-plane projection")

        # Create local coordinate system on the face
        # Use principal axes from shape analysis or construct from normal
        # Pick an arbitrary vector not parallel to normal, then cross to get tangents
        if abs(face_normal.z) < 0.9:
            arbitrary = FreeCAD.Vector(0, 0, 1)
        else:
            arbitrary = FreeCAD.Vector(1, 0, 0)

        u_tangent = face_normal.cross(arbitrary).normalize()
        v_tangent = face_normal.cross(u_tangent).normalize()

        # Get face center for origin reference
        face_center = flat_face.CenterOfMass
        print(f"  u_tangent: ({u_tangent.x:.3f}, {u_tangent.y:.3f}, {u_tangent.z:.3f})")
        print(f"  v_tangent: ({v_tangent.x:.3f}, {v_tangent.y:.3f}, {v_tangent.z:.3f})")

        def get_2d_coords(point):
            # Vector from face center to point
            vec = FreeCAD.Vector(point.x - face_center.x,
                                  point.y - face_center.y,
                                  point.z - face_center.z)
            # Project onto face tangent directions
            u = vec.dot(u_tangent) * scale_factor
            v = vec.dot(v_tangent) * scale_factor
            return FreeCAD.Vector(u, v, 0)

        use_axes = ('face_u', 'face_v')

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
    print(f"  {part_width * 25.4:.3f} mm x {part_height * 25.4:.3f} mm")
    print(f"  ({part_width:.3f}\" x {part_height:.3f}\")")

    # Get original part bounding box for comparison
    orig_bb = imported_obj.Shape.BoundBox
    orig_dims = sorted([orig_bb.XLength, orig_bb.YLength, orig_bb.ZLength], reverse=True)
    orig_max_dim = orig_dims[0] / 25.4  # Convert to inches
    orig_mid_dim = orig_dims[1] / 25.4
    print(f"Original part bbox: {orig_dims[0]:.1f} x {orig_dims[1]:.1f} x {orig_dims[2]:.1f}mm")

    # Detect failed unfold: collapsed geometry OR unreasonably large result
    min_dim = min(part_width, part_height)
    max_dim = max(part_width, part_height)
    unfold_failed = False

    print(f"Unfold vs original: {max_dim:.2f}\" vs {orig_max_dim:.2f}\" (ratio: {max_dim/orig_max_dim:.1f}x)")

    if min_dim < 0.1 and max_dim > 1.0:  # Collapsed to a line
        print(f"\nWARNING: Unfold result is collapsed (aspect ratio {max_dim/max(min_dim, 0.001):.0f}:1)")
        unfold_failed = True
    elif max_dim > orig_max_dim * 5:  # Unfold >5x larger than original = garbage
        print(f"\nWARNING: Unfold result is unreasonably large ({max_dim:.1f}\" vs original {orig_max_dim:.1f}\")")
        unfold_failed = True

    if unfold_failed:
        print("Falling back to direct face export (part may have no bends or unfold failed)...")

        # Fall back to original imported object's largest face
        original_faces = sorted(imported_obj.Shape.Faces, key=lambda f: f.Area, reverse=True)
        flat_face = original_faces[0]

        # Recalculate face orientation for the fallback face
        face_normal = flat_face.normalAt(0, 0)
        print(f"Fallback face normal: ({face_normal.x:.3f}, {face_normal.y:.3f}, {face_normal.z:.3f})")
        if abs(face_normal.z) > 0.9:
            use_axes = ('x', 'y')
        elif abs(face_normal.y) > 0.9:
            use_axes = ('x', 'z')
        else:
            use_axes = ('y', 'z')

        # Recalculate coordinates from original face with corrected axes
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

        print(f"Direct face dimensions: {part_width:.3f}\" x {part_height:.3f}\"")

    # Create 2D edges from the flat face outline
    print("\nCreating 2D geometry for DXF export...")

    edges_2d = []
    edge_stats = {"Line": 0, "Arc": 0, "Circle": 0, "BSpline": 0, "Other": 0, "Fallback": 0, "Skipped": 0}

    def process_edge(edge, label=""):
        """Convert a 3D edge to 2D. Always produces output — falls back to
        a straight line between vertices if curved-edge processing fails."""
        if not hasattr(edge, 'Curve'):
            # No curve attribute — fall back to vertex-to-vertex line
            if len(edge.Vertexes) >= 2:
                p1 = get_2d_coords(edge.Vertexes[0].Point)
                p2 = get_2d_coords(edge.Vertexes[-1].Point)
                print(f"  {label}Edge has no Curve attr, fallback to line")
                edge_stats["Fallback"] += 1
                edges_2d.append(Part.makeLine(p1, p2))
            return

        curve_type = edge.Curve.TypeId

        if 'Line' in curve_type:
            # Handle line edges - some may have degenerate vertex data
            if len(edge.Vertexes) < 2:
                # The edge exists but has broken vertex topology
                # Recover geometry from curve parameters (this IS the real edge, not a guess)
                try:
                    start_pt = edge.valueAt(edge.FirstParameter)
                    end_pt = edge.valueAt(edge.LastParameter)
                    p1 = get_2d_coords(start_pt)
                    p2 = get_2d_coords(end_pt)
                    dist = p1.distanceToPoint(p2)
                    if dist > 1e-6:
                        # Log details to prove this is real geometry
                        print(f"  {label}Line with broken vertex refs, recovered from curve params:")
                        print(f"    Edge.Length={edge.Length:.3f}mm, Params=[{edge.FirstParameter:.6f}, {edge.LastParameter:.6f}]")
                        print(f"    Start: ({start_pt.x:.3f}, {start_pt.y:.3f}, {start_pt.z:.3f})mm")
                        print(f"    End:   ({end_pt.x:.3f}, {end_pt.y:.3f}, {end_pt.z:.3f})mm")
                        edges_2d.append(Part.makeLine(p1, p2))
                        edge_stats["Line"] += 1
                        return
                except Exception as ex:
                    print(f"  {label}SKIP: Could not recover line geometry: {ex}")
                print(f"  {label}SKIP: Line with <2 vertices and no valid parameters")
                edge_stats["Skipped"] += 1
                return
            p1 = get_2d_coords(edge.Vertexes[0].Point)
            p2 = get_2d_coords(edge.Vertexes[1].Point)
            dist = p1.distanceToPoint(p2)
            # Handle zero-length edges - try to recover from curve parameters
            if dist < 1e-6:
                # The 2D projection might collapse edges - try using 3D edge length
                if edge.Length > 0.1:  # Edge has real 3D length
                    try:
                        start_pt = edge.valueAt(edge.FirstParameter)
                        end_pt = edge.valueAt(edge.LastParameter)
                        p1 = get_2d_coords(start_pt)
                        p2 = get_2d_coords(end_pt)
                        dist = p1.distanceToPoint(p2)
                        if dist > 1e-6:
                            print(f"  {label}Line recovered from params (3D length={edge.Length:.2f}mm)")
                            edges_2d.append(Part.makeLine(p1, p2))
                            edge_stats["Line"] += 1
                            return
                    except:
                        pass
                print(f"  {label}SKIP: Zero-length line ({dist:.8f}\")")
                edge_stats["Skipped"] += 1
                return
            edges_2d.append(Part.makeLine(p1, p2))
            edge_stats["Line"] += 1

        elif 'Circle' in curve_type:
            if len(edge.Vertexes) == 2:
                # Arc
                p1 = get_2d_coords(edge.Vertexes[0].Point)
                p2 = get_2d_coords(edge.Vertexes[1].Point)
                mid_param = (edge.FirstParameter + edge.LastParameter) / 2
                mid_point = edge.valueAt(mid_param)
                mid_2d = get_2d_coords(mid_point)

                try:
                    arc = Part.Arc(p1, mid_2d, p2)
                    edges_2d.append(arc.toShape())
                    edge_stats["Arc"] += 1
                except Exception as ex:
                    # Skip zero-length edges (coincident points)
                    dist = p1.distanceToPoint(p2)
                    if dist < 1e-6:
                        print(f"  {label}SKIP: Arc with coincident endpoints ({dist:.8f}\")")
                        edge_stats["Skipped"] += 1
                        return
                    print(f"  {label}Arc failed ({ex}), using line fallback")
                    edges_2d.append(Part.makeLine(p1, p2))
                    edge_stats["Fallback"] += 1
            elif len(edge.Vertexes) == 0:
                # Full circle
                radius = edge.Curve.Radius * scale_factor
                center_2d = get_2d_coords(edge.Curve.Center)
                circle = Part.makeCircle(radius, center_2d)
                edges_2d.append(circle)
                edge_stats["Circle"] += 1
            else:
                # Unexpected vertex count — discretize
                _discretize_edge(edge, label)

        elif 'BSpline' in curve_type:
            _discretize_edge(edge, label)
            edge_stats["BSpline"] += 1

        else:
            print(f"  {label}Unknown curve type '{curve_type}', discretizing")
            _discretize_edge(edge, label)
            edge_stats["Other"] += 1

    def _discretize_edge(edge, label=""):
        """Discretize an edge to polyline points. Falls back to a straight
        line between start/end vertices if discretization fails."""
        try:
            points = edge.discretize(Number=20)
            scaled_pts = [get_2d_coords(p) for p in points]
            if len(scaled_pts) >= 2:
                wire = Part.makePolygon(scaled_pts)
                for e in wire.Edges:
                    edges_2d.append(e)
                return
        except Exception as ex:
            print(f"  {label}WARNING: discretize() failed: {ex}")

        # Fallback: straight line between start and end vertices
        if len(edge.Vertexes) >= 2:
            p1 = get_2d_coords(edge.Vertexes[0].Point)
            p2 = get_2d_coords(edge.Vertexes[-1].Point)
            # Skip zero-length edges (coincident points)
            if p1.distanceToPoint(p2) < 1e-6:
                edge_stats["Skipped"] += 1
                return
            edges_2d.append(Part.makeLine(p1, p2))
            edge_stats["Fallback"] += 1
            print(f"  {label}Fallback: line from vertex to vertex")

    # Process outer wire - first analyze edge lengths to understand geometry
    outer_edges = flat_face.OuterWire.Edges
    edge_lengths = [(e.Length, e.Curve.TypeId if hasattr(e, 'Curve') else 'NoCurve') for e in outer_edges]
    lengths_only = [l for l, t in edge_lengths]
    min_len = min(lengths_only) if lengths_only else 0
    max_len = max(lengths_only) if lengths_only else 0
    small_edges = [(l, t) for l, t in edge_lengths if l < 5.0]  # < 5mm edges

    print(f"\nOuterWire Analysis:")
    print(f"  Total edges: {len(outer_edges)}")
    print(f"  Edge lengths: {min_len:.3f}mm to {max_len:.3f}mm")
    debug_log(f"OuterWire: {len(outer_edges)} edges, lengths {min_len:.3f}mm to {max_len:.3f}mm")

    if small_edges:
        print(f"  Small edges (<5mm): {len(small_edges)} - these may be bend reliefs!")
        for i, (length, ctype) in enumerate(sorted(small_edges, key=lambda x: x[0])):
            msg = f"    [{i}] {length:.4f}mm ({length/25.4:.5f}in) - {ctype}"
            print(msg)
            debug_log(msg)
    else:
        print("  No small edges (<5mm) found - bend reliefs may be missing from source!")

    # Check for suspicious diagonals in OuterWire (unfolder artifacts)
    # If any edge spans more than 50% of the part diagonally, use discretization
    part_diagonal = ((part_width**2 + part_height**2)**0.5)
    has_suspicious_diagonals = False
    for edge in outer_edges:
        if len(edge.Vertexes) >= 2:
            p1 = get_2d_coords(edge.Vertexes[0].Point)
            p2 = get_2d_coords(edge.Vertexes[1].Point)
            edge_len = p1.distanceToPoint(p2)
            # Check if edge is diagonal (not axis-aligned) and spans large distance
            dx = abs(p1.x - p2.x)
            dy = abs(p1.y - p2.y)
            if edge_len > part_diagonal * 0.3 and min(dx, dy) > 0.1:  # Diagonal if both dx and dy significant
                print(f"  WARNING: Suspicious diagonal edge detected ({edge_len:.2f}\" across part)")
                has_suspicious_diagonals = True
                break

    if has_suspicious_diagonals:
        print("  Using wire discretization to avoid unfolder artifacts...")
        # Discretize the outer wire to get proper boundary
        try:
            # Discretize with enough points to capture detail
            outer_points = flat_face.OuterWire.discretize(Distance=2.5)  # 2.5mm resolution (0.1")
            scaled_pts = [get_2d_coords(p) for p in outer_points]
            if len(scaled_pts) >= 3:
                # Close the polygon if needed
                if scaled_pts[0].distanceToPoint(scaled_pts[-1]) > 1e-6:
                    scaled_pts.append(scaled_pts[0])
                outer_poly = Part.makePolygon(scaled_pts)
                for e in outer_poly.Edges:
                    edges_2d.append(e)
                edge_stats["Line"] += len(outer_poly.Edges)
                print(f"  Discretized outer wire: {len(scaled_pts)} points, {len(outer_poly.Edges)} edges")
        except Exception as ex:
            print(f"  Discretization failed ({ex}), falling back to edge processing")
            for i, edge in enumerate(outer_edges):
                process_edge(edge, f"Outer[{i}] ")
    else:
        for i, edge in enumerate(outer_edges):
            process_edge(edge, f"Outer[{i}] ")

    # Process inner wires (holes)
    inner_wires = [w for w in flat_face.Wires if w.hashCode() != flat_face.OuterWire.hashCode()]
    for wi, wire in enumerate(inner_wires):
        # Check if this wire has broken vertices or suspicious edges
        wire_has_issues = False
        for edge in wire.Edges:
            if len(edge.Vertexes) < 2:
                wire_has_issues = True
                break
            # Check for suspicious diagonals in hole
            p1 = get_2d_coords(edge.Vertexes[0].Point)
            p2 = get_2d_coords(edge.Vertexes[1].Point)
            dx = abs(p1.x - p2.x)
            dy = abs(p1.y - p2.y)
            edge_len = p1.distanceToPoint(p2)
            if edge_len > 5.0 and min(dx, dy) > 0.5:  # Large diagonal in a hole
                wire_has_issues = True
                break

        if wire_has_issues:
            # Use discretization for this hole
            try:
                hole_points = wire.discretize(Distance=1.0)  # 1mm resolution for holes
                scaled_pts = [get_2d_coords(p) for p in hole_points]
                if len(scaled_pts) >= 3:
                    if scaled_pts[0].distanceToPoint(scaled_pts[-1]) > 1e-6:
                        scaled_pts.append(scaled_pts[0])
                    hole_poly = Part.makePolygon(scaled_pts)
                    for e in hole_poly.Edges:
                        edges_2d.append(e)
                    edge_stats["Line"] += len(hole_poly.Edges)
                    continue  # Skip normal edge processing
            except:
                pass  # Fall through to normal processing

        # Normal edge-by-edge processing
        for ei, edge in enumerate(wire.Edges):
            process_edge(edge, f"Hole[{wi}][{ei}] ")


    total_input = len(outer_edges) + sum(len(w.Edges) for w in inner_wires)
    print(f"\nEdge Processing Summary:")
    print(f"  Input edges:  {total_input}")
    print(f"  Output edges: {len(edges_2d)}")
    print(f"  Edge types: {', '.join(f'{k}={v}' for k, v in edge_stats.items() if v > 0)}")
    if edge_stats["Skipped"] > 0:
        print(f"  WARNING: {edge_stats['Skipped']} edges SKIPPED (too small or degenerate)")

    if not edges_2d:
        raise RuntimeError("No edges created for DXF export")

    # Create compound from edges (already scaled to inches during creation)
    compound = Part.makeCompound(edges_2d)

    # Analyze contours - report open vs closed (no auto-repair)
    print("\n" + "-" * 40)
    print("CONTOUR ANALYSIS")
    print("-" * 40)
    try:
        sorted_edges = Part.sortEdges(edges_2d)
        open_contours = 0
        closed_contours = 0
        for edge_group in sorted_edges:
            try:
                wire = Part.Wire(edge_group)
                if wire.isClosed():
                    closed_contours += 1
                else:
                    open_contours += 1
            except:
                open_contours += 1

        print(f"  Closed contours: {closed_contours}")
        print(f"  Open contours:   {open_contours}")
        if open_contours > 0:
            print(f"  WARNING: {open_contours} open contours = geometry may be incomplete")
        debug_log(f"CONTOUR RESULT: {closed_contours} closed, {open_contours} open")
    except Exception as e:
        print(f"  Contour analysis failed: {e}")
    print("-" * 40)

    # Create object for export
    export_obj = doc.addObject("Part::Feature", "FlatPattern2D")
    export_obj.Shape = compound
    doc.recompute()

    # Export to DXF
    print(f"\nExporting to: {output_dxf}")
    importDXF.export([export_obj], output_dxf)

    if os.path.exists(output_dxf):
        size = os.path.getsize(output_dxf)
        print(f"SUCCESS: Created {output_dxf} ({size} bytes)")
        print(f"\nDXF dimensions (inches):")
        print(f"  {part_width:.3f}\" x {part_height:.3f}\"")
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
