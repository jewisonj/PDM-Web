#!/usr/bin/env python3
"""
FreeCAD Bend Line Drawing Generator - Portable Version
Creates an SVG technical drawing showing the flat pattern with bend lines and dimensions
Compatible with both installed and portable FreeCAD versions
"""

import sys
import os
import math

# Disable GUI if running headless
try:
    import FreeCAD
    FreeCAD.GuiUp = False
except:
    pass

print("="*60)
print("FreeCAD Bend Line Drawing Generator (Portable)")
print("="*60)

# Import FreeCAD modules
try:
    import FreeCAD
    import Part
    import Import
    print(f"SUCCESS FreeCAD {FreeCAD.Version()} loaded successfully")
except Exception as e:
    print(f"ERROR Failed to load FreeCAD modules: {e}")
    sys.exit(1)

def create_bent_part_preview(obj, width=50, height=50):
    """Create a simple wireframe preview of the bent part"""
    try:
        # Get bounding box for the bent part
        bbox = obj.Shape.BoundBox
        
        # Calculate isometric projection angles (30 degrees)
        import math
        cos30 = math.cos(math.radians(30))
        sin30 = math.sin(math.radians(30))
        
        def project_point(p):
            """Project a 3D point to isometric 2D coordinates"""
            x_iso = (p.x * cos30 - p.z * cos30)
            y_iso = (p.y + p.x * sin30 + p.z * sin30)
            return x_iso, y_iso
        
        # Find all edges and project them
        edges = []
        for edge in obj.Shape.Edges:
            try:
                edge_segments = []
                
                if hasattr(edge, 'Curve'):
                    if 'Line' in edge.Curve.TypeId:
                        # Straight line edge
                        p1 = edge.Vertexes[0].Point
                        p2 = edge.Vertexes[1].Point
                        
                        x1_iso, y1_iso = project_point(p1)
                        x2_iso, y2_iso = project_point(p2)
                        avg_z = (p1.z + p2.z) / 2
                        
                        edge_segments.append(((x1_iso, y1_iso), (x2_iso, y2_iso), avg_z))
                    
                    elif 'Circle' in edge.Curve.TypeId or 'BSpline' in edge.Curve.TypeId or 'Bezier' in edge.Curve.TypeId:
                        # Curved edge - discretize into short segments
                        num_segments = 12  # Number of segments to approximate the curve
                        
                        param_range = edge.LastParameter - edge.FirstParameter
                        for i in range(num_segments):
                            t1 = edge.FirstParameter + (i / num_segments) * param_range
                            t2 = edge.FirstParameter + ((i + 1) / num_segments) * param_range
                            
                            p1 = edge.valueAt(t1)
                            p2 = edge.valueAt(t2)
                            
                            x1_iso, y1_iso = project_point(p1)
                            x2_iso, y2_iso = project_point(p2)
                            avg_z = (p1.z + p2.z) / 2
                            
                            edge_segments.append(((x1_iso, y1_iso), (x2_iso, y2_iso), avg_z))
                
                edges.extend(edge_segments)
            except:
                pass
        
        if not edges:
            return None
        
        # Sort edges by z-depth (back to front)
        edges.sort(key=lambda e: e[2])
        
        # Find bounds of projected edges
        all_x = [p[0] for edge in edges for p in [edge[0], edge[1]]]
        all_y = [p[1] for edge in edges for p in [edge[0], edge[1]]]
        
        min_x, max_x = min(all_x), max(all_x)
        min_y, max_y = min(all_y), max(all_y)
        
        range_x = max_x - min_x
        range_y = max_y - min_y
        
        if range_x == 0 or range_y == 0:
            return None
        
        # Scale to fit in the preview box with margins
        margin = 5
        scale = min((width - 2*margin) / range_x, (height - 2*margin) / range_y)
        
        # Determine threshold for visible lines - show ALL edges equally
        min_z = min(e[2] for e in edges)
        max_z = max(e[2] for e in edges)
        
        # Create SVG group with wireframe
        svg_lines = []
        svg_lines.append(f'  <g id="bent_preview">')
        svg_lines.append(f'    <rect x="0" y="0" width="{width}" height="{height}" fill="white" stroke="black" stroke-width="0.5"/>')
        svg_lines.append(f'    <text x="{width/2}" y="8" text-anchor="middle" font-size="4" font-weight="bold">Bent State</text>')
        
        # Draw all edges with same formatting
        for (x1, y1), (x2, y2), z in edges:
            # Transform to SVG coordinates
            svg_x1 = margin + (x1 - min_x) * scale
            svg_y1 = height - margin - (y1 - min_y) * scale
            svg_x2 = margin + (x2 - min_x) * scale
            svg_y2 = height - margin - (y2 - min_y) * scale
            
            # All lines use the same style
            svg_lines.append(f'    <line x1="{svg_x1:.1f}" y1="{svg_y1:.1f}" x2="{svg_x2:.1f}" y2="{svg_y2:.1f}" stroke="black" stroke-width="0.3"/>')
        
        svg_lines.append(f'  </g>')
        
        return '\n'.join(svg_lines)
        
    except Exception as e:
        print(f"  Warning: Could not create bent part preview: {e}")
        return None


