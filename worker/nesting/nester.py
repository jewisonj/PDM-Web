"""Bottom-Left Fill (BLF) nesting algorithm using Shapely.

Places parts onto rectangular sheets by scanning for valid positions
from bottom-left, with configurable rotation. Produces multi-sheet
output when parts don't fit on a single sheet.
"""

import math
from dataclasses import dataclass, field

from shapely.geometry import Polygon, box
from shapely.affinity import rotate, translate
from shapely import prepared


@dataclass
class Placement:
    """A single part placed on a sheet."""
    part_id: str
    instance: int
    polygon: Polygon  # Transformed polygon on the sheet
    x: float
    y: float
    rotation: float


@dataclass
class SheetResult:
    """Result for a single sheet."""
    index: int
    width: float
    height: float
    placements: list[Placement] = field(default_factory=list)
    utilization: float = 0.0

    @property
    def occupied_area(self) -> float:
        return sum(p.polygon.area for p in self.placements)


@dataclass
class SkippedPart:
    """A part that could not be placed on any sheet."""
    part_id: str
    instance: int
    reason: str


@dataclass
class NestingResult:
    """Full nesting result across all sheets."""
    sheets: list[SheetResult] = field(default_factory=list)
    skipped: list[SkippedPart] = field(default_factory=list)

    @property
    def total_parts_placed(self) -> int:
        return sum(len(s.placements) for s in self.sheets)

    @property
    def total_sheets(self) -> int:
        return len(self.sheets)

    @property
    def total_skipped(self) -> int:
        return len(self.skipped)

    @property
    def avg_utilization(self) -> float:
        if not self.sheets:
            return 0.0
        return sum(s.utilization for s in self.sheets) / len(self.sheets)


def nest_parts(
    parts: list[dict],
    sheet_width: float,
    sheet_height: float,
    spacing: float = 0.125,
    margin: float = 0.5,
    rotation_step: int = 5,
) -> NestingResult:
    """
    Nest parts onto sheets using Bottom-Left Fill with rotation.

    Args:
        parts: List of dicts with keys:
            - id: str (part identifier)
            - polygon: Shapely Polygon (part outline)
            - quantity: int (number of instances)
        sheet_width: Sheet width in inches.
        sheet_height: Sheet height in inches.
        spacing: Part-to-part spacing in inches.
        margin: Sheet edge margin in inches.
        rotation_step: Rotation increment in degrees (0 = no rotation).

    Returns:
        NestingResult with sheets and placements.
    """
    usable_width = sheet_width - 2 * margin
    usable_height = sheet_height - 2 * margin
    usable_area = usable_width * usable_height

    if usable_width <= 0 or usable_height <= 0:
        return NestingResult()

    # Build list of part instances to place
    instances = []
    for part in parts:
        buffered = part["polygon"].buffer(spacing / 2)
        if not buffered.is_valid or buffered.is_empty:
            continue
        for i in range(part["quantity"]):
            instances.append({
                "id": part["id"],
                "instance": i + 1,
                "original": part["polygon"],
                "buffered": buffered,
            })

    # Sort by polygon area, largest first (big parts are hardest to place)
    instances.sort(
        key=lambda p: p["original"].area,
        reverse=True,
    )

    # Generate rotation angles
    if rotation_step <= 0:
        rotations = [0]
    else:
        rotations = list(range(0, 360, rotation_step))

    result = NestingResult()
    current_sheet = SheetResult(index=1, width=sheet_width, height=sheet_height)
    result.sheets.append(current_sheet)

    # Track occupied regions per sheet as a list of placed polygons
    sheet_polygons: list[list[Polygon]] = [[]]

    # Pre-check: find parts that are too large for the sheet at ANY rotation
    # so we can report them and skip them entirely
    oversized_ids = set()
    for inst in instances:
        if _is_oversized(inst["buffered"], usable_width, usable_height, rotations):
            oversized_ids.add((inst["id"], inst["instance"]))
            result.skipped.append(SkippedPart(
                part_id=inst["id"],
                instance=inst["instance"],
                reason="Too large for sheet at any rotation",
            ))

    # Filter out oversized parts
    placeable = [inst for inst in instances
                 if (inst["id"], inst["instance"]) not in oversized_ids]

    for inst in placeable:
        placed = _try_place(
            inst, current_sheet, sheet_polygons[-1],
            usable_width, usable_height, margin, rotations,
        )
        if not placed:
            # Start new sheet
            current_sheet = SheetResult(
                index=len(result.sheets) + 1,
                width=sheet_width,
                height=sheet_height,
            )
            result.sheets.append(current_sheet)
            sheet_polygons.append([])

            placed = _try_place(
                inst, current_sheet, sheet_polygons[-1],
                usable_width, usable_height, margin, rotations,
            )
            if not placed:
                result.skipped.append(SkippedPart(
                    part_id=inst["id"],
                    instance=inst["instance"],
                    reason="Could not fit on any sheet",
                ))
                continue

    # Calculate utilization for each sheet
    for sheet in result.sheets:
        original_area = sum(p.polygon.area for p in sheet.placements)
        sheet.utilization = original_area / usable_area if usable_area > 0 else 0

    # Remove empty sheets
    result.sheets = [s for s in result.sheets if s.placements]

    # Re-index sheets
    for i, sheet in enumerate(result.sheets):
        sheet.index = i + 1

    return result


