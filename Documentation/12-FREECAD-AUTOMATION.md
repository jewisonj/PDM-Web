# FreeCAD Automation Reference

## Overview

FreeCAD automation scripts run headless to convert STEP files into manufacturing documents (DXF flat patterns and SVG technical drawings). Called by Worker-Processor service via batch files.

## Batch File Architecture

### flatten_sheetmetal.bat
**Location:** `D:\FreeCAD\Tools\flatten_sheetmetal.bat`

**Purpose:** Convert 3D sheet metal STEP file into flattened 2D DXF pattern for manufacturing.

**Usage:**
```batch
flatten_sheetmetal.bat "input.step" "output.dxf"
```

**Process:**
1. Accepts STEP file path as input
2. Calls FreeCAD Python script (headless mode)
3. Script uses SheetMetal workbench to unfold 3D model
4. Exports flattened geometry as DXF
5. Returns exit code: 0 = success, non-zero = failure

**Called by:** Worker-Processor `Generate-DXF` function

### create_bend_drawing.bat
**Location:** `D:\FreeCAD\Tools\create_bend_drawing.bat`

**Purpose:** Generate technical drawing (SVG) from STEP file with dimensions and annotations.

**Usage:**
```batch
create_bend_drawing.bat "input.step" "output.svg"
```

**Process:**
1. Accepts STEP file path as input
2. Calls FreeCAD Python script (headless mode)
3. Script creates TechDraw page with views
4. Adds dimensions and annotations
5. Exports as SVG
6. Returns exit code: 0 = success, non-zero = failure

**Called by:** Worker-Processor `Generate-SVG` function

## FreeCAD Python Scripts

### Current Development: Technical Drawing Generation

**Active Work:** Creating SVG technical drawings from sheet metal STEP files with automatic dimensioning and proper page layout.

**Key Features Being Developed:**
1. **SVG Output with Proper Arc Direction:**
   - Arcs must be clockwise for proper rendering
   - Arc direction control in export

2. **Dimension Placement:**
   - Automatic dimension line placement
   - Collision detection between dimensions
   - Iterative spacing adjustment

3. **Page Layout Optimization:**
   - Iterative scale reduction to fit drawings on page
   - Multiple views (front, top, side) as needed
   - Title block integration (planned)

4. **Dimension Line Spacing:**
   - Minimum spacing between parallel dimension lines
   - Collision avoidance with part geometry
   - Readable text placement

**Technical Challenges:**

1. **Headless Operation:**
   - FreeCAD runs without GUI via `FreeCADCmd.exe` or `FreeCAD.exe -c`
   - No visual feedback for debugging
   - Console output captured to temp files

2. **SheetMetal Workbench Integration:**
   - API for unfolding operations
   - Coordinate transformations for 2D projection
   - Handling complex bend geometries

3. **TechDraw API:**
   - Programmatic view creation
   - Dimension generation and placement
   - SVG export configuration

4. **Coordinate Transformations:**
   - Converting 3D STEP coordinates to 2D drawing space
   - Proper scaling and units
   - View orientation (front, top, side)

## Script Location Conventions

**Batch Files:**
- Primary: `D:\FreeCAD\Tools\`
- Batch files are thin wrappers that call Python scripts

**Python Scripts:**
- Location determined by batch file implementation
- Typically in same `Tools\` folder or FreeCAD macro directory
- May be embedded directly in batch file or separate .py files

## Execution Pattern

**From Worker-Processor:**
```powershell
Push-Location $Global:ToolsPath  # D:\FreeCAD\Tools
$process = Start-Process -FilePath $Global:FlattenBat `
                         -ArgumentList "`"$CADFilePath`" `"$outputDXF`"" `
                         -NoNewWindow `
                         -Wait `
                         -PassThru `
                         -RedirectStandardOutput "$env:TEMP\dxf_stdout.txt" `
                         -RedirectStandardError "$env:TEMP\dxf_stderr.txt"
Pop-Location

# Check exit code
if ($process.ExitCode -eq 0) {
    Write-Log "Success"
} else {
    Write-Log "Failed: exit code $($process.ExitCode)"
}
```

