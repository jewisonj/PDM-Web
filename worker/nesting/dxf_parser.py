"""Parse DXF files and extract geometry as Shapely polygons.

Reads modelspace entities (LINE, ARC, CIRCLE, LWPOLYLINE),
converts arcs to line segments using chord tolerance,
stitches segments into closed loops, and returns Shapely Polygon objects.
"""

import math
from typing import Optional

import ezdxf
from shapely.geometry import Polygon, LineString, Point
from shapely.ops import polygonize, unary_union


def parse_dxf_to_polygons(
    dxf_path: str,
    chord_tol: float = 0.01,
    allowed_layers: Optional[set] = None,
) -> list[Polygon]:
    """
    Read a DXF file and return closed polygons representing part outlines.

    Args:
        dxf_path: Path to the DXF file.
        chord_tol: Arc discretization tolerance (inches).
        allowed_layers: If set, only include entities on these layers.
                        Default: include all layers.

    Returns:
        List of valid Shapely Polygon objects.
    """
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()

    segments = []
    direct_polygons = []

    for entity in msp:
        # Filter by layer if specified
        if allowed_layers and entity.dxf.layer not in allowed_layers:
            continue

        etype = entity.dxftype()

        if etype == "LINE":
            start = (entity.dxf.start.x, entity.dxf.start.y)
            end = (entity.dxf.end.x, entity.dxf.end.y)
            if _dist(start, end) > chord_tol:
                segments.append(LineString([start, end]))

        elif etype == "ARC":
            points = _discretize_arc(entity, chord_tol)
            if len(points) >= 2:
                segments.append(LineString(points))

        elif etype == "CIRCLE":
            points = _discretize_circle(entity, chord_tol)
            if len(points) >= 4:
                direct_polygons.append(Polygon(points))

        elif etype == "SPLINE":
            points = _discretize_spline(entity, chord_tol)
            if len(points) >= 3 and entity.closed:
                poly = Polygon(points)
                if poly.is_valid and poly.area > 0.001:
                    direct_polygons.append(poly)
            elif len(points) >= 2:
                segments.append(LineString(points))

        elif etype == "LWPOLYLINE":
            points = _extract_lwpolyline(entity, chord_tol)
            if len(points) >= 3:
                if entity.closed:
                    poly = Polygon(points)
                    if poly.is_valid and poly.area > 0.001:
                        direct_polygons.append(poly)
                else:
                    segments.append(LineString(points))

    # Stitch open segments into closed loops
    stitched_polygons = []
    if segments:
        try:
            merged = unary_union(segments)
            stitched_polygons = list(polygonize(merged))
        except Exception:
            pass

    # Combine all polygons
    all_polys = direct_polygons + stitched_polygons

    # Filter: keep only valid, non-degenerate polygons
    result = []
    for p in all_polys:
        if not p.is_valid:
            # Try to fix with buffer(0)
            p = p.buffer(0)
        if p.is_valid and not p.is_empty and p.area > 0.001:
            result.append(p)

    if not result:
        return result

    # Return the largest polygon as the part outline
    # (in case there are nested contours, the outer one is usually largest)
    # If there's only one, return it
    if len(result) == 1:
        return result

    # Sort by area descending - the outer contour should be largest
    result.sort(key=lambda p: p.area, reverse=True)
    return result


def get_bounding_box(polygons: list[Polygon]) -> tuple[float, float]:
    """Get the bounding box dimensions (width, height) of a list of polygons."""
    if not polygons:
        return (0.0, 0.0)
    # Use the first (largest) polygon
    bounds = polygons[0].bounds  # (minx, miny, maxx, maxy)
    return (bounds[2] - bounds[0], bounds[3] - bounds[1])


def get_total_area(polygons: list[Polygon]) -> float:
    """Get the total area of a list of polygons."""
    if not polygons:
        return 0.0
    return polygons[0].area


# === Private Helpers ===

def _dist(a: tuple, b: tuple) -> float:
    """Euclidean distance between two 2D points."""
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