def _try_place(
    inst: dict,
    sheet: SheetResult,
    placed_polys: list[Polygon],
    usable_width: float,
    usable_height: float,
    margin: float,
    rotations: list[int],
) -> bool:
    """Try to place a part on a sheet. Returns True if placed."""
    buffered = inst["buffered"]
    original = inst["original"]

    # Grid step size for scanning (adaptive based on part size)
    bounds = buffered.bounds
    part_w = bounds[2] - bounds[0]
    part_h = bounds[3] - bounds[1]
    step = max(0.25, min(part_w, part_h) / 4)

    best_placement = None
    best_y = float("inf")
    best_x = float("inf")

    # Prepare existing polygons for fast intersection tests
    prep_polys = [prepared.prep(p) for p in placed_polys]

    for rot in rotations:
        # Rotate around centroid
        if rot != 0:
            rotated_buf = rotate(buffered, rot, origin="centroid", use_radians=False)
            rotated_orig = rotate(original, rot, origin="centroid", use_radians=False)
        else:
            rotated_buf = buffered
            rotated_orig = original

        # Normalize: move so that bounding box starts at (0, 0)
        rb = rotated_buf.bounds
        dx = -rb[0]
        dy = -rb[1]
        norm_buf = translate(rotated_buf, dx, dy)
        norm_orig = translate(rotated_orig, dx, dy)

        nb = norm_buf.bounds
        pw = nb[2] - nb[0]
        ph = nb[3] - nb[1]

        # Skip if part doesn't fit at all
        if pw > usable_width or ph > usable_height:
            continue

        # Scan positions: bottom-to-top, left-to-right
        y = 0.0
        while y + ph <= usable_height + 0.001:
            x = 0.0
            while x + pw <= usable_width + 0.001:
                # Translate to position on sheet (including margin offset)
                candidate = translate(norm_buf, x + margin, y + margin)

                # Check no overlap with existing parts
                if not _overlaps_any(candidate, prep_polys):
                    # Valid position found
                    if y < best_y or (y == best_y and x < best_x):
                        actual_orig = translate(norm_orig, x + margin, y + margin)
                        best_placement = Placement(
                            part_id=inst["id"],
                            instance=inst["instance"],
                            polygon=actual_orig,
                            x=x + margin,
                            y=y + margin,
                            rotation=rot,
                        )
                        best_y = y
                        best_x = x
                    # Found a position at this y level, no need to scan more x
                    break

                x += step
            # If we found something at this y, use it (bottom-left preference)
            if best_placement is not None and best_y <= y:
                break
            y += step

    if best_placement is not None:
        sheet.placements.append(best_placement)
        # Add buffered version for collision detection
        placed_buf = translate(
            rotate(inst["buffered"], best_placement.rotation, origin="centroid", use_radians=False)
            if best_placement.rotation != 0 else inst["buffered"],
            0, 0,
        )
        # Rebuild the placed buffered polygon at the actual position
        rb = (rotate(inst["buffered"], best_placement.rotation, origin="centroid", use_radians=False)
              if best_placement.rotation != 0 else inst["buffered"])
        b = rb.bounds
        norm = translate(rb, -b[0], -b[1])
        placed_final = translate(norm, best_placement.x, best_placement.y)
        placed_polys.append(placed_final)
        return True

    return False


def _overlaps_any(candidate: Polygon, prep_polys: list) -> bool:
    """Check if candidate overlaps any existing prepared polygon."""
    for pp in prep_polys:
        if pp.intersects(candidate):
            # Check if it's more than a touching edge
            if not pp.touches(candidate):
                return True
    return False


def _is_oversized(
    buffered: Polygon,
    usable_width: float,
    usable_height: float,
    rotations: list[int],
) -> bool:
    """Check if a buffered part doesn't fit the sheet at any rotation."""
    for rot in rotations:
        if rot != 0:
            rotated = rotate(buffered, rot, origin="centroid", use_radians=False)
        else:
            rotated = buffered
        b = rotated.bounds
        pw = b[2] - b[0]
        ph = b[3] - b[1]
        if pw <= usable_width and ph <= usable_height:
            return False  # Fits at this rotation
    return True  # Doesn't fit at any rotation
