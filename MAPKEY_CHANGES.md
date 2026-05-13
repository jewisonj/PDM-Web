# Mapkey FAV_ Favorites Replaced with Hard-Coded Paths

## Changes Made in config_FIXED.pro

All FAV_ favorite button references have been replaced with hard-coded folder navigation using the `computer_pb` button and double-action `Select`+`Activate` commands for each folder level.

### FAV_9_ → C:\PTC_Data\formats
**Used for:** Browsing to format files (.frm) for drawing sheet formats

**Mapkeys affected:**
- `dfwmba` - Watts Marine DRW Format B ASM (line 111-117)
- `dfwmbp` - Watts Marine DRW Format B PRT (line 128-134)
- `dfwmap` - Watts Marine DRW Format A PRT (line 145-151)
- `dfamfap` - AMF DRW Format A PRT (line 162-168)
- `dfamfbp` - AMF DRW Format B PRT (line 179-185)
- `dfamfba` - AMF DRW Format B ASM (line 196-202)
- `apsf` - Apply Sheet Format (line 266-272)

**Change pattern:**
```
BEFORE:
~ Activate `file_open` `pb_favorites__FAV_9_`;\

AFTER:
~ Open `file_open` `Ph_path.Path`;\
~ Close `file_open` `Ph_path.Path`;\
~ Select `file_open` `Ph_path.Path` 1 `C:`;\
~ Select `file_open` `Ph_list.Filelist` 1 `PTC_Data`;\
~ Activate `file_open` `Ph_list.Filelist` 1 `PTC_Data`;\
```
(Then existing `~ Select` and `~ Activate` commands navigate to `formats` folder)

### FAV_10_ & FAV_14_ → C:\PDM-Upload
**Used for:** Exporting OBJ, STEP, and PDF files to upload folder

**Mapkeys affected:**
- `cipdf` - Check In PDF (line 211)
- `expdf` - Export PDF to Export Folder (line 295)
- `exofa` - Export OBJ of Assembly (line 315)
- `exofp` - Export OBJ of Part (line 327 - had duplicate FAV_10_ calls)
- `exsta` - Export STEP of Assembly (line 342)

**Change pattern:**
```
BEFORE:
~ Activate `file_saveas` `pb_favorites__FAV_10_`;
(or)
~ Activate `file_saveas` `pb_favorites__FAV_14_`;

AFTER:
~ Activate `file_saveas` `computer_pb`;\
~ Select `file_saveas` `ph_list.Filelist` 1 `c:`;\
~ Activate `file_saveas` `ph_list.Filelist` 1 `c:`;\
~ Select `file_saveas` `ph_list.Filelist` 1 `PDM-Upload`;\
~ Activate `file_saveas` `ph_list.Filelist` 1 `PDM-Upload`;\
```

## Total Changes
- **12 FAV_ references** replaced with hard-coded navigation
- **1 Update command** replaced with navigation (cipdf)
- **11 mapkeys** modified total
- **2 destination paths:**
  - `C:\PTC_Data\formats` (for format files)
  - `C:\PDM-Upload` (for exports)

## Testing Instructions

1. **Backup your original config.pro:**
   ```
   copy C:\PTC_Data\config.pro C:\PTC_Data\config_BACKUP.pro
   ```

2. **Replace with fixed version:**
   ```
   copy J:\PDM-Web\config_FIXED.pro C:\PTC_Data\config.pro
   ```

3. **Restart Creo Parametric**

4. **Test each mapkey:**
   - Run `cipdf` - Should navigate to C:\PDM-Upload, with NO path in filename field
   - Run `expdf` - Should navigate to C:\PDM-Upload, with NO path in filename field
   - Run `exsta` - Should navigate to C:\PDM-Upload for STEP export
   - Run `dfamfap` - Should navigate to C:\PTC_Data\formats for format selection

   **Expected result:** The dialog should show the correct folder in the address bar, but the "New file name" field should only contain the base filename, NOT a path.

## Technical Details

### The Solution: Double-Action Navigation

The key to replacing FAV_ buttons was discovered by recording a manual navigation mapkey. The correct pattern requires:

1. **`~ Activate 'computer_pb'`** - Click the "Computer" button in the save dialog
2. **Double-action for each level** - BOTH Select AND Activate to actually "enter" folders:
   - `~ Select 'ph_list.Filelist' 1 'c:'` - Highlight the C: drive
   - `~ Activate 'ph_list.Filelist' 1 'c:'` - Enter the C: drive
   - `~ Select 'ph_list.Filelist' 1 'PDM-Upload'` - Highlight the folder
   - `~ Activate 'ph_list.Filelist' 1 'PDM-Upload'` - Enter the folder

This mimics double-clicking through the folder tree in Creo's UI.

### Failed Approaches

❌ **Using `Ph_path.Path`** - Only changed display, didn't change actual save location
❌ **Using `~ Update 'Inputname' 'C:\\PDM-Upload'`** - Put path in filename field, erased actual filename
❌ **Select without Activate** - Highlighted folder but didn't enter it, saved to working directory

### Folder Naming Notes

- **Folder names must match exactly** as they appear in Windows Explorer
- `PTC_Data` (not `PTC-Data` or `ptc_data`) - case matters
- `PDM-Upload` (with hyphen, not underscore)
- `c:` (lowercase) - as Creo displays it in the file list

## Notes

- **Activating is key:** Must Activate each folder level to actually navigate into it
- **Computer button required:** `computer_pb` ensures we start from the correct location
- **Favorites removed:** No longer dependent on Creo favorites being set up correctly
- **Portable:** These mapkeys will work on any machine with the same folder structure
