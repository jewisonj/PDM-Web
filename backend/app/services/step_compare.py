"""
STEP File Comparison Service

Compares STEP files by extracting geometric fingerprints rather than
direct text comparison (which fails due to timestamps/entity renumbering).

Fingerprint includes:
- Entity counts by type (CARTESIAN_POINT, LINE, ADVANCED_FACE, etc.)
- Bounding box (min/max X, Y, Z from all CARTESIAN_POINTs)
- Total entity count
- File size (approximate indicator)

Two files with matching fingerprints are geometrically equivalent.
"""

import re
from dataclasses import dataclass
from typing import Optional
from pathlib import Path


@dataclass
class StepFingerprint:
    """Geometric fingerprint of a STEP file."""
    # Entity counts
    cartesian_points: int = 0
    directions: int = 0
    vectors: int = 0
    lines: int = 0
    circles: int = 0
    planes: int = 0
    advanced_faces: int = 0
    closed_shells: int = 0
    manifold_solids: int = 0

    # Bounding box
    min_x: float = float('inf')
    max_x: float = float('-inf')
    min_y: float = float('inf')
    max_y: float = float('-inf')
    min_z: float = float('inf')
    max_z: float = float('-inf')

    # Totals
    total_entities: int = 0
    file_size: int = 0

    @property
    def bounding_box(self) -> tuple:
        """Return (width, height, depth) of bounding box."""
        if self.min_x == float('inf'):
            return (0, 0, 0)
        return (
            round(self.max_x - self.min_x, 6),
            round(self.max_y - self.min_y, 6),
            round(self.max_z - self.min_z, 6)
        )

    def matches(self, other: 'StepFingerprint', tolerance: float = 0.001) -> bool:
        """Check if two fingerprints match within tolerance."""
        # Check entity counts (must be exact)
        if (self.cartesian_points != other.cartesian_points or
            self.directions != other.directions or
            self.lines != other.lines or
            self.circles != other.circles or
            self.advanced_faces != other.advanced_faces or
            self.closed_shells != other.closed_shells or
            self.manifold_solids != other.manifold_solids):
            return False

        # Check bounding box (within tolerance)
        bb1 = self.bounding_box
        bb2 = other.bounding_box
        for i in range(3):
            if abs(bb1[i] - bb2[i]) > tolerance:
                return False

        return True

    def diff(self, other: 'StepFingerprint') -> dict:
        """Return differences between two fingerprints."""
        diffs = {}

        for attr in ['cartesian_points', 'directions', 'vectors', 'lines',
                     'circles', 'planes', 'advanced_faces', 'closed_shells',
                     'manifold_solids', 'total_entities']:
            v1 = getattr(self, attr)
            v2 = getattr(other, attr)
            if v1 != v2:
                diffs[attr] = {'old': v1, 'new': v2, 'delta': v2 - v1}

        bb1 = self.bounding_box
        bb2 = other.bounding_box
        if bb1 != bb2:
            diffs['bounding_box'] = {'old': bb1, 'new': bb2}

        return diffs

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'entity_counts': {
                'cartesian_points': self.cartesian_points,
                'directions': self.directions,
                'vectors': self.vectors,
                'lines': self.lines,
                'circles': self.circles,
                'planes': self.planes,
                'advanced_faces': self.advanced_faces,
                'closed_shells': self.closed_shells,
                'manifold_solids': self.manifold_solids,
                'total': self.total_entities,
            },
            'bounding_box': {
                'min': [self.min_x, self.min_y, self.min_z],
                'max': [self.max_x, self.max_y, self.max_z],
                'dimensions': list(self.bounding_box),
            },
            'file_size': self.file_size,
        }


# Regex patterns for STEP entity extraction
ENTITY_PATTERNS = {
    'cartesian_points': re.compile(r'CARTESIAN_POINT\s*\('),
    'directions': re.compile(r'DIRECTION\s*\('),
    'vectors': re.compile(r'VECTOR\s*\('),
    'lines': re.compile(r'#\d+=LINE\s*\('),  # Match LINE entities by ID prefix
    'circles': re.compile(r'CIRCLE\s*\('),
    'planes': re.compile(r'PLANE\s*\('),
    'advanced_faces': re.compile(r'ADVANCED_FACE\s*\('),
    'closed_shells': re.compile(r'CLOSED_SHELL\s*\('),
    'manifold_solids': re.compile(r'MANIFOLD_SOLID_BREP\s*\('),
}

