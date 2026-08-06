#!/usr/bin/env python3
"""
STEP File Fingerprint Calculator

Computes a geometric fingerprint of a STEP file for comparison.
Outputs JSON to stdout for use by PowerShell upload service.

Usage:
    python step_fingerprint.py <file.step>
    python step_fingerprint.py <file.step> --compare <fingerprint.json>

Output:
    JSON object with entity_counts, bounding_box, file_size
"""

import sys
import json
import re
from pathlib import Path


def parse_step_fingerprint(content: str, file_size: int = 0) -> dict:
    """
    Parse a STEP file and extract its geometric fingerprint.

    Returns dict with entity_counts, bounding_box, file_size.
    """
    # Entity patterns
    patterns = {
        'cartesian_points': re.compile(r'CARTESIAN_POINT\s*\('),
        'directions': re.compile(r'DIRECTION\s*\('),
        'vectors': re.compile(r'VECTOR\s*\('),
        'lines': re.compile(r'#\d+=LINE\s*\('),
        'circles': re.compile(r'CIRCLE\s*\('),
        'planes': re.compile(r'PLANE\s*\('),
        'advanced_faces': re.compile(r'ADVANCED_FACE\s*\('),
        'closed_shells': re.compile(r'CLOSED_SHELL\s*\('),
        'manifold_solids': re.compile(r'MANIFOLD_SOLID_BREP\s*\('),
    }

    # Coordinate pattern for bounding box
    coord_pattern = re.compile(
        r"CARTESIAN_POINT\s*\(\s*'[^']*'\s*,\s*\(\s*"
        r"([+-]?\d+\.?\d*E?[+-]?\d*)\s*,\s*"
        r"([+-]?\d+\.?\d*E?[+-]?\d*)\s*,\s*"
        r"([+-]?\d+\.?\d*E?[+-]?\d*)\s*\)\s*\)"
    )

    # Count entities
    entity_counts = {}
    for name, pattern in patterns.items():
        entity_counts[name] = len(pattern.findall(content))

    # Count total entities
    entity_counts['total'] = len(re.findall(r'^#\d+=', content, re.MULTILINE))

    # Extract bounding box
    min_x = min_y = min_z = float('inf')
    max_x = max_y = max_z = float('-inf')

    for match in coord_pattern.finditer(content):
        try:
            x = float(match.group(1))
            y = float(match.group(2))
            z = float(match.group(3))

            min_x = min(min_x, x)
            max_x = max(max_x, x)
            min_y = min(min_y, y)
            max_y = max(max_y, y)
            min_z = min(min_z, z)
            max_z = max(max_z, z)
        except (ValueError, IndexError):
            continue

    # Handle empty bounding box
    if min_x == float('inf'):
        min_x = max_x = 0
        min_y = max_y = 0
        min_z = max_z = 0

    # Compute dimensions
    dimensions = [
        round(max_x - min_x, 6),
        round(max_y - min_y, 6),
        round(max_z - min_z, 6)
    ]

    return {
        'entity_counts': entity_counts,
        'bounding_box': {
            'min': [min_x, min_y, min_z],
            'max': [max_x, max_y, max_z],
            'dimensions': dimensions
        },
        'file_size': file_size
    }


def fingerprints_match(fp1: dict, fp2: dict, tolerance: float = 0.001) -> bool:
    """Check if two fingerprints match within tolerance."""
    ec1 = fp1.get('entity_counts', {})
    ec2 = fp2.get('entity_counts', {})

    # Check entity counts (must be exact)
    for key in ['cartesian_points', 'directions', 'lines', 'circles',
                'advanced_faces', 'closed_shells', 'manifold_solids']:
        if ec1.get(key, 0) != ec2.get(key, 0):
            return False

    # Check bounding box dimensions (within tolerance)
    dims1 = fp1.get('bounding_box', {}).get('dimensions', [0, 0, 0])
    dims2 = fp2.get('bounding_box', {}).get('dimensions', [0, 0, 0])

    for i in range(3):
        if abs(dims1[i] - dims2[i]) > tolerance:
            return False

    return True


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: step_fingerprint.py <file.step> [--compare <fingerprint.json>]"}))
        sys.exit(1)

    file_path = Path(sys.argv[1])

    if not file_path.exists():
        print(json.dumps({"error": f"File not found: {file_path}"}))
        sys.exit(1)

    # Read and parse the STEP file
    try:
        content = file_path.read_text(encoding='utf-8', errors='ignore')
        file_size = file_path.stat().st_size
        fingerprint = parse_step_fingerprint(content, file_size)
    except Exception as e:
        print(json.dumps({"error": f"Failed to parse STEP file: {str(e)}"}))
        sys.exit(1)

    # Compare mode
    if len(sys.argv) >= 4 and sys.argv[2] == '--compare':
        compare_arg = sys.argv[3]

        # Parse comparison fingerprint (can be JSON string or file path)
        try:
            if Path(compare_arg).exists():
                compare_fp = json.loads(Path(compare_arg).read_text())
            else:
                compare_fp = json.loads(compare_arg)
        except Exception as e:
            print(json.dumps({
                "error": f"Failed to parse comparison fingerprint: {str(e)}",
                "fingerprint": fingerprint
            }))
            sys.exit(1)

        is_match = fingerprints_match(fingerprint, compare_fp)

        print(json.dumps({
            "match": is_match,
            "fingerprint": fingerprint,
            "compared_to": compare_fp
        }))
    else:
        # Just output the fingerprint
        print(json.dumps(fingerprint))


if __name__ == '__main__':
    main()
