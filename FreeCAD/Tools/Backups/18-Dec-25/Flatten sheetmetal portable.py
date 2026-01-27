#!/usr/bin/env python3
"""
FreeCAD Sheet Metal Flattening Script - Portable Version
Imports a STEP file, flattens the sheet metal part, and exports to DXF
Compatible with both installed and portable FreeCAD versions
"""

import sys
import os

# Disable GUI if running headless
try:
    import FreeCAD
    FreeCAD.GuiUp = False
except:
    pass

print("="*60)
print("FreeCAD Sheet Metal Flattening Tool (Portable)")
print(f"Python: {sys.version}")
print(f"Arguments: {sys.argv}")
print("="*60)

# Import FreeCAD modules
try:
    import FreeCAD
    import Part
    import Import
    import importDXF
    print(f"SUCCESS FreeCAD {FreeCAD.Version()} loaded successfully")
except Exception as e:
    print(f"ERROR Failed to load FreeCAD modules: {e}")
    sys.exit(1)

def flatten_sheetmetal(step_file, output_dxf=None, k_factor=0.35):
    """
    Flatten a sheet metal part from a STEP file and export to DXF
    
    Args:
        step_file: Path to input STEP file
        output_dxf: Path to output DXF file (optional, auto-generated if not provided)
        k_factor: K-factor for bend allowance calculation (default: 0.35)
    
    Returns:
        Path to the output DXF file
    """
    
    # Convert to absolute path for portability
    step_file = os.path.abspath(step_file)
    
    # Validate input file
    if not os.path.exists(step_file):
        raise FileNotFoundError(f"Input file not found: {step_file}")
    
    # Generate output filename if not provided
    if output_dxf is None:
        base_name = os.path.splitext(step_file)[0]
        output_dxf = f"{base_name}_flat.dxf"
    else:
        output_dxf = os.path.abspath(output_dxf)
    
    print(f"\nProcessing: {step_file}")
    print(f"K-factor: {k_factor}")
    
    # Create a new document
    doc = FreeCAD.newDocument("SheetMetalFlatten")
    print(f"SUCCESS Created document: {doc.Name}")
    
    # Import the STEP file
    print("Importing STEP file...")
    try:
        Import.insert(step_file, doc.Name)
        print(f"SUCCESS STEP file imported, found {len(doc.Objects)} objects")
    except Exception as e:
        raise ValueError(f"Failed to import STEP file: {e}")
    
    # Get the imported object
    if len(doc.Objects) == 0:
        raise ValueError("No objects found in STEP file")
    
    imported_obj = doc.Objects[0]
    print(f"SUCCESS Imported object: {imported_obj.Label} (Type: {imported_obj.TypeId})")
    
    # Check if SheetMetal workbench is available
    print("\nChecking for SheetMetal workbench...")
    try:
        import SheetMetalUnfoldCmd
        import SheetMetalUnfolder
        print("SUCCESS SheetMetal workbench found")
    except ImportError as e:
        print("ERROR SheetMetal workbench not found!")
        print("Please install it via Tools > Addon Manager > SheetMetal")
        print(f"Error details: {e}")
        raise ImportError("SheetMetal workbench is required")
    
    # Create unfold operation
    print("\nAttempting to unfold sheet metal part...")
    
    # Find the largest face to use as the starting face
    print("Finding largest face to use as unfold base...")
    if not hasattr(imported_obj, 'Shape') or not hasattr(imported_obj.Shape, 'Faces'):
        raise ValueError("Imported object has no faces - may not be a valid solid")
    
    faces = imported_obj.Shape.Faces
    if len(faces) == 0:
        raise ValueError("No faces found in the imported object")
    
    print(f"  Found {len(faces)} faces")
    
    # Find the face with the largest area
    largest_face = max(faces, key=lambda f: f.Area)
    largest_face_index = faces.index(largest_face)
    
    print(f"  Largest face: Face{largest_face_index + 1} with area {largest_face.Area:.2f} mm²")
    
    # Use getUnfold to flatten the part
    print(f"Attempting unfold using K-factor={k_factor}...")
    
    # Create a k-factor lookup dictionary
    k_factor_lookup = {0.0: k_factor, 1.0: k_factor, 10.0: k_factor}
    face_name = f"Face{largest_face_index + 1}"
    
    print(f"  Calling getUnfold with face: {face_name}")
    unfold_result = SheetMetalUnfolder.getUnfold(
        k_factor_lookup,
        imported_obj,
        face_name,
        k_factor
    )
    
    if unfold_result is None:
        raise ValueError("Unfold operation returned None - part may not be valid sheet metal")
    
    print(f"SUCCESS Unfold operation completed")
    
    # Extract the unfolded shape
    if isinstance(unfold_result, tuple) and len(unfold_result) > 0:
        unfold_shape = unfold_result[0]
        print(f"  Unfold returned {len(unfold_result)} elements")
    else:
        unfold_shape = unfold_result
    
    # Create object with unfolded shape
    unfold_obj = doc.addObject("Part::Feature", "Unfold")
    unfold_obj.Shape = unfold_shape
    doc.recompute()
    
    print(f"  Unfold shape: {len(unfold_obj.Shape.Faces)} faces, {len(unfold_obj.Shape.Edges)} edges")
    
    # Find the flat face (largest area face in the unfolded shape)
    print("\nFinding flat pattern face...")
    flat_faces = sorted(unfold_obj.Shape.Faces, key=lambda f: f.Area, reverse=True)
    
    # Print top 3 faces by area
    for i in range(min(3, len(flat_faces))):
        bbox = flat_faces[i].BoundBox
        z_height = bbox.ZMax - bbox.ZMin
        print(f"  Face {i}: Area={flat_faces[i].Area:.2f} mm², Z-height={z_height:.2f} mm")
    
    # Select the largest face
    flat_face = flat_faces[0]
    print(f"\nSUCCESS Selected flat face with area: {flat_face.Area:.2f} mm²")
    
    # Create a sketch from the flat face using Draft workbench
    print("\nCreating 2D sketch from flat face...")
    try:
        # Create a Part object with just the flat face
        flat_obj = doc.addObject("Part::Feature", "FlatFace")
        flat_obj.Shape = flat_face
        doc.recompute()
        
        print(f"  Created flat face object")
        
        # Get the face normal to determine the correct projection direction
        face_normal = flat_face.normalAt(0, 0)
        print(f"  Face normal: ({face_normal.x:.3f}, {face_normal.y:.3f}, {face_normal.z:.3f})")
        
        # Create a sketch and attach it to the flat face
        print("  Creating sketch attached to flat face...")
        sketch = doc.addObject('Sketcher::SketchObject', 'FlatPatternSketch')
        sketch.Support = (flat_obj, ['Face1'])
        sketch.MapMode = 'FlatFace'
        doc.recompute()
        
        print(f"  Sketch attached to face")
        print(f"  Sketch placement: Origin=({sketch.Placement.Base.x:.1f}, {sketch.Placement.Base.y:.1f}, {sketch.Placement.Base.z:.1f})")
        
        # Add all edges from the flat face to the sketch
        print(f"  Adding edges to sketch...")
        outer_wire = flat_face.OuterWire
        inner_wires = [w for w in flat_face.Wires if w.hashCode() != outer_wire.hashCode()]
        
        edge_count = 0
        for edge in outer_wire.Edges:
            try:
                # Transform edge to sketch local coordinates
                if hasattr(edge, 'Curve'):
                    curve_type = edge.Curve.TypeId
                    
                    if 'Line' in curve_type:
                        p1 = sketch.Placement.inverse().multVec(edge.Vertexes[0].Point)
                        p2 = sketch.Placement.inverse().multVec(edge.Vertexes[1].Point)
                        sketch.addGeometry(Part.LineSegment(p1, p2), False)
                        edge_count += 1
                    elif 'Circle' in curve_type:
                        center = sketch.Placement.inverse().multVec(edge.Curve.Center)
                        radius = edge.Curve.Radius
                        
                        if len(edge.Vertexes) == 2:
                            # Arc
                            p1 = sketch.Placement.inverse().multVec(edge.Vertexes[0].Point)
                            p2 = sketch.Placement.inverse().multVec(edge.Vertexes[1].Point)
                            # Find a third point on the arc
                            mid_param = (edge.FirstParameter + edge.LastParameter) / 2
                            p3 = sketch.Placement.inverse().multVec(edge.valueAt(mid_param))
                            
                            arc = Part.ArcOfCircle(p1, p3, p2)
                            sketch.addGeometry(arc, False)
                            edge_count += 1
                        else:
                            # Full circle
                            circle = Part.Circle(center, FreeCAD.Vector(0, 0, 1), radius)
                            sketch.addGeometry(circle, False)
                            edge_count += 1
            except Exception as e:
                print(f"    Warning: Could not add edge: {e}")
        
        # Add inner wires (holes)
        for wire in inner_wires:
            for edge in wire.Edges:
                try:
                    if hasattr(edge, 'Curve') and 'Line' in edge.Curve.TypeId:
                        p1 = sketch.Placement.inverse().multVec(edge.Vertexes[0].Point)
                        p2 = sketch.Placement.inverse().multVec(edge.Vertexes[1].Point)
                        sketch.addGeometry(Part.LineSegment(p1, p2), False)
                        edge_count += 1
                except:
                    pass
        
        doc.recompute()
        print(f"  SUCCESS Added {edge_count} edges to sketch")
        
        # Export the sketch
        print(f"\nExporting sketch to: {output_dxf}")
        importDXF.export([sketch], output_dxf)
        print("SUCCESS DXF export completed from sketch")
        
    except Exception as e:
        print(f"  Sketch creation failed: {e}")
        import traceback
        traceback.print_exc()
        print("\n  Falling back to Draft projection...")
        
        try:
            import Draft
            # Project along the face normal for correct orientation
            projection = Draft.makeShape2DView(flat_obj, face_normal)
            doc.recompute()
            
            print(f"  SUCCESS Created Draft projection")
            importDXF.export([projection], output_dxf)
            print("SUCCESS DXF export completed from projection")
        except Exception as e2:
            print(f"  Draft projection also failed: {e2}")
            print("  Using direct face export as last resort...")
            importDXF.export([flat_obj], output_dxf)
            print("SUCCESS DXF export completed (direct face)")
    
    # Verify file was created
    if os.path.exists(output_dxf):
        print(f"SUCCESS File created successfully: {output_dxf}")
        file_size = os.path.getsize(output_dxf)
        print(f"  File size: {file_size} bytes")
    else:
        print(f"⚠ Warning: Output file not found at expected location")
    
    # Close document without saving
    FreeCAD.closeDocument(doc.Name)
    print("SUCCESS Document closed")
    
    return output_dxf