**Key Points:**
- Working directory: `D:\FreeCAD\Tools\`
- stdout/stderr captured for debugging
- Exit code determines success/failure
- Output files written to CheckIn folder

## FreeCAD Installation

**Current Version:** FreeCAD 0.21

**Installation Path:** `C:\Program Files\FreeCAD 0.21\bin\`

**Executables:**
- `FreeCAD.exe` - GUI version (can run with `-c` for console mode)
- `FreeCADCmd.exe` - Headless console version (preferred for automation)

**Configuration in CheckIn-Watcher:**
```powershell
$Global:FreeCADExe = "C:\Program Files\FreeCAD 0.21\bin\FreeCAD.exe"
```

## Debugging FreeCAD Scripts

**Capture Console Output:**
```powershell
# stdout and stderr saved by Worker-Processor
Get-Content "$env:TEMP\dxf_stdout.txt"
Get-Content "$env:TEMP\dxf_stderr.txt"
```

**Test Batch Script Manually:**
```batch
cd D:\FreeCAD\Tools
flatten_sheetmetal.bat "C:\Path\To\test.step" "C:\Path\To\output.dxf"
echo Exit code: %ERRORLEVEL%
```

**Run FreeCAD Interactively:**
```batch
# Open FreeCAD GUI and run Python script manually
FreeCAD.exe
# In Python console, paste script code
```

**Common Issues:**

1. **Import Errors:**
   - Workbench not installed (SheetMetal, TechDraw)
   - Module import failures
   - Solution: Verify workbenches in FreeCAD GUI

2. **File Path Issues:**
   - Spaces in paths (must be quoted)
   - Backslash escaping in Python strings
   - Relative vs absolute paths

3. **Memory Issues:**
   - Large STEP files consume significant RAM
   - Process files individually
   - Clear FreeCAD document after each operation

4. **Coordinate System Issues:**
   - STEP import orientation varies
   - Need to verify placement and rotation
   - Debug with simplified test geometry

## Integration with PDM Workflow

**Automatic Regeneration:**
When a STEP file is updated (checked into CheckIn folder):
1. CheckIn-Watcher checks if DXF/SVG exist for this item
2. If they exist, queues `GENERATE_DXF` and `GENERATE_SVG` tasks
3. Worker-Processor picks up tasks and regenerates files
4. New DXF/SVG appear in CheckIn folder
5. CheckIn-Watcher detects and moves to appropriate folders
6. File iterations bumped in database

**Manual Regeneration:**
Insert task directly into work_queue:
```sql
INSERT INTO work_queue (item_number, file_path, task_type, status)
VALUES ('csp0030', 'D:\PDM_Vault\CADData\STEP\csp0030.step', 'GENERATE_SVG', 'Pending');
```

## Performance Considerations

**Batch Processing:**
- FreeCAD startup overhead (~2-5 seconds per file)
- Consider batching multiple operations in single FreeCAD session
- Currently: One file per batch script call

**Concurrent Processing:**
- Worker-Processor processes one task at a time
- FreeCAD not thread-safe for automation
- Multiple Worker-Processor instances not recommended

**File Size Limits:**
- Complex STEP files (>10MB) may take 30+ seconds
- Very complex assemblies may fail due to memory
- Consider timeout mechanism for stuck processes

## Future Enhancements

**Planned Features:**
1. Title block automation
2. Multiple view layouts (front+top, isometric)
3. Automatic bend table generation
4. Material and thickness callouts
5. Custom dimension styles and standards

**Code Organization:**
- Move Python scripts from batch files to separate .py files
- Create reusable Python module for common operations
- Add logging within Python scripts
- Implement retry logic for failed operations

## FreeCAD Python API Notes

**Importing Modules:**
```python
import FreeCAD
import Part
import TechDraw
import Spreadsheet  # For bend tables
# SheetMetal workbench
try:
    import SheetMetalUnfolder
except ImportError:
    print("SheetMetal workbench not installed")
```

**Opening STEP Files:**
```python
doc = FreeCAD.newDocument()
Part.insert(step_file_path, doc.Name)
FreeCAD.setActiveDocument(doc.Name)
```

**Creating TechDraw Page:**
```python
page = doc.addObject('TechDraw::DrawPage', 'Page')
template = doc.addObject('TechDraw::DrawSVGTemplate', 'Template')
template.Template = '/path/to/template.svg'
page.Template = template
```

**Exporting SVG:**
```python
page.ViewObject.saveAs(output_svg_path)
# or
import TechDrawGui
TechDrawGui.exportPageAsSvg(page, output_svg_path)
```

## Current Development Status

**Working:**
- STEP import and basic view creation
- SVG export functionality
- Dimension generation
- Basic page layout

**In Progress:**
- Arc direction control for proper SVG rendering
- Iterative dimension collision detection and spacing
- Page scale optimization (iterative reduction to fit)
- Dimension line spacing refinement

**Planned:**
- Title block integration
- Bend table automation
- Multiple sheet support
- Batch processing optimization
