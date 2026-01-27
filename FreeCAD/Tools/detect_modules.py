#!/usr/bin/env python3
"""
Detect available export modules in FreeCAD
"""

import sys
import os

try:
    import FreeCAD
    FreeCAD.GuiUp = False
except:
    pass

import FreeCAD

print("="*60)
print("FreeCAD Module Detection")
print(f"FreeCAD Version: {FreeCAD.Version()}")
print("="*60)

# Try to find glTF/WebGL related modules
modules_to_check = [
    'importWebGL',
    'ImportWebGL', 
    'importGLTF',
    'ImportGLTF',
    'WebGL',
    'GLTF',
    'glTF',
    'RWGltf',
]

print("\nChecking for glTF export modules:")
available_modules = []

for mod_name in modules_to_check:
    try:
        mod = __import__(mod_name)
        print(f"  ✓ {mod_name} - AVAILABLE")
        available_modules.append(mod_name)
        
        # Check for export function
        if hasattr(mod, 'export'):
            print(f"    - has export() function")
        if hasattr(mod, 'save'):
            print(f"    - has save() function")
            
    except ImportError:
        print(f"  ✗ {mod_name} - not found")

# Check Import module capabilities
print("\n" + "="*60)
print("Checking Import module:")
import Import

if hasattr(Import, 'export'):
    print("  ✓ Import.export() available")
    
    # Try to get supported formats
    try:
        # Some versions expose this
        if hasattr(Import, 'getSupportedTypes'):
            formats = Import.getSupportedTypes()
            print(f"\n  Supported export formats:")
            for fmt in formats:
                print(f"    - {fmt}")
    except:
        pass

# List all FreeCAD modules
print("\n" + "="*60)
print("All available FreeCAD modules containing 'web', 'gltf', or 'gl':")
import pkgutil

for importer, modname, ispkg in pkgutil.iter_modules():
    lower_name = modname.lower()
    if 'web' in lower_name or 'gltf' in lower_name or 'gltf' in lower_name:
        print(f"  - {modname}")

print("\n" + "="*60)
if available_modules:
    print(f"Found {len(available_modules)} glTF-related modules: {', '.join(available_modules)}")
else:
    print("No glTF export modules found")
    print("\nTry exporting manually:")
    print("  1. Open your STEP file in FreeCAD GUI")
    print("  2. Select object")
    print("  3. File > Export")
    print("  4. Choose .glb extension")
    print("  5. Note any error messages")
