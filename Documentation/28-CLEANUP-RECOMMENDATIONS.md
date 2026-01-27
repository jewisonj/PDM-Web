# PDM System Cleanup Recommendations

## Overview

This document identifies cleanup opportunities discovered during the January 2026 codebase review. Items are organized by priority and risk level.

**Review Date:** 2026-01-26
**Reviewer:** Claude (AI Assistant)

---

## Tier 1: Safe to Delete (Zero Risk)

These items are redundant backups or auto-generated files that can be safely removed.

### Backup Directories

| Location | Contents | Size | Recommendation |
|----------|----------|------|----------------|
| `D:\PDM_PowerShell\Backups\17-Dec-2025\` | 7 old script versions | ~12 KB | Delete |
| `D:\PDM_PowerShell\Backups\Older\` | 2 very old PDM-HTMLBrowser versions | ~26 KB | Delete |
| `D:\PDM_WebServer\public\mrp\Backup\` | 6 HTML page duplicates | ~136 KB | Delete entire folder |
| `D:\FreeCAD\Tools\Backups\18-Dec-25\` | 8 Python/batch files | ~120 KB | Delete |

### Auto-Generated Files

| Location | Contents | Size | Recommendation |
|----------|----------|------|----------------|
| `D:\FreeCAD\Tools\__pycache__\` | Python bytecode (.pyc) | ~88 KB | Delete (auto-regenerated) |

### Standalone Backup Files

| File | Size | Recommendation |
|------|------|----------------|
| `D:\PDM_WebServer\public\mrp\shop_terminal.html.bak` | ~3 KB | Delete |
| `D:\PDM_WebServer\public\mrp\mrp_dashboard.html.bak` | ~4 KB | Delete |
| `D:\PDM_PowerShell\Backups\BOM-Watcher.ps1` | ~15 KB | Delete |
| `D:\PDM_PowerShell\Backups\CompareWorkspace_Simple.ps1` | ~8 KB | Delete (or document if intentional) |

**Total Space Recovered: ~412 KB**

### Cleanup Commands

```powershell
# Run these commands to clean up Tier 1 items
# RECOMMENDED: Review contents first before deleting

# Backup folders
Remove-Item "D:\PDM_PowerShell\Backups\17-Dec-2025" -Recurse -Force
Remove-Item "D:\PDM_PowerShell\Backups\Older" -Recurse -Force
Remove-Item "D:\PDM_WebServer\public\mrp\Backup" -Recurse -Force
Remove-Item "D:\FreeCAD\Tools\Backups\18-Dec-25" -Recurse -Force

# Python cache
Remove-Item "D:\FreeCAD\Tools\__pycache__" -Recurse -Force

# Standalone backup files
Remove-Item "D:\PDM_WebServer\public\mrp\shop_terminal.html.bak" -Force
Remove-Item "D:\PDM_WebServer\public\mrp\mrp_dashboard.html.bak" -Force
Remove-Item "D:\PDM_PowerShell\Backups\BOM-Watcher.ps1" -Force
Remove-Item "D:\PDM_PowerShell\Backups\CompareWorkspace_Simple.ps1" -Force
```

---

## Tier 2: Documentation Consolidation (Low Risk)

### Duplicate Documentation Files

The numbered documentation (`01-*.md`, `02-*.md`, etc.) is the canonical set. Older non-numbered duplicates should be removed.

| Duplicate File | Keep Instead | Action |
|---------------|--------------|--------|
| `D:\Documentation\PDM_COMPLETE_OVERVIEW.md` | `02-PDM-COMPLETE-OVERVIEW.md` | Delete duplicate |
| `D:\Documentation\PDM_SYSTEM_MAP.md` | `01-PDM-SYSTEM-MAP.md` | Delete duplicate |
| `D:\Documentation\DOCUMENTATION_UPDATES_2025-01-03.md` | `16-DOCUMENTATION-UPDATES-SUMMARY.md` | Delete obsolete |

### Skills Folder Redundancy

The `D:\Skills\` folder contains copies of documentation already in `D:\Documentation\`:

| Skills File | Documentation Equivalent | Recommendation |
|-------------|-------------------------|----------------|
| `database_schema.md` | `03-DATABASE-SCHEMA.md` | Keep Skills version for AI context |
| `services.md` | `04-SERVICES-REFERENCE.md` | Keep Skills version for AI context |
| `freecad_automation.md` | `12-FREECAD-AUTOMATION.md` | Keep Skills version for AI context |
| `DEVELOPMENT-NOTES-workspace-comparison.md` | `15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md` | Keep Skills version for AI context |

**Recommendation:** Keep both locations but ensure Skills folder is clearly marked as "AI Context Files" and Documentation folder as "Canonical Documentation". Consider adding a note to Skills folder README explaining its purpose.

### Cleanup Commands

```powershell
# Remove duplicate documentation
Remove-Item "D:\Documentation\PDM_COMPLETE_OVERVIEW.md" -Force
Remove-Item "D:\Documentation\PDM_SYSTEM_MAP.md" -Force
Remove-Item "D:\Documentation\DOCUMENTATION_UPDATES_2025-01-03.md" -Force
```

---

## Tier 3: Code Quality Issues (Medium Priority)

### TODO/FIXME Items Found

| File | Line | Issue | Priority |
|------|------|-------|----------|
| `D:\PDM_WebServer\public\mrp\shop_terminal.html` | 386 | `// TODO: fetch from part_completion` - incomplete functionality | Medium |