def determine_correct_sweep(arc_edge, angle_span, to_svg_func):
    """
    Determine the correct sweep flag for an arc using the cross product method.
    
    The key insight: In SVG, the sweep flag determines which side of the chord 
    the arc bulges toward. We check which side of the chord the center lies on
    using cross product, then draw the arc on the OPPOSITE side.
    
    Returns: (sweep_flag, large_arc_flag)
    """
    try:
        # Calculate large arc flag based on angle span
        large_arc = 1 if abs(angle_span) > math.pi else 0
        
        # Get arc properties in 3D space
        center_3d = arc_edge.Curve.Center
        p1_3d = arc_edge.Vertexes[0].Point  # Start point
        p2_3d = arc_edge.Vertexes[1].Point  # End point
        
        # Transform to 2D SVG coordinates
        center_x, center_y = to_svg_func(center_3d)
        p1_x, p1_y = to_svg_func(p1_3d)
        p2_x, p2_y = to_svg_func(p2_3d)
        
        # Chord vector (from p1 to p2)
        chord_x = p2_x - p1_x
        chord_y = p2_y - p1_y
        
        # Vector from p1 to center
        to_center_x = center_x - p1_x
        to_center_y = center_y - p1_y
        
        # Cross product in 2D: chord × to_center
        # If positive: center is to the LEFT of the chord (counter-clockwise side)
        # If negative: center is to the RIGHT of the chord (clockwise side)
        cross_product = chord_x * to_center_y - chord_y * to_center_x
        
        # In SVG:
        # sweep=0 means: draw arc to the left of the chord (counter-clockwise)
        # sweep=1 means: draw arc to the right of the chord (clockwise)
        
        # The sweep flag indicates which side of the chord to draw the arc
        # BUT we want the arc to bulge AWAY from the center, not toward it
        # So if center is on the left (cross > 0), we want to draw on the right: sweep=1
        # If center is on the right (cross < 0), we want to draw on the left: sweep=0
        if cross_product > 0:
            sweep = 1  # Center on left, arc on right
        else:
            sweep = 0  # Center on right, arc on left
        
        return sweep, large_arc
        
    except Exception as e:
        print(f"    Warning: Cross product sweep calculation failed: {e}")
        # Fallback to angle-based
        large_arc = 1 if abs(angle_span) > math.pi else 0
        sweep = 0 if angle_span > 0 else 1
        return sweep, large_arc


