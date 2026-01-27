#!/usr/bin/env python3
"""
FreeCAD STEP to STL Converter
STL is widely supported in web viewers (Three.js STLLoader)
"""

import sys
import os

try:
    import FreeCAD
    FreeCAD.GuiUp = False
except:
    pass

print("="*60)
print("FreeCAD STEP to STL Converter")
print("="*60)

import FreeCAD
import Import
import Mesh
import MeshPart
import Part

def convert_to_stl(step_file, output_stl=None, linear_deflection=0.1):
    """
    Convert STEP file to STL
    
    Args:
        step_file: Path to input STEP file
        output_stl: Path to output STL file (optional)
        linear_deflection: Mesh quality (smaller = finer, default 0.1mm)
    
    Returns:
        Path to created STL file
    """
    
    step_file = os.path.abspath(step_file)
    
    if not os.path.exists(step_file):
        raise FileNotFoundError(f"Input file not found: {step_file}")
    
    if output_stl is None:
        base_name = os.path.splitext(step_file)[0]
        output_stl = f"{base_name}.stl"
    else:
        output_stl = os.path.abspath(output_stl)
    
    print(f"\nProcessing: {step_file}")
    print(f"Output: {output_stl}")
    print(f"Mesh Quality: LinearDeflection={linear_deflection}")
    
    # Create new document
    doc = FreeCAD.newDocument("STLConvert")
    
    # Import STEP file
    print("\nImporting STEP file...")
    Import.insert(step_file, doc.Name)
    
    obj_count = len(doc.Objects)
    print(f"Imported {obj_count} object(s)")
    
    # Collect all shapes
    shapes = []
    for obj in doc.Objects:
        if hasattr(obj, 'Shape') and obj.Shape:
            shapes.append(obj.Shape)
            print(f"  - {obj.Label}: {len(obj.Shape.Faces)} faces")
    
    if not shapes:
        raise RuntimeError("No valid shapes found in STEP file")
    
    # Create compound
    print("\nCreating compound shape...")
    compound = Part.makeCompound(shapes) if len(shapes) > 1 else shapes[0]
    
    # Convert to mesh
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
    
    # Export to STL
    print(f"\nExporting to STL format...")
    Mesh.export([mesh_obj], output_stl)
    
    # Verify output
    if os.path.exists(output_stl):
        size = os.path.getsize(output_stl)
        print(f"SUCCESS: Created {output_stl} ({size:,} bytes)")
    else:
        raise RuntimeError("STL file was not created")
    
    # Cleanup
    FreeCAD.closeDocument(doc.Name)
    
    return output_stl


# Main execution
args = []
if len(sys.argv) > 1:
    if 'freecadcmd' in sys.argv[0].lower() or (len(sys.argv) > 1 and 'freecad' in sys.argv[1].lower()):
        args = sys.argv[2:] if len(sys.argv) > 2 else []
    else:
        args = sys.argv[1:]

if len(args) < 1:
    print("\nUsage: freecadcmd convert_to_stl.py input.step [output.stl] [linear_deflection]")
    print("\nExamples:")
    print("  freecadcmd convert_to_stl.py part.step")
    print("  freecadcmd convert_to_stl.py part.step part.stl 0.05")
    sys.exit(1)

step_file = args[0]
output_stl = args[1] if len(args) > 1 else None
linear_deflection = float(args[2]) if len(args) > 2 else 0.1

try:
    result = convert_to_stl(step_file, output_stl, linear_deflection)
    print("\n" + "="*60)
    print(f"SUCCESS! STL created: {result}")
    print("="*60)
except Exception as e:
    print("\n" + "="*60)
    print(f"FAILED: {str(e)}")
    print("="*60)
    import traceback
    traceback.print_exc()
    sys.exit(1)
