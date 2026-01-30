"""Generate nested DXF output files.

Creates DXF files with parts placed on sheets, including:
- Sheet boundary on SHEET layer
- Parts geometry on PARTS layer
- Part labels on LABELS layer
"""

import ezdxf
from shapely.geometry import Polygon

from nester import SheetResult


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
            _insert_part_from_dxf(
                msp, part_dxf,
                placement.x, placement.y,
                placement.rotation,
            )
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
    x: float, y: float,
    rotation: float,
) -> None:
    """Read a DXF file and insert its geometry into msp, transformed."""
    src = ezdxf.readfile(dxf_path)
    src_msp = src.modelspace()

    # Get bounding box of source to normalize position
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

    if not all_points:
        return

    min_x = min(p[0] for p in all_points)
    min_y = min(p[1] for p in all_points)

    import math

    # Rotation in radians
    rad = math.radians(rotation)
    cos_r = math.cos(rad)
    sin_r = math.sin(rad)

    def transform(px: float, py: float) -> tuple[float, float]:
        """Normalize to origin, rotate, then translate to placement position."""
        # Normalize
        nx = px - min_x
        ny = py - min_y
        # Rotate around origin
        rx = nx * cos_r - ny * sin_r
        ry = nx * sin_r + ny * cos_r
        # Translate
        return (rx + x, ry + y)

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
            cx, cy = transform(entity.dxf.center.x, entity.dxf.center.y)
            msp.add_circle(
                (cx, cy), entity.dxf.radius,
                dxfattribs={"layer": "PARTS"},
            )

        elif etype == "ARC":
            # Transform arc center; adjust angles for rotation
            cx, cy = transform(entity.dxf.center.x, entity.dxf.center.y)
            start_angle = entity.dxf.start_angle + rotation
            end_angle = entity.dxf.end_angle + rotation
            msp.add_arc(
                (cx, cy), entity.dxf.radius,
                start_angle, end_angle,
                dxfattribs={"layer": "PARTS"},
            )


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