**Recommendation:** Implement the part_completion fetch or document why it's hardcoded to 0.

### Debug Statements to Clean

| File | Issue | Recommendation |
|------|-------|----------------|
| `D:\PDM_PowerShell\Get-McMasterPrint.ps1` | Lines 42-43 have DEBUG output | Add -Debug parameter or remove |
| `D:\PDM_PowerShell\CompareWorkspace.ps1` | Line 135 has DEBUG logging | Control with logging level |

### NPM Deprecated Packages

The web server uses deprecated npm packages:

| Package | Issue | Recommendation |
|---------|-------|----------------|
| `@npmcli/fs` | Deprecated | Update npm dependencies |
| `glob` v7 | Unsupported (use v9+) | Update |
| `mkdirp` v1 | Memory leak (use v3+) | Update |
| `rimraf` < v4 | Unsupported | Update |

**Fix:**
```powershell
cd D:\PDM_WebServer
npm update
npm audit fix
```

---

## Tier 4: Documentation & Clarity (Low Priority)

### Scripts Needing Better Documentation

| Script | Status | Recommendation |
|--------|--------|----------------|
| `Release-Watcher.ps1` | Stub (In Development) | Add clear "NOT IMPLEMENTED" banner |
| `Revise-Watcher.ps1` | Stub (In Development) | Add clear "NOT IMPLEMENTED" banner |

### FreeCAD Tools Clarity

The FreeCAD Tools folder has multiple similar scripts:

| File Set | Question | Recommendation |
|----------|----------|----------------|
| `flatten_sheetmetal.bat` vs `Flatten sheetmetal portable.py` | Which is primary? | Document relationship |
| `create_bend_drawing.bat` vs `create_bend_drawing_open.bat` | What's the difference? | Add comments to batch files |
| `convert_to_obj.py/bat`, `convert_to_stl.py/bat` | Are these used? | Document or archive if unused |

### Potentially Unused Files

Review whether these are still needed:

| File | Purpose | Recommendation |
|------|---------|----------------|
| `D:\FreeCAD\Tools\convert_to_obj.py` | OBJ conversion | Check if used by any workflow |
| `D:\FreeCAD\Tools\convert_to_stl.py` | STL conversion | Check if used by any workflow |
| `D:\FreeCAD\Tools\process_all.bat` | Batch processing | Check if used |
| `D:\FreeCAD\Tools\detect_modules.py` | Module detection | Check if used |

---

## Tier 5: Maintenance Tasks (Ongoing)

### Log Rotation

**Issue:** Log files grow indefinitely.

**Location:** `D:\PDM_Vault\logs\`
- `pdm.log` - Main system log
- `workspace-compare.log` - Comparison service log

**Recommendation:** Implement log rotation:
```powershell
# Add to PDM-Library.ps1 or create separate maintenance script
$maxLogSize = 10MB
$keepFiles = 5

function Rotate-Log {
    param([string]$LogPath)
    if ((Get-Item $LogPath -ErrorAction SilentlyContinue).Length -gt $maxLogSize) {
        # Rotate logic here
    }
}
```

### Database Maintenance

Run periodic cleanup:
```powershell
# Monthly database maintenance
& "D:\PDM_PowerShell\PDM-Database-Cleanup.ps1" -DryRun

# If dry run looks good:
& "D:\PDM_PowerShell\PDM-Database-Cleanup.ps1"
```

### Node.js Dependencies

Periodically check for vulnerabilities:
```powershell
cd D:\PDM_WebServer
npm audit
npm outdated
```

---

## Summary Statistics

| Category | Count | Size |
|----------|-------|------|
| Backup directories to delete | 4 | ~294 KB |
| Backup files to delete | 6 | ~118 KB |
| Python cache to delete | 7 files | ~88 KB |
| Documentation duplicates | 3 | ~50 KB |
| **Total recoverable space** | | **~550 KB** |

| Code Quality | Count |
|--------------|-------|
| TODO comments found | 1 |
| Debug statements | 3 |
| Deprecated npm packages | 4+ |
| Scripts needing docs | 2 |

---

## Execution Checklist

### Immediate (This Session)

- [ ] Review Tier 1 items for anything important
- [ ] Delete Tier 1 backup folders
- [ ] Delete Python cache

### This Week

- [ ] Remove documentation duplicates
- [ ] Run npm update on web server
- [ ] Add "IN DEVELOPMENT" banners to stub scripts

### This Month

- [ ] Implement log rotation
- [ ] Document FreeCAD tools purpose
- [ ] Review potentially unused converters
- [ ] Fix TODO in shop_terminal.html

### Ongoing

- [ ] Run database cleanup monthly
- [ ] Check npm vulnerabilities monthly
- [ ] Monitor log file sizes

---

**Document Version:** 1.0
**Created:** 2026-01-26
**Status:** Ready for Review
