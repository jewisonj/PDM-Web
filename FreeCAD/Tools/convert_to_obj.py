#!/usr/bin/env python3
"""
FreeCAD STEP to OBJ Converter - Headless
OBJ supports colors/materials and works in Three.js
"""

import sys
import os

try:
    import FreeCAD
    FreeCAD.GuiUp = False
except:
    pass

print("="*60)
print("FreeCAD STEP to OBJ Converter")
print("="*60)

import FreeCAD
import Import
import Mesh
import MeshPart
import Part

def convert_to_obj(step_file, output_obj=None, linear_deflection=0.1):
    """
    Convert STEP file to OBJ (Wavefront format with materials)
    
    Args:
        step_file: Path to input STEP file
        output_obj: Path to output OBJ file (optional)
        linear_deflection: Mesh quality in mm (default 0.1, smaller = finer)
    
    Returns:
        Path to created OBJ file
    """
    
    step_file = os.path.abspath(step_file)
    
    if not os.path.exists(step_file):
        raise FileNotFoundError(f"Input file not found: {step_file}")
    
    if output_obj is None:
        base_name = os.path.splitext(step_file)[0]
        output_obj = f"{base_name}.obj"
    else:
        output_obj = os.path.abspath(output_obj)
    
    if not output_obj.lower().endswith('.obj'):
        output_obj = os.path.splitext(output_obj)[0] + '.obj'
    
    print(f"\nProcessing: {step_file}")
    print(f"Output: {output_obj}")
    print(f"Mesh Quality: {linear_deflection}mm")
    
    # Create document
    doc = FreeCAD.newDocument("OBJConvert")
    
    # Import STEP
    print("\nImporting STEP file...")
    Import.insert(step_file, doc.Name)
    
    obj_count = len(doc.Objects)
    print(f"Imported {obj_count} object(s)")
    
    # Collect shapes and mesh them
    shapes = []
    for obj in doc.Objects:
        if hasattr(obj, 'Shape') and obj.Shape and obj.Shape.Faces:
            shapes.append(obj.Shape)
            print(f"  - {obj.Label}: {len(obj.Shape.Faces)} faces")
    
    if not shapes:
        raise RuntimeError("No valid shapes found")
    
    # Create compound
    print("\nCreating compound shape...")
    compound = Part.makeCompound(shapes) if len(shapes) > 1 else shapes[0]
    
    # Mesh the geometry
    print("Meshing geometry...")
    mesh = MeshPart.meshFromShape(
        Shape=compound,
        LinearDeflection=linear_deflection,
        AngularDeflection=0.5,
        Relative=False
    )
    
    print(f"Mesh created: {len(mesh.Facets)} triangles, {len(mesh.Points)} vertices")
    
    # Create mesh object
    mesh_obj = doc.addObject("Mesh::Feature", "ExportMesh")
    mesh_obj.Mesh = mesh
    doc.recompute()
    
    # Export to OBJ
    print(f"\nExporting to OBJ format...")
    Mesh.export([mesh_obj], output_obj)
    
    # Verify
    if not os.path.exists(output_obj):
        raise RuntimeError("OBJ file was not created")
    
    size = os.path.getsize(output_obj)
    print(f"SUCCESS: Created {output_obj} ({size:,} bytes)")
    
    # Cleanup
    FreeCAD.closeDocument(doc.Name)
    
    return output_obj


# Main execution
args = []
if len(sys.argv) > 1:
    if 'freecadcmd' in sys.argv[0].lower() or (len(sys.argv) > 1 and 'freecad' in sys.argv[1].lower()):
        args = sys.argv[2:] if len(sys.argv) > 2 else []
    else:
        args = sys.argv[1:]

if len(args) < 1:
    print("\nUsage: freecadcmd convert_to_obj.py input.step [output.obj] [linear_deflection]")
    print("\nExamples:")
    print("  freecadcmd convert_to_obj.py part.step")
    print("  freecadcmd convert_to_obj.py assembly.step output.obj")
    print("  freecadcmd convert_to_obj.py part.step part.obj 0.05")
    sys.exit(1)

step_file = args[0]
output_obj = args[1] if len(args) > 1 else None
linear_deflection = float(args[2]) if len(args) > 2 else 0.1

try:
    result = convert_to_obj(step_file, output_obj, linear_deflection)
    print("\n" + "="*60)
    print(f"SUCCESS! OBJ created: {result}")
    print("="*60)
except Exception as e:
    print("\n" + "="*60)
    print(f"FAILED: {str(e)}")
    print("="*60)
    import traceback
    traceback.print_exc()
    sys.exit(1)