# Pattern to extract coordinates from CARTESIAN_POINT
COORD_PATTERN = re.compile(
    r"CARTESIAN_POINT\s*\(\s*'[^']*'\s*,\s*\(\s*"
    r"([+-]?\d+\.?\d*E?[+-]?\d*)\s*,\s*"
    r"([+-]?\d+\.?\d*E?[+-]?\d*)\s*,\s*"
    r"([+-]?\d+\.?\d*E?[+-]?\d*)\s*\)\s*\)"
)


def parse_step_fingerprint(content: str | bytes, file_size: int = 0) -> StepFingerprint:
    """
    Parse a STEP file and extract its geometric fingerprint.

    Args:
        content: STEP file content as string or bytes
        file_size: Optional file size in bytes

    Returns:
        StepFingerprint with extracted metrics
    """
    if isinstance(content, bytes):
        content = content.decode('utf-8', errors='ignore')

    fp = StepFingerprint()
    fp.file_size = file_size or len(content)

    # Count entities
    for attr, pattern in ENTITY_PATTERNS.items():
        setattr(fp, attr, len(pattern.findall(content)))

    # Count total entities (lines starting with #number=)
    fp.total_entities = len(re.findall(r'^#\d+=', content, re.MULTILINE))

    # Extract bounding box from CARTESIAN_POINTs
    for match in COORD_PATTERN.finditer(content):
        try:
            x = float(match.group(1))
            y = float(match.group(2))
            z = float(match.group(3))

            fp.min_x = min(fp.min_x, x)
            fp.max_x = max(fp.max_x, x)
            fp.min_y = min(fp.min_y, y)
            fp.max_y = max(fp.max_y, y)
            fp.min_z = min(fp.min_z, z)
            fp.max_z = max(fp.max_z, z)
        except (ValueError, IndexError):
            continue

    # Handle empty bounding box
    if fp.min_x == float('inf'):
        fp.min_x = fp.max_x = 0
        fp.min_y = fp.max_y = 0
        fp.min_z = fp.max_z = 0

    return fp


def parse_step_file(file_path: str | Path) -> StepFingerprint:
    """Parse a STEP file from disk."""
    path = Path(file_path)
    content = path.read_text(encoding='utf-8', errors='ignore')
    return parse_step_fingerprint(content, path.stat().st_size)


def compare_step_files(file1: str | Path, file2: str | Path) -> dict:
    """
    Compare two STEP files and return comparison result.

    Returns:
        dict with 'match' (bool), 'fingerprint1', 'fingerprint2', 'differences'
    """
    fp1 = parse_step_file(file1)
    fp2 = parse_step_file(file2)

    return {
        'match': fp1.matches(fp2),
        'fingerprint1': fp1.to_dict(),
        'fingerprint2': fp2.to_dict(),
        'differences': fp1.diff(fp2),
    }


def compare_step_content(content1: bytes, content2: bytes) -> dict:
    """Compare two STEP file contents directly."""
    fp1 = parse_step_fingerprint(content1)
    fp2 = parse_step_fingerprint(content2)

    return {
        'match': fp1.matches(fp2),
        'fingerprint1': fp1.to_dict(),
        'fingerprint2': fp2.to_dict(),
        'differences': fp1.diff(fp2),
    }


# Quick test if run directly
if __name__ == '__main__':
    import sys
    if len(sys.argv) == 2:
        # Single file - print fingerprint
        fp = parse_step_file(sys.argv[1])
        import json
        print(json.dumps(fp.to_dict(), indent=2))
    elif len(sys.argv) == 3:
        # Two files - compare
        result = compare_step_files(sys.argv[1], sys.argv[2])
        import json
        print(json.dumps(result, indent=2))
    else:
        print("Usage: python step_compare.py <file.step> [file2.step]")
