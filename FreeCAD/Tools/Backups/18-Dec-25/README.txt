# FreeCAD Sheet Metal Automation Tools
**Location:** D:\FreeCAD\Tools

## Quick Start

### Install Right-Click Menu (Easiest!)

**One-time setup:**
1. Right-click `install_context_menu.bat`
2. Select **"Run as administrator"**
3. Click "Yes" when Windows asks for permission
4. Done!

**Now you can:**
- Right-click any `.step` or `.stp` file in File Explorer
- Select **"Create Flat DXF"** or **"Create Bend Drawing"**
- Files are created instantly in the same folder
- Bend drawings automatically open in your browser!

**To uninstall:**
- Right-click `uninstall_context_menu.bat` → "Run as administrator"

---

### Manual Usage (Without Right-Click Menu)

**Option 1: Drag and Drop**
1. Drag your `.step` file onto `flatten_sheetmetal.bat` to create DXF
2. Drag your `.step` file onto `create_bend_drawing.bat` to create SVG

**Option 2: Command Line**
```cmd
cd /d "D:\path\to\your\step\files"
D:\FreeCAD\Tools\flatten_sheetmetal.bat bracket.step
D:\FreeCAD\Tools\create_bend_drawing.bat bracket.step
```

**Option 3: From the Tools directory**
```cmd
cd /d D:\FreeCAD\Tools
flatten_sheetmetal.bat "D:\Projects\bracket.step"
create_bend_drawing.bat "D:\Projects\bracket.step"
```

### Process Multiple Files
```cmd
cd /d "D:\path\to\your\step\files"
D:\FreeCAD\Tools\process_all.bat
```
This will process all `.step` and `.stp` files in the current directory.

## Files in This Directory

| File | Description |
|------|-------------|
| `flatten_sheetmetal.bat` | Wrapper script to flatten STEP → DXF |
| `create_bend_drawing.bat` | Wrapper script to create SVG drawings |
| `process_all.bat` | Batch process all STEP files in a folder |
| `install_context_menu.bat` | **Install right-click menu options (Run as Admin)** |
| `uninstall_context_menu.bat` | **Remove right-click menu options (Run as Admin)** |
| `verify_installation.bat` | Check that everything is set up correctly |
| `Flatten sheetmetal portable.py` | Python script for flattening |
| `Create bend drawing portable.py` | Python script for bend drawings |
| `README.txt` | This file |

## How the Batch Files Work

The `.bat` files automatically:
1. ✓ Detect FreeCAD at `D:\FreeCAD\bin\freecadcmd.exe`
2. ✓ Find the Python scripts in the Tools folder
3. ✓ Handle file paths correctly (spaces, special characters)
4. ✓ Show clear success/failure messages
5. ✓ Pause so you can read the output

## Usage Examples

### Example 1: Flatten with default K-factor (0.35)
```cmd
D:\FreeCAD\Tools\flatten_sheetmetal.bat bracket.step
```
**Output:** `bracket_flat.dxf` (same directory as input)

### Example 2: Flatten with custom K-factor
```cmd
D:\FreeCAD\Tools\flatten_sheetmetal.bat bracket.step bracket_flat.dxf 0.4
```

### Example 3: Create bend drawing
```cmd
D:\FreeCAD\Tools\create_bend_drawing.bat bracket.step
```
**Output:** `bracket_bends.svg` (same directory as input)

### Example 4: Custom output paths
```cmd
D:\FreeCAD\Tools\flatten_sheetmetal.bat "C:\Projects\bracket.step" "C:\Output\flat.dxf"
D:\FreeCAD\Tools\create_bend_drawing.bat "C:\Projects\bracket.step" "C:\Output\bends.svg"
```

### Example 5: Process all files in a directory
```cmd
cd /d C:\MyProjects\SheetMetal
D:\FreeCAD\Tools\process_all.bat
```

## Adding to PATH (Optional)

To run the scripts from anywhere without typing the full path:

1. Press `Win + R`, type `SystemPropertiesAdvanced`, press Enter
2. Click "Environment Variables"
3. Under "User variables", select "Path" and click "Edit"
4. Click "New" and add: `D:\FreeCAD\Tools`
5. Click "OK" on all windows
6. **Restart PowerShell/CMD**

Now you can run from anywhere:
```cmd
cd C:\MyProjects
flatten_sheetmetal.bat bracket.step
create_bend_drawing.bat bracket.step
```

## Creating Desktop Shortcuts

### For Drag-and-Drop Processing

**Flatten Shortcut:**
1. Right-click on Desktop → New → Shortcut
2. Location: `D:\FreeCAD\Tools\flatten_sheetmetal.bat`
3. Name: "Flatten Sheet Metal"
4. Now drag `.step` files onto this shortcut!

**Bend Drawing Shortcut:**
1. Right-click on Desktop → New → Shortcut
2. Location: `D:\FreeCAD\Tools\create_bend_drawing.bat`
3. Name: "Create Bend Drawing"
4. Drag `.step` files onto this shortcut!

## K-Factor Reference

| Material | K-Factor Range | Recommended |
|----------|---------------|-------------|
| Soft Aluminum | 0.30-0.35 | 0.33 |
| Hard Aluminum | 0.38-0.42 | 0.40 |
| Soft Steel | 0.33-0.38 | 0.35 |
| Mild Steel | 0.35-0.40 | 0.38 |
| Stainless Steel | 0.40-0.45 | 0.43 |
| Copper/Brass | 0.35-0.40 | 0.37 |