# Main execution
print("\n" + "="*60)
print("MAIN SCRIPT EXECUTION")
print("="*60)

# Enhanced argument parsing for portable FreeCAD compatibility
# Handles multiple calling patterns:
# 1. freecadcmd flatten_sheetmetal_portable.py input.step
# 2. python flatten_sheetmetal_portable.py input.step
# 3. Direct execution: ./flatten_sheetmetal_portable.py input.step

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
    print("  freecadcmd flatten_sheetmetal_portable.py input.step [output.dxf] [k_factor]")
    print("  python flatten_sheetmetal_portable.py input.step [output.dxf] [k_factor]")
    print("\nExamples:")
    print("  freecadcmd flatten_sheetmetal_portable.py bracket.step")
    print("  freecadcmd flatten_sheetmetal_portable.py bracket.step bracket_flat.dxf")
    print("  freecadcmd flatten_sheetmetal_portable.py bracket.step bracket_flat.dxf 0.4")
    print("\nK-factor default: 0.35")
    sys.exit(1)

step_file = args[0]
output_dxf = args[1] if len(args) > 1 else None
k_factor = float(args[2]) if len(args) > 2 else 0.35

print(f"Input file: {step_file}")
print(f"Output file: {output_dxf or 'auto-generated'}")
print(f"K-factor: {k_factor}")

try:
    result = flatten_sheetmetal(step_file, output_dxf, k_factor)
    print("\n" + "="*60)
    print(f"SUCCESS SUCCESS! DXF created: {result}")
    print("="*60)
except Exception as e:
    print("\n" + "="*60)
    print(f"ERROR FAILED: {str(e)}")
    print("="*60)
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\nScript finished.")