def create_svg_drawing(flat_face, fold_lines, output_file, title="Flat Pattern with Bend Lines", k_factor=0.35, thickness=None, bent_preview_svg=None):
    """Create an SVG drawing with the flat pattern, bend lines, and dimensions"""
    
    def determine_gauge(thickness_inches):
        """
        Determine sheet metal gauge from thickness in inches.
        Returns tuple: (gauge, is_standard_gauge)
        is_standard_gauge indicates if the thickness exactly matches a standard gauge.
        """
        # Sheet metal gauge chart (gauge: thickness in inches)
        gauge_chart = {
            10: 0.1345,
            11: 0.1196,
            12: 0.1046,
            13: 0.0897,
            14: 0.0747,
            15: 0.0673,
            16: 0.0598,
            17: 0.0538,
            18: 0.0478,
            19: 0.0418,
            20: 0.0359,
            21: 0.0329,
            22: 0.0299
        }
        
        # Find closest gauge (within tolerance)
        tolerance = 0.003  # 3 thousandths tolerance
        closest_gauge = None
        min_diff = float('inf')
        
        for gauge, std_thickness in gauge_chart.items():
            diff = abs(thickness_inches - std_thickness)
            if diff < min_diff:
                min_diff = diff
                closest_gauge = gauge
        
        is_standard = min_diff <= tolerance
        return closest_gauge, is_standard


    def decimal_to_fraction(decimal_inches):
        """Convert decimal inches to fractional format (nearest 1/16")"""
        # Round to nearest 1/16"
        sixteenths = round(decimal_inches * 16)
        
        # Separate whole inches and fractional part
        whole = sixteenths // 16
        remainder = sixteenths % 16
        
        # Simplify the fraction
        if remainder == 0:
            return f'{whole}"' if whole > 0 else '0"'
        
        # Simplify fraction (reduce 16ths to 8ths, 4ths, or halves)
        if remainder == 8:
            frac = "1/2"
        elif remainder == 4 or remainder == 12:
            frac = f"{remainder//4}/4"
        elif remainder % 2 == 0:
            frac = f"{remainder//2}/8"
        else:
            frac = f"{remainder}/16"
        
        if whole > 0:
            return f'{whole}-{frac}"'
        else:
            return f'{frac}"'
    
    face_normal = flat_face.normalAt(0, 0)
    print(f"  Face normal: ({face_normal.x:.3f}, {face_normal.y:.3f}, {face_normal.z:.3f})")
    
    if abs(face_normal.z) > 0.9:
        use_axes = ('x', 'y')
        print(f"  Face orientation: XY plane")
    elif abs(face_normal.y) > 0.9:
        use_axes = ('x', 'z')
        print(f"  Face orientation: XZ plane")
    else:
        use_axes = ('y', 'z')
        print(f"  Face orientation: YZ plane")
    
    def get_coords(point):
        if use_axes == ('x', 'y'):
            return point.x, point.y
        elif use_axes == ('x', 'z'):
            return point.x, point.z
        else:
            return point.y, point.z
    
    all_points = []
    for edge in flat_face.Edges:
        for vertex in edge.Vertexes:
            all_points.append(get_coords(vertex.Point))
    
    min_x = min(p[0] for p in all_points)
    max_x = max(p[0] for p in all_points)
    min_y = min(p[1] for p in all_points)
    max_y = max(p[1] for p in all_points)
    
    part_width = max_x - min_x
    part_height = max_y - min_y
    
    # Rotate 90° if height > width to better use landscape page
    if part_height > part_width:
        print(f"  Part dimensions (before rotation): {part_width:.2f} x {part_height:.2f} mm")
        print(f"  Rotating 90° to optimize page usage...")
        
        # Swap width and height
        part_width, part_height = part_height, part_width
        
        # Swap min/max values
        min_x, min_y = min_y, min_x
        max_x, max_y = max_y, max_x
        
        # Create new get_coords function that swaps and negates y to rotate
        original_get_coords = get_coords
        def get_coords(point):
            x, y = original_get_coords(point)
            return y, -x  # Rotate 90° clockwise
        
        # Recalculate all points with rotation
        all_points = []
        for edge in flat_face.Edges:
            for vertex in edge.Vertexes:
                all_points.append(get_coords(vertex.Point))
        
        min_x = min(p[0] for p in all_points)
        max_x = max(p[0] for p in all_points)
        min_y = min(p[1] for p in all_points)
        max_y = max(p[1] for p in all_points)
        
        part_width = max_x - min_x
        part_height = max_y - min_y
    
    part_max_dim = max(part_width, part_height)
    
    print(f"  Part dimensions (final): {part_width:.2f} x {part_height:.2f} mm")
    
    # Page size for 8.5x11 landscape with margins for printing
    # 8.5" x 11" = 215.9mm x 279.4mm
    # Leave 0.5" (12.7mm) margins for printer
    page_width = 279.4 - (2 * 12.7)  # 254mm
    page_height = 215.9 - (2 * 12.7)  # 190.5mm
    margin = 15
    
    # Reserve space for header: title (2 lines) + k-factor + thickness + bent preview
    # Bent preview is 50mm tall, so align header height with that
    header_height = 56  # Matches bent preview box (50mm) + 6mm margin
    
    # Calculate available space for the drawing
    # Reserve space at bottom for bend dimensions + bounding box dimension
    # Increased reserve to account for text offset and leader lines
    bottom_reserve = 50  # Conservative - accounts for dimensions + text offset
    
    # Reserve space on right for bend dimensions + bounding box dimension
    # Increased reserve to account for text offset and leader lines
    right_reserve = 50  # Conservative - accounts for dimensions + text offset
    
    available_width = page_width - 2 * margin - right_reserve
    available_height = page_height - header_height - bottom_reserve
    
    scale_x = available_width / part_width if part_width > 0 else 1
    scale_y = available_height / part_height if part_height > 0 else 1
    raw_scale = min(scale_x, scale_y, 1.0)
    
    scale = round(raw_scale / 0.125) * 0.125
    if scale <= 0:
        scale = 0.125
    
    print(f"  Drawing scale: {scale:.3f} (rounded from {raw_scale:.3f})")
    
    # Center the drawing in the available space below the header
    drawing_area_center_y = header_height + (page_height - header_height) / 2
    offset_x = page_width / 2 - (part_width * scale) / 2 - min_x * scale
    offset_y = drawing_area_center_y - (part_height * scale) / 2 - min_y * scale
    
    def to_svg(point):
        x, y = get_coords(point)
        svg_x = offset_x + x * scale
        svg_y = offset_y + y * scale
        return svg_x, svg_y
    
    svg = []
    svg.append(f'<?xml version="1.0" encoding="UTF-8"?>')
    svg.append(f'<svg width="{page_width}mm" height="{page_height}mm" viewBox="0 0 {page_width} {page_height}" xmlns="http://www.w3.org/2000/svg">')
    
    # Add visible border around the entire page
    svg.append(f'  <rect x="0" y="0" width="{page_width}" height="{page_height}" stroke="black" stroke-width="0.5" fill="none"/>')
    
    # Header section with title, scale, and notes
    svg.append(f'  <text x="{page_width/2}" y="10" text-anchor="middle" font-size="6" font-weight="bold">{title}</text>')
    svg.append(f'  <text x="{page_width/2}" y="16" text-anchor="middle" font-size="4">Scale: {scale:.3f}:1</text>')
    
    # Add K-factor and thickness info at top
    notes_y = 22
    svg.append(f'  <text x="{page_width/2}" y="{notes_y}" text-anchor="middle" font-size="5" fill="#666">K-Factor: {k_factor}</text>')
    if thickness:
        thickness_inches = thickness / 25.4
        gauge, is_standard = determine_gauge(thickness_inches)
        
        # Build thickness string
        thickness_str = f"Thickness: {thickness_inches:.4f}\""
        
        if gauge and is_standard:
            # Standard gauge - show gauge number
            thickness_str += f" ({gauge}ga)"
            # For thicker than 10ga (9ga, 8ga, 7ga, etc.), add fractional equivalent
            if gauge < 10:
                fractional = decimal_to_fraction(thickness_inches)
                thickness_str += f" [{fractional}]"
        elif gauge:
            # Close to a gauge but not exact
            thickness_str += f" (~{gauge}ga)"
            # For thicker than 10ga, add fractional equivalent
            if gauge < 10:
                fractional = decimal_to_fraction(thickness_inches)
                thickness_str += f" [{fractional}]"
        
        svg.append(f'  <text x="{page_width/2}" y="{notes_y + 6}" text-anchor="middle" font-size="5" fill="#666">{thickness_str}</text>')
    
    
    # Add bent state preview in upper right corner (tight to border)
    if bent_preview_svg:
        preview_x = page_width - 52  # 2mm from right edge (50mm box + 2mm margin)
        preview_y = 2  # 2mm from top
        svg.append(f'  <g transform="translate({preview_x}, {preview_y})">')
        svg.append(bent_preview_svg)
        svg.append(f'  </g>')
    
    print("  Drawing flat pattern outline...")
        # -------------------------------------------------------
    # BEGIN DRAWING GROUP (part + all dimensions)
    # -------------------------------------------------------
    svg.append('  <g id="drawing_group">')

    svg.append('  <g stroke="black" stroke-width="0.5" fill="none">')
    
    outer_wire = flat_face.OuterWire
    for edge in outer_wire.Edges:
        if hasattr(edge, 'Curve'):
            curve_type = edge.Curve.TypeId
            
            if 'Line' in curve_type:
                p1, p2 = edge.Vertexes[0].Point, edge.Vertexes[1].Point
                x1, y1 = to_svg(p1)
                x2, y2 = to_svg(p2)
                svg.append(f'    <line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}"/>')
                
            elif 'Circle' in curve_type:
                center = edge.Curve.Center
                radius = edge.Curve.Radius * scale
                
                if len(edge.Vertexes) == 2:
                    p1, p2 = edge.Vertexes[0].Point, edge.Vertexes[1].Point
                    x1, y1 = to_svg(p1)
                    x2, y2 = to_svg(p2)
                    
                    angle_span = edge.LastParameter - edge.FirstParameter
                    while angle_span > 2 * math.pi:
                        angle_span -= 2 * math.pi
                    while angle_span < -2 * math.pi:
                        angle_span += 2 * math.pi
                    
                    sweep, large_arc = determine_correct_sweep(edge, angle_span, to_svg)
                    sweep, large_arc = determine_correct_sweep(edge, angle_span, to_svg)
                    
                    svg.append(f'    <path d="M {x1:.2f},{y1:.2f} A {radius:.2f},{radius:.2f} 0 {large_arc},{sweep} {x2:.2f},{y2:.2f}"/>')
                else:
                    cx, cy = to_svg(center)
                    svg.append(f'    <circle cx="{cx:.2f}" cy="{cy:.2f}" r="{radius:.2f}"/>')
    
    inner_wires = [w for w in flat_face.Wires if w.hashCode() != outer_wire.hashCode()]
    for wire in inner_wires:
        for edge in wire.Edges:
            if hasattr(edge, 'Curve'):
                curve_type = edge.Curve.TypeId
                
                if 'Line' in curve_type:
                    p1, p2 = edge.Vertexes[0].Point, edge.Vertexes[1].Point
                    x1, y1 = to_svg(p1)
                    x2, y2 = to_svg(p2)
                    svg.append(f'    <line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}"/>')
                    
                elif 'Circle' in curve_type:
                    center = edge.Curve.Center
                    radius = edge.Curve.Radius * scale
                    
                    if len(edge.Vertexes) == 2:
                        p1, p2 = edge.Vertexes[0].Point, edge.Vertexes[1].Point
                        x1, y1 = to_svg(p1)
                        x2, y2 = to_svg(p2)
                        
                        angle_span = edge.LastParameter - edge.FirstParameter
                        while angle_span > 2 * math.pi:
                            angle_span -= 2 * math.pi
                        while angle_span < -2 * math.pi:
                            angle_span += 2 * math.pi
                        
                        sweep, large_arc = determine_correct_sweep(edge, angle_span, to_svg)
                        
                        svg.append(f'    <path d="M {x1:.2f},{y1:.2f} A {radius:.2f},{radius:.2f} 0 {large_arc},{sweep} {x2:.2f},{y2:.2f}"/>')
                    else:
                        cx, cy = to_svg(center)
                        svg.append(f'    <circle cx="{cx:.2f}" cy="{cy:.2f}" r="{radius:.2f}"/>')
    
    svg.append('  </g>')
    
    if fold_lines and hasattr(fold_lines, 'Edges'):
        print(f"  Drawing {len(fold_lines.Edges)} bend lines...")
        svg.append('  <g stroke="red" stroke-width="0.35" stroke-dasharray="2,2" fill="none">')
        
        for edge in fold_lines.Edges:
            if hasattr(edge, 'Curve') and 'Line' in edge.Curve.TypeId:
                p1, p2 = edge.Vertexes[0].Point, edge.Vertexes[1].Point
                x1, y1 = to_svg(p1)
                x2, y2 = to_svg(p2)
                svg.append(f'    <line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}"/>')
        
        svg.append('  </g>')
        
        print("  Adding dimensions from bend lines to edges...")
        dimension_count = 0
        placed_dimensions = []  # Track placed dimensions to detect overlaps
        
        for edge_idx, edge in enumerate(fold_lines.Edges):
            if hasattr(edge, 'Curve') and 'Line' in edge.Curve.TypeId:
                # Find the nearest perpendicular edge using distToShape
                bend_dir = edge.tangentAt(edge.FirstParameter)
                min_distance = float('inf')
                min_parallel_distance = float('inf')
                nearest_edge = None
                nearest_parallel_edge = None
                nearest_point_pair = None
                nearest_parallel_point_pair = None
                
                min_parallelism_threshold = 0.95  # Edges must be this parallel (0.95 = ~18 degrees tolerance)
                
                # Check all edges in the outer wire
                for flat_edge in flat_face.OuterWire.Edges:
                    if hasattr(flat_edge, 'Curve') and 'Line' in flat_edge.Curve.TypeId:
                        flat_dir = flat_edge.tangentAt(flat_edge.FirstParameter)
                        
                        # Check if edges are perpendicular (dot product near 0) or parallel (near 1)
                        dot_product = abs(bend_dir.dot(flat_dir))
                        
                        dist_result = edge.distToShape(flat_edge)
                        distance = dist_result[0]
                        
                        # Track nearest edge regardless of parallelism (fallback)
                        if distance < min_distance and distance > 0.1:
                            min_distance = distance
                            nearest_edge = flat_edge
                            nearest_point_pair = dist_result[1][0] if len(dist_result) > 1 and len(dist_result[1]) > 0 else None
                        
                        # Prioritize parallel edges (parallel edges have dot product near 1)
                        if dot_product > min_parallelism_threshold:  # Parallel/same direction
                            if distance < min_parallel_distance and distance > 0.1:
                                min_parallel_distance = distance
                                nearest_parallel_edge = flat_edge
                                nearest_parallel_point_pair = dist_result[1][0] if len(dist_result) > 1 and len(dist_result[1]) > 0 else None
                
                # Prefer parallel edge if found, otherwise use nearest edge
                if nearest_parallel_edge:
                    nearest_edge = nearest_parallel_edge
                    nearest_point_pair = nearest_parallel_point_pair
                    min_distance = min_parallel_distance
                    print(f"    Bend {edge_idx+1}: Using parallel edge (distance: {min_distance:.2f}mm)")
                elif nearest_edge:
                    print(f"    Bend {edge_idx+1}: Warning - Using non-parallel edge (distance: {min_distance:.2f}mm)")
                
                if nearest_edge and min_distance < float('inf'):
                    svg.append(f'  <g>')
                    
                    # Get bend line endpoints in SVG coords
                    p1, p2 = edge.Vertexes[0].Point, edge.Vertexes[1].Point
                    bend_x1, bend_y1 = to_svg(p1)
                    bend_x2, bend_y2 = to_svg(p2)
                    
                    # Bend line midpoint
                    bend_mid_x = (bend_x1 + bend_x2) / 2
                    bend_mid_y = (bend_y1 + bend_y2) / 2
                    
                    # Bend line direction (unit vector)
                    dx = bend_x2 - bend_x1
                    dy = bend_y2 - bend_y1
                    length = math.sqrt(dx**2 + dy**2)
                    
                    if length > 0:
                        ux = dx / length
                        uy = dy / length
                        
                        # Get the nearest point on the edge (from distToShape)
                        if nearest_point_pair:
                            nearest_point = nearest_point_pair[1]  # Second point is on the other shape
                            near_x, near_y = to_svg(nearest_point)
                        else:
                            # Fallback: use edge center
                            edge_center = nearest_edge.CenterOfMass
                            near_x, near_y = to_svg(edge_center)
                        
                        # Vector from bend to nearest point
                        to_edge_dx = near_x - bend_mid_x
                        to_edge_dy = near_y - bend_mid_y
                        
                        # Two perpendicular directions
                        perp_dx1 = -uy
                        perp_dy1 = ux
                        perp_dx2 = uy
                        perp_dy2 = -ux
                        
                        # Choose the perpendicular that points toward the edge
                        dot1 = perp_dx1 * to_edge_dx + perp_dy1 * to_edge_dy
                        
                        if dot1 > 0:
                            perp_dx, perp_dy = perp_dx1, perp_dy1
                        else:
                            perp_dx, perp_dy = perp_dx2, perp_dy2
                        
                        # Distance in SVG space - add 7.5mm base offset from part edge
                        base_offset_mm = 7.5
                        svg_distance = math.sqrt(to_edge_dx**2 + to_edge_dy**2) + (base_offset_mm * scale)
                        
                        # Check for overlaps with previously placed dimensions
                        sideways_offset = 0
                        offset_increment = 32 * scale   # 7mm spacing between bend dimensions

                        
                        for placed in placed_dimensions:
                            # Check if this dimension goes in a similar direction
                            dir_dot = perp_dx * placed['dir_x'] + perp_dy * placed['dir_y']
                            
                            # Distance between the two bend line midpoints
                            dist_between = math.sqrt((bend_mid_x - placed['x'])**2 + (bend_mid_y - placed['y'])**2)
                            
                            # If pointing same direction AND close together, they'll overlap
                            if dir_dot > 0.7 and dist_between < 60 * scale:
                                sideways_offset += offset_increment
                                print(f"      Dimension overlap detected, adding offset: {sideways_offset/scale:.1f}mm")
                        
                        # Store this dimension for future overlap checks
                        placed_dimensions.append({
                            'x': bend_mid_x,
                            'y': bend_mid_y,
                            'dir_x': perp_dx,
                            'dir_y': perp_dy
                        })
                        
                        # Apply sideways offset perpendicular to the dimension direction
                        # Perpendicular to (perp_dx, perp_dy) is (-perp_dy, perp_dx)
                        offset_dir_x = -perp_dy
                        offset_dir_y = perp_dx
                        
                        # Start at the bend line with sideways offset applied
                        dim_start_x = bend_mid_x + offset_dir_x * sideways_offset
                        dim_start_y = bend_mid_y + offset_dir_y * sideways_offset
                        
                        # Search for intersection with the nearest edge
                        max_search_distance = svg_distance * 2
                        
                        closest_intersection = None
                        closest_distance = float('inf')
                        
                        for flat_edge in flat_face.OuterWire.Edges:
                            if hasattr(flat_edge, 'Curve') and 'Line' in flat_edge.Curve.TypeId:
                                edge_p1 = flat_edge.Vertexes[0].Point
                                edge_p2 = flat_edge.Vertexes[1].Point
                                e1x, e1y = to_svg(edge_p1)
                                e2x, e2y = to_svg(edge_p2)
                                
                                edge_dx = e2x - e1x
                                edge_dy = e2y - e1y
                                
                                denom = perp_dx * edge_dy - perp_dy * edge_dx
                                
                                if abs(denom) > 0.001:
                                    t = ((e1x - dim_start_x) * edge_dy - (e1y - dim_start_y) * edge_dx) / denom
                                    s = ((e1x - dim_start_x) * perp_dy - (e1y - dim_start_y) * perp_dx) / denom
                                    
                                    if 0 <= t <= max_search_distance and 0 <= s <= 1:
                                        int_x = dim_start_x + t * perp_dx
                                        int_y = dim_start_y + t * perp_dy
                                        
                                        dist = math.sqrt((int_x - dim_start_x)**2 + (int_y - dim_start_y)**2)
                                        
                                        if dist < closest_distance and dist > 0.1:
                                            closest_distance = dist
                                            closest_intersection = (int_x, int_y)
                        
                        if closest_intersection:
                            dim_end_x, dim_end_y = closest_intersection
                        else:
                            dim_end_x = dim_start_x + perp_dx * svg_distance
                            dim_end_y = dim_start_y + perp_dy * svg_distance
                        
                        # Draw dimension line
                        svg.append(f'    <line x1="{dim_start_x:.2f}" y1="{dim_start_y:.2f}" x2="{dim_end_x:.2f}" y2="{dim_end_y:.2f}" stroke="blue" stroke-width="0.3"/>')
                        
                        # Calculate dimension from actual line length
                        actual_line_length_svg = math.sqrt((dim_end_x - dim_start_x)**2 + (dim_end_y - dim_start_y)**2)
                        actual_line_length_mm = actual_line_length_svg / scale
                        distance_inches = actual_line_length_mm / 25.4
                        
                        arrow_len = part_max_dim * scale * 0.015
                        arrow_width = arrow_len * 0.6
                        
                        wing_dx = -perp_dy
                        wing_dy = perp_dx
                        
                        # Arrow at bend line
                        arrow1_tip_x = dim_start_x
                        arrow1_tip_y = dim_start_y
                        arrow1_base_x = dim_start_x + perp_dx * arrow_len
                        arrow1_base_y = dim_start_y + perp_dy * arrow_len
                        arrow1_wing1_x = arrow1_base_x + wing_dx * arrow_width
                        arrow1_wing1_y = arrow1_base_y + wing_dy * arrow_width
                        arrow1_wing2_x = arrow1_base_x - wing_dx * arrow_width
                        arrow1_wing2_y = arrow1_base_y - wing_dy * arrow_width
                        
                        svg.append(f'    <polygon points="{arrow1_tip_x:.2f},{arrow1_tip_y:.2f} {arrow1_wing1_x:.2f},{arrow1_wing1_y:.2f} {arrow1_wing2_x:.2f},{arrow1_wing2_y:.2f}" fill="blue"/>')
                        
                        # Arrow at edge
                        arrow2_tip_x = dim_end_x
                        arrow2_tip_y = dim_end_y
                        arrow2_base_x = dim_end_x - perp_dx * arrow_len
                        arrow2_base_y = dim_end_y - perp_dy * arrow_len
                        arrow2_wing1_x = arrow2_base_x + wing_dx * arrow_width
                        arrow2_wing1_y = arrow2_base_y + wing_dy * arrow_width
                        arrow2_wing2_x = arrow2_base_x - wing_dx * arrow_width
                        arrow2_wing2_y = arrow2_base_y - wing_dy * arrow_width
                        
                        svg.append(f'    <polygon points="{arrow2_tip_x:.2f},{arrow2_tip_y:.2f} {arrow2_wing1_x:.2f},{arrow2_wing1_y:.2f} {arrow2_wing2_x:.2f},{arrow2_wing2_y:.2f}" fill="blue"/>')
                        
                        # Text offset from edge - additional offset beyond the dimension line
                        base_text_offset = 8
                        additional_text_offset = 7.5  # Extra offset for text only
                        total_text_offset = base_text_offset + (additional_text_offset * scale)
                        text_x = dim_end_x + perp_dx * total_text_offset
                        text_y = dim_end_y + perp_dy * total_text_offset
                        
                        # Convert to fractional format
                        fractional_dim = decimal_to_fraction(distance_inches)
                        
                        # Display dual dimensions: decimal above, fractional below, same font size
                        svg.append(f'    <text x="{text_x:.2f}" y="{text_y - 2:.2f}" text-anchor="middle" font-size="5" fill="blue">{distance_inches:.3f}"</text>')
                        svg.append(f'    <text x="{text_x:.2f}" y="{text_y + 5:.2f}" text-anchor="middle" font-size="5" fill="blue">{fractional_dim}</text>')
                        svg.append(f'  </g>')
                        
                        dimension_count += 1
                        print(f"    Dimension {dimension_count}: {distance_inches:.3f}\" (line length: {actual_line_length_mm:.2f}mm in SVG: {actual_line_length_svg:.2f}px)")
        
        print(f"  SUCCESS Added {dimension_count} dimensions")
    
    # Draw bounding box with dimensions (after bend dimensions so we can detect overlaps)
    print("  Drawing bounding box...")
    bbox_min_x = min_x * scale + offset_x
    bbox_min_y = min_y * scale + offset_y
    bbox_max_x = max_x * scale + offset_x
    bbox_max_y = max_y * scale + offset_y
    bbox_width = bbox_max_x - bbox_min_x
    bbox_height = bbox_max_y - bbox_min_y
    
    # Draw dashed bounding box
    svg.append('  <g stroke="#999" stroke-width="0.3" stroke-dasharray="2,2" fill="none">')
    svg.append(f'    <rect x="{bbox_min_x:.2f}" y="{bbox_min_y:.2f}" width="{bbox_width:.2f}" height="{bbox_height:.2f}"/>')
    svg.append('  </g>')
    
    # Add bounding box dimensions
    svg.append('  <g stroke="#666" stroke-width="0.3" fill="none">')
    
    # Convert dimensions to inches
    bbox_width_mm = part_width
    bbox_height_mm = part_height
    bbox_width_inches = bbox_width_mm / 25.4
    bbox_height_inches = bbox_height_mm / 25.4
    
    arrow_len = 3
    arrow_width = 1.5
    
    # Check if there are bend dimensions near the bottom that might overlap
    # Look for bend dimensions pointing downward (positive y direction)
    bottom_offset = 8  # Default offset
    max_bottom_extent = bbox_max_y  # Track how far down bend dimensions extend
    
    if fold_lines and hasattr(fold_lines, 'Edges'):
        for placed in placed_dimensions:
            # Check if dimension is in the lower half and pointing downward
            if placed['y'] > (bbox_min_y + bbox_max_y) / 2 and placed['dir_y'] > 0.5:
                # Estimate how far this dimension extends below the bbox
                # Assume dimension line is about 30 units long plus text
                estimated_extent = placed['y'] + 40
                if estimated_extent > max_bottom_extent:
                    max_bottom_extent = estimated_extent
        
        if max_bottom_extent > bbox_max_y + 5:
            # Need to move the bounding box dimension below the bend dimensions
            bottom_offset = max_bottom_extent - bbox_max_y + 8
            print(f"    Detected bend dimension near bottom edge - adjusting bounding box dimension offset to {bottom_offset:.1f}")
    
    # Make sure horizontal dimension stays within page bounds (leave 10mm margin from bottom for text)
    max_allowed_y = page_height - 10
    if bbox_max_y + bottom_offset + 10 > max_allowed_y:
        bottom_offset = max(5, max_allowed_y - bbox_max_y - 10)
        print(f"    Limiting bounding box dimension to stay within page bounds: offset={bottom_offset:.1f}mm")
    
    # Horizontal dimension (bottom) - with adjusted offset if needed
    h_dim_y = bbox_max_y + bottom_offset
    svg.append(f'    <line x1="{bbox_min_x:.2f}" y1="{h_dim_y:.2f}" x2="{bbox_max_x:.2f}" y2="{h_dim_y:.2f}"/>')
    
    # Leader lines from dimension to part (horizontal)
    svg.append(f'    <line x1="{bbox_min_x:.2f}" y1="{bbox_max_y:.2f}" x2="{bbox_min_x:.2f}" y2="{h_dim_y:.2f}" stroke="#666" stroke-width="0.3" stroke-dasharray="2,2"/>')
    svg.append(f'    <line x1="{bbox_max_x:.2f}" y1="{bbox_max_y:.2f}" x2="{bbox_max_x:.2f}" y2="{h_dim_y:.2f}" stroke="#666" stroke-width="0.3" stroke-dasharray="2,2"/>')
    
    # Horizontal arrows
    svg.append(f'    <polygon points="{bbox_min_x:.2f},{h_dim_y:.2f} {bbox_min_x + arrow_len:.2f},{h_dim_y - arrow_width:.2f} {bbox_min_x + arrow_len:.2f},{h_dim_y + arrow_width:.2f}" fill="#666"/>')
    svg.append(f'    <polygon points="{bbox_max_x:.2f},{h_dim_y:.2f} {bbox_max_x - arrow_len:.2f},{h_dim_y - arrow_width:.2f} {bbox_max_x - arrow_len:.2f},{h_dim_y + arrow_width:.2f}" fill="#666"/>')
    
    # Horizontal dimension text
    h_text_x = (bbox_min_x + bbox_max_x) / 2
    h_text_y = h_dim_y + 5
    h_fractional = decimal_to_fraction(bbox_width_inches)
    svg.append(f'    <text x="{h_text_x:.2f}" y="{h_text_y:.2f}" text-anchor="middle" font-size="5" fill="#666">{bbox_width_inches:.3f}"</text>')
    svg.append(f'    <text x="{h_text_x:.2f}" y="{h_text_y + 5:.2f}" text-anchor="middle" font-size="5" fill="#666">{h_fractional}</text>')
    
    # Check if there are bend dimensions near the right edge that might overlap
    right_offset = 8  # Default offset
    max_right_extent = bbox_max_x  # Track how far right bend dimensions extend
    
    if fold_lines and hasattr(fold_lines, 'Edges'):
        for placed in placed_dimensions:
            # Check if dimension is in the right half and pointing rightward
            if placed['x'] > (bbox_min_x + bbox_max_x) / 2 and placed['dir_x'] > 0.5:
                # Estimate how far this dimension extends to the right
                # Assume dimension line is about 30 units long plus text
                estimated_extent = placed['x'] + 40
                if estimated_extent > max_right_extent:
                    max_right_extent = estimated_extent
        
        if max_right_extent > bbox_max_x + 5:
            # Need to move the bounding box dimension beyond the bend dimensions
            right_offset = max_right_extent - bbox_max_x + 8
            print(f"    Detected bend dimension near right edge - adjusting bounding box dimension offset to {right_offset:.1f}")
    
    # Make sure vertical dimension stays within page bounds (leave 12mm margin from right for rotated text)
    max_allowed_x = page_width - 12
    if bbox_max_x + right_offset + 12 > max_allowed_x:
        right_offset = max(5, max_allowed_x - bbox_max_x - 12)
        print(f"    Limiting bounding box dimension to stay within page bounds: offset={right_offset:.1f}mm")
    
    # Vertical dimension (right side) - with adjusted offset if needed
    v_dim_x = bbox_max_x + right_offset
    svg.append(f'    <line x1="{v_dim_x:.2f}" y1="{bbox_min_y:.2f}" x2="{v_dim_x:.2f}" y2="{bbox_max_y:.2f}"/>')
    
    # Leader lines from dimension to part (vertical)
    svg.append(f'    <line x1="{bbox_max_x:.2f}" y1="{bbox_min_y:.2f}" x2="{v_dim_x:.2f}" y2="{bbox_min_y:.2f}" stroke="#666" stroke-width="0.3" stroke-dasharray="2,2"/>')
    svg.append(f'    <line x1="{bbox_max_x:.2f}" y1="{bbox_max_y:.2f}" x2="{v_dim_x:.2f}" y2="{bbox_max_y:.2f}" stroke="#666" stroke-width="0.3" stroke-dasharray="2,2"/>')
    
    # Vertical arrows
    svg.append(f'    <polygon points="{v_dim_x:.2f},{bbox_min_y:.2f} {v_dim_x - arrow_width:.2f},{bbox_min_y + arrow_len:.2f} {v_dim_x + arrow_width:.2f},{bbox_min_y + arrow_len:.2f}" fill="#666"/>')
    svg.append(f'    <polygon points="{v_dim_x:.2f},{bbox_max_y:.2f} {v_dim_x - arrow_width:.2f},{bbox_max_y - arrow_len:.2f} {v_dim_x + arrow_width:.2f},{bbox_max_y - arrow_len:.2f}" fill="#666"/>')
    
    # Vertical dimension text (rotated -90 degrees, so adjust spacing accordingly)
    v_text_x = v_dim_x + 5  # Decimal dimension
    v_text_x2 = v_dim_x + 11  # Fractional dimension (further out for better spacing)
    v_text_y = (bbox_min_y + bbox_max_y) / 2
    v_fractional = decimal_to_fraction(bbox_height_inches)
    svg.append(f'    <text x="{v_text_x:.2f}" y="{v_text_y:.2f}" text-anchor="middle" font-size="5" fill="#666" transform="rotate(-90 {v_text_x:.2f} {v_text_y:.2f})">{bbox_height_inches:.3f}"</text>')
    svg.append(f'    <text x="{v_text_x2:.2f}" y="{v_text_y:.2f}" text-anchor="middle" font-size="5" fill="#666" transform="rotate(-90 {v_text_x2:.2f} {v_text_y:.2f})">{v_fractional}</text>')
    
    svg.append('  </g>')
    print(f"  SUCCESS Bounding box: {bbox_width_inches:.3f}\" x {bbox_height_inches:.3f}\"")
    
    # -------------------------------------------------------
    # END DRAWING GROUP - Now center it and ensure bottom margin
    # -------------------------------------------------------
    svg.append('  </g>')
    
    # Calculate the actual bounds of the entire drawing group (part + all dimensions)
    # This requires tracking the furthest extents we've drawn
    print("  Calculating final drawing bounds for centering...")
    
    # Track extents of everything in drawing_group
    drawing_min_x = bbox_min_x - 8  # Account for left dimension line
    drawing_max_x = v_dim_x + 12    # Account for right dimension line and text
    drawing_min_y = bbox_min_y - 8  # Account for top dimension line  
    drawing_max_y = h_dim_y + 10    # Account for bottom dimension line and text
    
    # Also check bend dimensions
    if fold_lines and hasattr(fold_lines, 'Edges'):
        for placed in placed_dimensions:
            # Estimate dimension extents (approximate)
            est_extent_x = placed['x'] + abs(placed['dir_x']) * 40
            est_extent_y = placed['y'] + abs(placed['dir_y']) * 40
            drawing_max_x = max(drawing_max_x, est_extent_x)
            drawing_max_y = max(drawing_max_y, est_extent_y)
    
    drawing_width = drawing_max_x - drawing_min_x
    drawing_height = drawing_max_y - drawing_min_y
    
    # Calculate centering offsets
    # Horizontal: center in page
    target_center_x = page_width / 2
    current_center_x = (drawing_min_x + drawing_max_x) / 2
    shift_x = target_center_x - current_center_x
    
    # Vertical: ensure 1/4" (6.35mm) minimum bottom margin
    min_bottom_margin = 6.35  # 1/4 inch in mm
    current_bottom = drawing_max_y
    max_allowed_bottom = page_height - min_bottom_margin
    
    if current_bottom > max_allowed_bottom:
        # Need to shift up
        shift_y = max_allowed_bottom - current_bottom
    else:
        # Center vertically in available space
        available_height = page_height - header_height - min_bottom_margin
        target_center_y = header_height + available_height / 2
        current_center_y = (drawing_min_y + drawing_max_y) / 2
        shift_y = target_center_y - current_center_y
        
        # But still respect bottom margin
        if drawing_max_y + shift_y > max_allowed_bottom:
            shift_y = max_allowed_bottom - drawing_max_y
    
    print(f"  Drawing bounds: {drawing_width:.1f}mm x {drawing_height:.1f}mm")
    print(f"  Centering adjustments: dx={shift_x:.1f}mm, dy={shift_y:.1f}mm")
    
    # Apply transform to center the drawing group
    # We need to modify the drawing_group to include a transform
    # Find the line with '<g id="drawing_group">' and add transform
    for i, line in enumerate(svg):
        if 'id="drawing_group"' in line:
            svg[i] = f'  <g id="drawing_group" transform="translate({shift_x:.2f}, {shift_y:.2f})">'
            break
    
    svg.append('</svg>')
    
    with open(output_file, 'w') as f:
        f.write('\n'.join(svg))
    
    print(f"  SUCCESS SVG drawing created: {output_file}")


