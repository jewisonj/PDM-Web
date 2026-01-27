#!/usr/bin/env python3
"""
FreeCAD Bend Line Drawing Generator - Docker CLI Compatible
Wrapper that sets up stubs for missing modules before running the bend drawing operation.
"""

import sys
import os

# Add the scripts directory to path for setup_stubs
scripts_dir = os.path.dirname(os.path.abspath(__file__))
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

# Set up stubs for missing modules BEFORE importing FreeCAD
import setup_stubs

# Add FreeCAD lib to path
if '/usr/local/lib' not in sys.path:
    sys.path.insert(0, '/usr/local/lib')

# Add SheetMetal addon to path
sheetmetal_path = '/root/.FreeCAD/Mod/sheetmetal'
if sheetmetal_path not in sys.path:
    sys.path.insert(0, sheetmetal_path)

# Now run the original script
# Import and run the original bend drawing script
tools_dir = '/scripts/tools'
if tools_dir not in sys.path:
    sys.path.insert(0, tools_dir)

# Disable GUI
try:
    import FreeCAD
    FreeCAD.GuiUp = False
except:
    pass

print("=" * 60)
print("FreeCAD Bend Drawing Generator - Docker CLI")
print("=" * 60)

# Now import the original module's functions
# Since the original script has spaces in the name, we use exec
original_script = '/scripts/tools/Create bend drawing portable.py'

if os.path.exists(original_script):
    # Read and execute the original script with our environment set up
    with open(original_script, 'r') as f:
        code = f.read()
    exec(code, globals())
else:
    print(f"ERROR: Original script not found: {original_script}")
    sys.exit(1)
