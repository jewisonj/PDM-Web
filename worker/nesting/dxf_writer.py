"""Generate nested DXF output files.

Creates DXF files with parts placed on sheets, including:
- Sheet boundary on SHEET layer
- Parts geometry on PARTS layer
- Part labels on LABELS layer
"""

import math
import ezdxf
from shapely.geometry import Polygon

from nester import SheetResult, Placement


def write_nested_sheet(
    sheet: SheetResult,
    original_dxf_paths: dict[str, str],
    output_path: str,
) -> None:
    """
    Create a DXF file with all parts placed on the sheet.

    Args:
        sheet: SheetResult with placements.
        original_dxf_paths: Map of part_id -> path to original DXF file.
        output_path: Path to write the output DXF.
    """
    doc = ezdxf.new(dxfversion="R2010")
    msp = doc.modelspace()

    # Create layers
    doc.layers.add("SHEET", color=7)      # White - sheet outline
    doc.layers.add("MARGIN", color=8)     # Gray - usable area
    doc.layers.add("PARTS", color=3)      # Green - part geometry
    doc.layers.add("LABELS", color=5)     # Blue - part labels

    # Draw sheet boundary
    w, h = sheet.width, sheet.height
    msp.add_lwpolyline(
        [(0, 0), (w, 0), (w, h), (0, h)],
        close=True,
        dxfattribs={"layer": "SHEET"},
    )

    # Place each part by reading its original DXF and transforming geometry
    for placement in sheet.placements:
        part_dxf = original_dxf_paths.get(placement.part_id)
        if not part_dxf:
            continue

        try:
            _insert_part_from_dxf(msp, part_dxf, placement)
        except Exception as e:
            # If we can't read the original DXF, draw the Shapely polygon instead
            _draw_polygon(msp, placement.polygon, "PARTS")

        # Add label at centroid
        centroid = placement.polygon.centroid
        label = f"{placement.part_id}#{placement.instance}"
        msp.add_text(
            label,
            dxfattribs={
                "layer": "LABELS",
                "height": min(0.25, sheet.width / 100),
                "insert": (centroid.x, centroid.y),
            },
        )

    doc.saveas(output_path)


def _insert_part_from_dxf(
    msp,
    dxf_path: str,
    placement: Placement,
) -> None:
    """Read a DXF file and insert its geometry into msp, transformed.

    Matches the nester's transform order:
    1. Rotate around source geometry centroid
    2. Normalize rotated bounding box to (0,0)
    3. Translate to placement polygon position on the sheet
    """
    src = ezdxf.readfile(dxf_path)
    src_msp = src.modelspace()

    rotation = placement.rotation

    # Collect all points from source to compute centroid and rotated bbox
    all_points = []
    for entity in src_msp:
        etype = entity.dxftype()
        if etype == "LINE":
            all_points.append((entity.dxf.start.x, entity.dxf.start.y))
            all_points.append((entity.dxf.end.x, entity.dxf.end.y))
        elif etype == "ARC" or etype == "CIRCLE":
            all_points.append((entity.dxf.center.x, entity.dxf.center.y))
        elif etype == "LWPOLYLINE":
            for pt in entity.get_points(format="xy"):
                all_points.append(pt)
        elif etype == "SPLINE":
            try:
                for pt in entity.flattening(0.01):
                    all_points.append((pt.x, pt.y))
            except Exception:
                pass

    if not all_points:
        raise ValueError("No geometry found in source DXF")

    # 1. Compute centroid of source geometry (rotation pivot, matching nester)
    cx = sum(p[0] for p in all_points) / len(all_points)
    cy = sum(p[1] for p in all_points) / len(all_points)

    # 2. Target position from placement polygon (already correctly placed by nester)
    target_min_x, target_min_y = placement.polygon.bounds[:2]

    # 3. Rotate all source points around centroid to find rotated bounding box
    rad = math.radians(rotation)
    cos_r = math.cos(rad)
    sin_r = math.sin(rad)

    def _rotate_pt(px: float, py: float) -> tuple[float, float]:
        """Rotate point around source centroid."""
        dx = px - cx
        dy = py - cy
        return (cx + dx * cos_r - dy * sin_r,
                cy + dx * sin_r + dy * cos_r)

    rotated_pts = [_rotate_pt(p[0], p[1]) for p in all_points]
    rot_min_x = min(p[0] for p in rotated_pts)
    rot_min_y = min(p[1] for p in rotated_pts)

    # 4. Full transform: rotate around centroid, then align rotated bbox to target
    def transform(px: float, py: float) -> tuple[float, float]:
        rx, ry = _rotate_pt(px, py)
        return (rx - rot_min_x + target_min_x,
                ry - rot_min_y + target_min_y)

    # Copy entities with transformation
    for entity in src_msp:
        etype = entity.dxftype()

        if etype == "LINE":
            sx, sy = transform(entity.dxf.start.x, entity.dxf.start.y)
            ex, ey = transform(entity.dxf.end.x, entity.dxf.end.y)
            msp.add_line(
                (sx, sy), (ex, ey),
                dxfattribs={"layer": "PARTS"},
            )

        elif etype == "LWPOLYLINE":
            points = list(entity.get_points(format="xy"))
            transformed = [transform(px, py) for px, py in points]
            msp.add_lwpolyline(
                transformed,
                close=entity.closed,
                dxfattribs={"layer": "PARTS"},
            )

        elif etype == "CIRCLE":
            tcx, tcy = transform(entity.dxf.center.x, entity.dxf.center.y)
            msp.add_circle(
                (tcx, tcy), entity.dxf.radius,
                dxfattribs={"layer": "PARTS"},
            )

        elif etype == "ARC":
            tcx, tcy = transform(entity.dxf.center.x, entity.dxf.center.y)
            start_angle = entity.dxf.start_angle + rotation
            end_angle = entity.dxf.end_angle + rotation
            msp.add_arc(
                (tcx, tcy), entity.dxf.radius,
                start_angle, end_angle,
                dxfattribs={"layer": "PARTS"},
            )

        elif etype == "SPLINE":
            # Flatten spline to polyline points
            try:
                pts = list(entity.flattening(0.01))
                if len(pts) < 2:
                    continue
                transformed = [transform(pt.x, pt.y) for pt in pts]
                msp.add_lwpolyline(
                    transformed,
                    close=entity.closed,
                    dxfattribs={"layer": "PARTS"},
                )
            except Exception:
                pass


def _draw_polygon(msp, polygon: Polygon, layer: str) -> None:
    """Fallback: draw a Shapely polygon as a LWPOLYLINE."""
    coords = list(polygon.exterior.coords)
    if len(coords) < 3:
        return
    msp.add_lwpolyline(
        coords,
        close=True,
        dxfattribs={"layer": layer},
    )