def create_bend_drawing(step_file, output_svg=None, k_factor=0.35):
    """Create bend line drawing from STEP file"""
    
    # Convert to absolute path for portability
    step_file = os.path.abspath(step_file)
    
    if not os.path.exists(step_file):
        raise FileNotFoundError(f"Input file not found: {step_file}")
    
    if output_svg is None:
        base_name = os.path.splitext(step_file)[0]
        output_svg = f"{base_name}_bends.svg"
    else:
        output_svg = os.path.abspath(output_svg)
        if not output_svg.endswith('.svg'):
            output_svg = output_svg.replace('.pdf', '.svg')
    
    print(f"\nProcessing: {step_file}")
    
    doc = FreeCAD.newDocument("BendDrawing")
    Import.insert(step_file, doc.Name)
    
    imported_obj = doc.Objects[0]
    
    try:
        import SheetMetalUnfolder
    except ImportError:
        raise ImportError("SheetMetal workbench is required. Install via Tools > Addon Manager > SheetMetal")
    
    faces = imported_obj.Shape.Faces
    largest_face = max(faces, key=lambda f: f.Area)
    largest_face_index = faces.index(largest_face)
    face_name = f"Face{largest_face_index + 1}"
    
    k_factor_lookup = {0.0: k_factor, 1.0: k_factor, 10.0: k_factor}
    unfold_result = SheetMetalUnfolder.getUnfold(k_factor_lookup, imported_obj, face_name, k_factor)
    
    unfold_shape = unfold_result[0]
    fold_lines = unfold_result[1] if len(unfold_result) > 1 else None
    
    unfold_obj = doc.addObject("Part::Feature", "Unfold")
    unfold_obj.Shape = unfold_shape
    doc.recompute()
    
    flat_faces = sorted(unfold_obj.Shape.Faces, key=lambda f: f.Area, reverse=True)
    flat_face = flat_faces[0]
    
    # Detect part thickness from the FLATTENED shape
    thickness = None
    try:
        # Get bounding box dimensions of the flattened part
        bbox = unfold_obj.Shape.BoundBox
        dimensions = sorted([bbox.XLength, bbox.YLength, bbox.ZLength])
        # The smallest dimension is the thickness
        thickness = dimensions[0]
        print(f"Detected thickness from flat pattern: {thickness:.3f} mm")
    except Exception as e:
        print(f"Could not detect thickness: {e}")
    
    # Generate bent state preview
    print("\nGenerating bent state preview...")
    bent_preview_svg = create_bent_part_preview(imported_obj)
    if bent_preview_svg:
        print("  SUCCESS Bent state preview created")
    else:
        print("  Note: Bent state preview not available")
    
    print("\nCreating SVG drawing...")
    create_svg_drawing(flat_face, fold_lines, output_svg, f"Flat Pattern - {os.path.basename(step_file)}", k_factor, thickness, bent_preview_svg)
    
    FreeCAD.closeDocument(doc.Name)
    return output_svg


