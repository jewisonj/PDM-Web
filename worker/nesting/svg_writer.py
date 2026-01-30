"""Convert a nested-sheet DXF to SVG for browser preview.

Reads a DXF produced by dxf_writer.py and emits an SVG with:
- Dark background (matches MRP dark theme)
- Sheet outline in gray
- Part geometry in green (#22c55e)
- Labels in sky-blue (#38bdf8)

Only handles entity types the DXF writer produces:
LINE, LWPOLYLINE, CIRCLE, ARC, TEXT.
"""

import math
import ezdxf
import svgwrite


# Layer → stroke color
LAYER_COLORS = {
    "SHEET":  "#64748b",   # slate-500
    "MARGIN": "#334155",   # slate-700
    "PARTS":  "#22c55e",   # green-500
    "LABELS": "#38bdf8",   # sky-400
}

BACKGROUND = "#0f172a"  # slate-900
DEFAULT_STROKE = "#94a3b8"

# SVG pixels per DXF inch — controls rendered size
SCALE = 12


def write_svg_from_dxf(
    dxf_path: str,
    svg_path: str,
    sheet_width: float,
    sheet_height: float,
) -> None:
    """
    Read a nested-sheet DXF and write an SVG preview.

    Args:
        dxf_path:     Path to the source DXF (output of dxf_writer).
        svg_path:     Path to write the SVG file.
        sheet_width:  Sheet width in inches (for viewBox).
        sheet_height: Sheet height in inches (for viewBox).
    """
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()

    # Padding around the sheet in DXF units
    pad = 0.5
    vb_w = sheet_width + pad * 2
    vb_h = sheet_height + pad * 2

    dwg = svgwrite.Drawing(
        svg_path,
        size=(f"{vb_w * SCALE}px", f"{vb_h * SCALE}px"),
        viewBox=f"{-pad} {-pad} {vb_w} {vb_h}",
    )

    # Background
    dwg.add(dwg.rect(
        insert=(-pad, -pad),
        size=(vb_w, vb_h),
        fill=BACKGROUND,
    ))

    stroke_w = max(0.08, sheet_width / 400)
    sheet_stroke_w = stroke_w * 0.5
    label_size = max(0.8, sheet_width / 40)

    for entity in msp:
        etype = entity.dxftype()
        layer = entity.dxf.layer if hasattr(entity.dxf, "layer") else ""
        color = LAYER_COLORS.get(layer, DEFAULT_STROKE)
        sw = sheet_stroke_w if layer == "SHEET" else stroke_w

        if etype == "LINE":
            dwg.add(dwg.line(
                start=_flip(entity.dxf.start, sheet_height),
                end=_flip(entity.dxf.end, sheet_height),
                stroke=color,
                stroke_width=sw,
                fill="none",
            ))

        elif etype == "LWPOLYLINE":
            points = [_flip(p, sheet_height)
                      for p in entity.get_points(format="xy")]
            if not points:
                continue
            if entity.closed and len(points) > 1:
                points.append(points[0])
            dwg.add(dwg.polyline(
                points=points,
                stroke=color,
                stroke_width=sw,
                fill="none",
            ))

        elif etype == "CIRCLE":
            cx, cy = _flip(
                (entity.dxf.center.x, entity.dxf.center.y), sheet_height
            )
            dwg.add(dwg.circle(
                center=(cx, cy),
                r=entity.dxf.radius,
                stroke=color,
                stroke_width=sw,
                fill="none",
            ))

        elif etype == "ARC":
            _draw_arc(dwg, entity, sheet_height, color, sw)

        elif etype == "TEXT":
            tx, ty = _flip(
                (entity.dxf.insert.x, entity.dxf.insert.y), sheet_height
            )
            dwg.add(dwg.text(
                entity.dxf.text,
                insert=(tx, ty),
                fill=color,
                font_size=f"{label_size}px",
                font_family="monospace",
                text_anchor="middle",
                dominant_baseline="central",
            ))

    dwg.save()


# ---------- helpers ----------

def _flip(pt, sheet_height: float) -> tuple[float, float]:
    """Flip Y axis: DXF is Y-up, SVG is Y-down."""
    if hasattr(pt, "x"):
        return (pt.x, sheet_height - pt.y)
    return (pt[0], sheet_height - pt[1])


def _draw_arc(dwg, entity, sheet_height, color, stroke_w):
    """Convert a DXF ARC entity to an SVG path arc."""
    cx, cy = _flip(
        (entity.dxf.center.x, entity.dxf.center.y), sheet_height
    )
    r = entity.dxf.radius
    # DXF angles are CCW from +X axis in degrees
    # After Y-flip, CCW becomes CW, so we swap start/end
    start_deg = entity.dxf.start_angle
    end_deg = entity.dxf.end_angle

    # Compute endpoints (in DXF coords, then flip)
    sx_dxf = entity.dxf.center.x + r * math.cos(math.radians(start_deg))
    sy_dxf = entity.dxf.center.y + r * math.sin(math.radians(start_deg))
    ex_dxf = entity.dxf.center.x + r * math.cos(math.radians(end_deg))
    ey_dxf = entity.dxf.center.y + r * math.sin(math.radians(end_deg))

    sx, sy = _flip((sx_dxf, sy_dxf), sheet_height)
    ex, ey = _flip((ex_dxf, ey_dxf), sheet_height)

    # Sweep angle (in DXF, arcs go CCW; after Y-flip they go CW)
    sweep = (end_deg - start_deg) % 360
    large_arc = 1 if sweep > 180 else 0
    # After Y-flip, CW = sweep-flag 1
    sweep_flag = 1

    d = f"M {sx},{sy} A {r},{r} 0 {large_arc},{sweep_flag} {ex},{ey}"
    dwg.add(dwg.path(d=d, stroke=color, stroke_width=stroke_w, fill="none"))