def _discretize_arc(entity, chord_tol: float) -> list[tuple]:
    """Convert a DXF ARC entity to a list of (x, y) points."""
    cx, cy = entity.dxf.center.x, entity.dxf.center.y
    radius = entity.dxf.radius
    start_angle = math.radians(entity.dxf.start_angle)
    end_angle = math.radians(entity.dxf.end_angle)

    # Handle wrapping
    if end_angle <= start_angle:
        end_angle += 2 * math.pi

    arc_length = radius * (end_angle - start_angle)
    if arc_length < chord_tol:
        return []

    # Number of segments based on chord tolerance
    n_segments = max(2, int(math.ceil(arc_length / chord_tol)))
    # Cap at reasonable number
    n_segments = min(n_segments, 360)

    points = []
    for i in range(n_segments + 1):
        t = start_angle + (end_angle - start_angle) * i / n_segments
        x = cx + radius * math.cos(t)
        y = cy + radius * math.sin(t)
        points.append((x, y))

    return points


def _discretize_circle(entity, chord_tol: float) -> list[tuple]:
    """Convert a DXF CIRCLE entity to a list of (x, y) points forming a closed polygon."""
    cx, cy = entity.dxf.center.x, entity.dxf.center.y
    radius = entity.dxf.radius

    circumference = 2 * math.pi * radius
    n_segments = max(12, int(math.ceil(circumference / chord_tol)))
    n_segments = min(n_segments, 360)

    points = []
    for i in range(n_segments):
        t = 2 * math.pi * i / n_segments
        x = cx + radius * math.cos(t)
        y = cy + radius * math.sin(t)
        points.append((x, y))

    # Close the polygon
    points.append(points[0])
    return points


def _extract_lwpolyline(entity, chord_tol: float) -> list[tuple]:
    """Extract points from an LWPOLYLINE, handling bulge (arc segments)."""
    raw_points = list(entity.get_points(format="xyseb"))
    # format: x, y, start_width, end_width, bulge

    points = []
    n = len(raw_points)

    for i in range(n):
        x1, y1 = raw_points[i][0], raw_points[i][1]
        bulge = raw_points[i][4] if len(raw_points[i]) > 4 else 0

        points.append((x1, y1))

        if abs(bulge) > 1e-6:
            # This segment has an arc (bulge)
            next_i = (i + 1) % n
            x2, y2 = raw_points[next_i][0], raw_points[next_i][1]
            arc_points = _bulge_to_arc_points(x1, y1, x2, y2, bulge, chord_tol)
            # Skip first and last (they're the endpoints)
            points.extend(arc_points[1:-1])

    return points


def _bulge_to_arc_points(
    x1: float, y1: float,
    x2: float, y2: float,
    bulge: float,
    chord_tol: float,
) -> list[tuple]:
    """Convert a bulge arc segment to intermediate points."""
    # Bulge = tan(arc_angle / 4)
    # Positive bulge = CCW arc, negative = CW
    dx = x2 - x1
    dy = y2 - y1
    chord_len = math.sqrt(dx * dx + dy * dy)

    if chord_len < 1e-10:
        return [(x1, y1), (x2, y2)]

    # Sagitta and radius
    sagitta = abs(bulge) * chord_len / 2
    radius = (chord_len / 2) ** 2 / (2 * sagitta) + sagitta / 2 if sagitta > 1e-10 else 1e10

    # Arc angle
    arc_angle = 4 * math.atan(abs(bulge))

    # Center of the chord
    mx = (x1 + x2) / 2
    my = (y1 + y2) / 2

    # Normal to chord
    nx = -dy / chord_len
    ny = dx / chord_len

    # Distance from midpoint to center
    d = radius - sagitta
    if bulge < 0:
        d = -d

    cx = mx + d * nx
    cy = my + d * ny

    # Start and end angles
    start_angle = math.atan2(y1 - cy, x1 - cx)
    end_angle = math.atan2(y2 - cy, x2 - cx)

    # Ensure correct direction
    if bulge > 0:  # CCW
        if end_angle <= start_angle:
            end_angle += 2 * math.pi
    else:  # CW
        if end_angle >= start_angle:
            end_angle -= 2 * math.pi

    # Number of points
    arc_len = abs(arc_angle * radius)
    n_segments = max(2, int(math.ceil(arc_len / chord_tol)))
    n_segments = min(n_segments, 90)

    points = []
    for i in range(n_segments + 1):
        t = start_angle + (end_angle - start_angle) * i / n_segments
        x = cx + radius * math.cos(t)
        y = cy + radius * math.sin(t)
        points.append((x, y))

    return points


def _discretize_spline(entity, chord_tol: float) -> list[tuple]:
    """Convert a DXF SPLINE entity to a list of (x, y) points using ezdxf flattening."""
    try:
        pts = list(entity.flattening(chord_tol))
        return [(p.x, p.y) for p in pts]
    except Exception:
        return []