# Main execution
print("\n" + "="*60)
print("MAIN SCRIPT EXECUTION")
print("="*60)

# Enhanced argument parsing for portable FreeCAD compatibility
args = []
if len(sys.argv) > 1:
    # Check if first arg is freecadcmd or contains path to it
    if 'freecadcmd' in sys.argv[0].lower() or 'freecad' in sys.argv[1].lower():
        # Called via freecadcmd, skip first 2 args
        args = sys.argv[2:] if len(sys.argv) > 2 else []
    else:
        # Direct python execution, skip first arg (script name)
        args = sys.argv[1:]

print(f"Parsed arguments: {args}")

if len(args) < 1:
    print("\nUsage:")
    print("  freecadcmd create_bend_drawing_portable.py input.step [output.svg] [k_factor]")
    print("  python create_bend_drawing_portable.py input.step [output.svg] [k_factor]")
    print("\nExamples:")
    print("  freecadcmd create_bend_drawing_portable.py bracket.step")
    print("  freecadcmd create_bend_drawing_portable.py bracket.step bracket_bends.svg")
    print("  freecadcmd create_bend_drawing_portable.py bracket.step bracket_bends.svg 0.4")
    print("\nK-factor default: 0.35")
    sys.exit(1)

step_file = args[0]
output_svg = args[1] if len(args) > 1 else None
k_factor = float(args[2]) if len(args) > 2 else 0.35

print(f"Input file: {step_file}")
print(f"Output file: {output_svg or 'auto-generated'}")
print(f"K-factor: {k_factor}")

try:
    result = create_bend_drawing(step_file, output_svg, k_factor)
    print("\n" + "="*60)
    print(f"SUCCESS SUCCESS! SVG drawing created: {result}")
    print("="*60)
except Exception as e:
    print("\n" + "="*60)
    print(f"ERROR FAILED: {str(e)}")
    print("="*60)
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\nScript finished.")