## Troubleshooting

### "Could not find freecadcmd.exe"
**Problem:** The batch file can't find FreeCAD.

**Solution:** 
- Ensure FreeCAD is at `D:\FreeCAD\bin\freecadcmd.exe`
- Or edit the batch file to point to your FreeCAD location

### "SheetMetal workbench not found"
**Problem:** FreeCAD doesn't have the SheetMetal addon installed.

**Solution:**
1. Open FreeCAD GUI (`D:\FreeCAD\bin\FreeCAD.exe`)
2. Go to Tools → Addon Manager
3. Search for "SheetMetal"
4. Click Install
5. Restart FreeCAD

### "Input file not found"
**Problem:** File path is incorrect or contains special characters.

**Solution:**
- Use quotes around paths with spaces: `flatten_sheetmetal.bat "my file.step"`
- Use absolute paths: `flatten_sheetmetal.bat "D:\Projects\file.step"`
- Check that the file extension is `.step` or `.stp`

### Script runs but no output file
**Problem:** Script completes but DXF/SVG isn't created.

**Solution:**
- Check the console output for errors
- Verify the STEP file is valid sheet metal (can be unfolded)
- Try opening the STEP file in FreeCAD GUI to check geometry
- Ensure write permissions in the output directory

### "Part may not be valid sheet metal"
**Problem:** FreeCAD can't unfold the part.

**Solution:**
- Part must have constant thickness
- All bends must be 90° or simple angles
- No complex curved surfaces
- Check in FreeCAD GUI: Part Design → SheetMetal → Unfold

### Context Menu Not Appearing
**Problem:** Right-click menu options don't show up after installation.

**Solution:**
- Ensure you ran `install_context_menu.bat` as Administrator
- Try restarting File Explorer (Task Manager → Windows Explorer → Restart)
- Check the file extension is `.step` or `.stp` (lowercase)
- Re-run the installer as Administrator

### Context Menu Shows Wrong Path
**Problem:** Right-click menu tries to run scripts from wrong location.

**Solution:**
- Run `uninstall_context_menu.bat` as Administrator
- Move the Tools folder to the correct location
- Run `install_context_menu.bat` as Administrator again
- The installer uses the current folder location when creating registry entries

## Direct Python Execution (Advanced)

If you want to bypass the batch files:

```cmd
D:\FreeCAD\bin\freecadcmd.exe "D:\FreeCAD\Tools\Flatten sheetmetal portable.py" bracket.step
D:\FreeCAD\bin\freecadcmd.exe "D:\FreeCAD\Tools\Create bend drawing portable.py" bracket.step
```

## Output Files

### DXF Files (from flatten_sheetmetal)
- Contains 2D flat pattern outline
- Includes holes and cutouts
- Ready for laser cutting or CNC punch
- Can be imported into CAM software

### SVG Files (from create_bend_drawing)
- Shows flat pattern with part outline
- Bend lines shown as red dashed lines
- Dimensions from each bend line to nearest edge (in inches)
- Scale is optimized to fit on page
- Can be opened in:
  - Web browser (Chrome, Firefox, Edge)
  - Inkscape (free vector editor)
  - Adobe Illustrator
  - Any SVG-compatible software

## Performance

- Small parts (<10 faces): ~2-3 seconds
- Medium parts (10-50 faces): ~3-5 seconds  
- Large parts (50+ faces): ~5-10 seconds
- Memory usage: ~200-400MB per file

## Integration Ideas

### File Explorer Context Menu
Add "Flatten Sheet Metal" to right-click menu on `.step` files:
1. Create registry file `flatten_context.reg`:
```reg
Windows Registry Editor Version 5.00

[HKEY_CLASSES_ROOT\SystemFileAssociations\.step\shell\FlattenSheetMetal]
@="Flatten Sheet Metal"

[HKEY_CLASSES_ROOT\SystemFileAssociations\.step\shell\FlattenSheetMetal\command]
@="\"D:\\FreeCAD\\Tools\\flatten_sheetmetal.bat\" \"%1\""
```
2. Double-click the `.reg` file to install
3. Now right-click any `.step` file → "Flatten Sheet Metal"

### PowerShell Function
Add to your PowerShell profile (`$PROFILE`):
```powershell
function Flatten-SheetMetal {
    param([string]$InputFile, [string]$OutputFile, [double]$KFactor = 0.35)
    & "D:\FreeCAD\Tools\flatten_sheetmetal.bat" $InputFile $OutputFile $KFactor
}

function New-BendDrawing {
    param([string]$InputFile, [string]$OutputFile, [double]$KFactor = 0.35)
    & "D:\FreeCAD\Tools\create_bend_drawing.bat" $InputFile $OutputFile $KFactor
}
```

Usage:
```powershell
Flatten-SheetMetal bracket.step
New-BendDrawing bracket.step
```

## Version Info
- Scripts: Portable Version (December 2025)
- Tested with: FreeCAD 0.20, 0.21
- Python: Uses FreeCAD's bundled Python (no separate installation needed)

## Support Resources
- FreeCAD Forum: https://forum.freecad.org/
- FreeCAD Documentation: https://wiki.freecad.org/
- SheetMetal Workbench: https://github.com/shaise/FreeCAD_SheetMetal

---
**Location:** D:\FreeCAD\Tools
**Last Updated:** December 16, 2025
