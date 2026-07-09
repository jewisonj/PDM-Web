# PDM-Web UI/UX Design Standards

**Last Updated:** 2026-07-09
**Applies To:** Frontend (Vue 3) and Backend (print packets, reports)
**Version:** v3.9.2

This document defines consistent UI/UX patterns, formatting rules, and display conventions for PDM-Web.

---

## Part Number Display Formatting

### Standard: Prefix Stripping for Clean Display

When displaying part numbers in UI tables, reports, print packets, and shop floor documents, **strip specific prefixes** to improve readability and reduce visual clutter.

#### Strip These Prefixes

| Prefix | Type | Example Input | Display Output | Rationale |
|--------|------|---------------|----------------|-----------|
| `MMC` | McMaster-Carr | `MMC2866T14` | `2866T14` | McMaster catalog numbers are self-explanatory; the prefix adds noise |
| `SPN` | Supplier Part | `SPNtank` | `tank` | Supplier part numbers are descriptive; the prefix is internal metadata |

#### Keep These Prefixes

| Prefix | Type | Example | Rationale |
|--------|------|---------|-----------|
| `CSA` | In-house Assembly | `CSA0030` | Meaningful identifier for shop floor |
| `CSP` | In-house Part | `CSP1024` | Meaningful identifier for shop floor |
| `HBL` | Hose/Belt | `HBL0015` | Meaningful category identifier |
| `STA` | Standard Assembly | `STA2030` | Meaningful category identifier |
| `STP` | Standard Part | `STP0512` | Meaningful category identifier |
| `WMA` | Weldment Assembly | `WMA20120` | Meaningful category identifier |
| `WMP` | Weldment Part | `WMP0045` | Meaningful category identifier |
| `XXA` | Experimental Assembly | `XXA0001` | Meaningful category identifier |
| `XXP` | Experimental Part | `XXP0002` | Meaningful category identifier |
| `ZZZ` | Reference/Document | `ZZZ0100` | Indicates special handling (do not strip) |

**Rule of thumb:** In-house part prefixes (`CSx`, `WMx`, `STx`, `HBL`, `XXx`) are meaningful to the shop floor and should always be preserved. External part prefixes (`MMC`, `SPN`) are metadata that can be hidden for cleaner display.

---

### Implementation Locations

#### Backend: Print Packet Service

File: `backend/app/services/print_packet.py`

**Functions that implement prefix stripping:**

1. **Cover sheet part number display** (line ~384)
   ```python
   # Part number cell - strip MMC/SPN prefixes for display
   pn_lower = part_number.lower()
   display_pn = part_number
   if pn_lower.startswith("mmc") or pn_lower.startswith("spn"):
       display_pn = part_number[3:]  # Strip first 3 characters
   ```

2. **Tracking sheet BOM lists** (line ~1182)
   ```python
   if show_link and pn_lower.startswith("mmc"):
       # McMaster link - strip MMC prefix
       display_pn = pn[3:]
   elif pn_lower.startswith("spn"):
       # Supplier part - strip SPN prefix
       display_pn = pn[3:]
   ```

3. **PDF stamp overlays** (line ~1343)
   ```python
   # Draw stamp content - strip MMC/SPN prefixes for display
   pn_lower = pn.lower()
   display_pn = pn[3:] if pn_lower.startswith("mmc") or pn_lower.startswith("spn") else pn
   ```

**Print outputs affected:**
- Cover sheets (project summary)
- Tracking sheets (BOM tables)
- PDF stamp overlays (part identification)

#### Frontend: MRP Dashboard View

File: `frontend/src/views/MrpDashboardView.vue`

**Helper function** (line ~131):
```typescript
// Format part number for display - strips MMC/SPN prefixes
function formatPartNumber(pn: string): string {
  const lower = pn.toLowerCase()
  if (lower.startsWith('mmc') || lower.startsWith('spn')) {
    return pn.substring(3)  // Strip first 3 characters
  }
  return pn
}
```

**UI locations using `formatPartNumber()`:**
- Build Tracker sheet part lists (line ~1477, ~1532)
- Build Book timeline part references
- Manufacturing schedule displays

---

### Usage Guidelines

#### When to Apply

✅ **DO strip prefixes:**
- Shop floor print packets
- Build Tracker sheets
- Build Book part lists
- Manufacturing schedules
- BOM tables in reports
- Part identification stamps on PDFs

✅ **DO preserve prefixes:**
- Engineering database views (PDM Browser)
- Part number search/filter inputs
- API responses (always use full part number)
- File paths and storage keys
- Database records (always store full part number)

#### Code Pattern

**Backend (Python):**
```python
def format_part_number_display(part_number: str) -> str:
    """Strip MMC/SPN prefixes for cleaner display."""
    pn_lower = part_number.lower()
    if pn_lower.startswith("mmc") or pn_lower.startswith("spn"):
        return part_number[3:]
    return part_number
```

**Frontend (TypeScript):**
```typescript
function formatPartNumber(pn: string): string {
  const lower = pn.toLowerCase()
  if (lower.startsWith('mmc') || lower.startsWith('spn')) {
    return pn.substring(3)
  }
  return pn
}
```

---

## Related Standards

### Item Numbering Format

See `02-PDM-COMPLETE-OVERVIEW.md` and `18-GLOSSARY-TERMS.md` for full item numbering conventions:

- **Format:** 3 uppercase letters + 4-6 digits
- **Storage:** Lowercase in database
- **Display:** Uppercase in UI (except where stripped per above rules)
- **Examples:** `CSP0030`, `WMA20120`, `MMC2866T14`, `SPNtank`

### Database Storage

**IMPORTANT:** Always store the **full part number** in the database, including all prefixes. Prefix stripping is a **display-only** operation that happens at render time.

**Correct:**
- Database: `mmc2866t14` (lowercase, full prefix)
- Display: `2866T14` (uppercase, stripped prefix)

**Incorrect:**
- Database: `2866t14` (missing prefix - breaks lookups!)

---

## Future Design Standards

This document will be expanded with additional UI/UX standards as they are formalized:

- Badge color conventions (lifecycle states, item types, task statuses)
- Table density and column sizing
- Panel slideout animations
- Icon usage (PrimeIcons)
- Dark theme vs light theme usage (MRP vs PDM)
- Button hierarchy (primary, secondary, danger)
- Form validation patterns
- Loading states and skeletons
- Error message formatting

---

## Version History

| Date | Version | Change |
|------|---------|--------|
| 2026-07-09 | v3.9.2 | Initial creation - documented part number prefix stripping standard |

---

## Related Documentation

| Document | Content |
|----------|---------|
| `10-PDM-WEBSERVER-OVERVIEW.md` | Frontend architecture, component patterns |
| `11-PDM-WEBSERVER-QUICK-REFERENCE.md` | Daily operations reference |
| `02-PDM-COMPLETE-OVERVIEW.md` | Item numbering conventions |
| `18-GLOSSARY-TERMS.md` | Terminology and acronyms |
| `31-BUILD-TRACKER-SHEET.md` | Shop floor build tracker (uses formatting) |
| `32-BUILD-BOOK.md` | Manufacturing build book (uses formatting) |
