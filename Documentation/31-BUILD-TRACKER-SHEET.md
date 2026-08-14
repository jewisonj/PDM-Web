# Shop-Floor Build Tracker Sheet Reference

## Overview

The Build Tracker Sheet is a printable, per-project progress sheet for the shop floor: the whole project laid out on paper, with a box for every station a part needs to pass through. It is the paper twin of the same completion data that drives the Gantt (`MrpProjectTrackingView`) and the digital Shop view (`MrpShopView`) -- generated fresh from live data every time it's printed, with already-recorded progress pre-filled as solid black boxes so a reprint mid-project resumes exactly where the shop left off.

**Key Features:**
- Fab parts grouped under their parent weldment/assembly, one row per part with a checkbox per station
- Weldments/assemblies matrix (JIG/LW/HW/WCU/ASM/INS columns) as a second table
- Derived build milestones (op 10-70) with plan dates computed from the scheduling engine
- Purchased-parts receive checklist (ORD/RCV columns, long-lead flag)
- Daily log block and shortages block for handwritten shop notes
- Pre-fill toggle: off prints a blank sheet, on prints already-completed stations as solid boxes
- Two print formats: 11x17 tabloid (one page) or 8.5x11 landscape letter (parts pages + a dedicated status page)
- Designed for a later AI photo-capture phase: every row has a printed ID, three corner anchor squares, dropout-gray shading, and a QR code linking back to the live sheet

**Architecture:** A pure data-shaping module (`buildTracker.ts`, no Supabase access) turns raw project/BOM/routing/completion rows into a fully laid-out `TrackerSheet` structure. A view component (`MrpBuildTrackerView.vue`) fetches the raw data with the same query pattern as `MrpProjectTrackingView`, runs the existing scheduling engine for milestone dates, and renders the sheet as CSS Grid "paper" divs styled for print.

---

## Where It Lives

**Route:** `/mrp/tracker/:projectCode` (named `mrp-build-tracker`, `requiresAuth: true`)

**Entry point:** MRP Project Tracking (`/mrp/tracking`) -> select a project -> "Print Build Tracker Sheet" button -> opens `/mrp/tracker/{projectCode}`

**Files:**

| File | Role |
|------|------|
| `frontend/src/utils/buildTracker.ts` | Pure data-shaping: classification, ordering, box computation, milestones, pagination. No Supabase calls. |
| `frontend/src/utils/buildTracker.test.ts` | 15 Vitest unit tests against a miniature fixture project (first unit test file in the project besides `scheduling.test.ts`). |
| `frontend/src/views/MrpBuildTrackerView.vue` | Loads data from Supabase, calls `calculateSchedule()` and `buildTrackerSheet()`, renders the printable pages. |
| `frontend/src/router/index.ts` | Route registration for `/mrp/tracker/:projectCode`. |
| `frontend/src/views/MrpProjectTrackingView.vue` | "Print Build Tracker Sheet" button and `openBuildTracker()` navigation helper. |
| `.claude/launch.json` | New dev-server launch config for the frontend (port 5174). |

**Run the unit tests:**

```bash
cd frontend
npx vitest run
```

---

## Data Flow

```
1. User selects a project in MRP Project Tracking (/mrp/tracking)
   and clicks "Print Build Tracker Sheet"
         |
2. Router navigates to /mrp/tracker/{projectCode}
   (MrpBuildTrackerView.vue mounts)
         |
3. View queries Supabase directly (same pattern as MrpProjectTrackingView):
   mrp_projects, mrp_project_parts (+ items), bom, routing (+ workstations),
   part_completion, workstations
         |
4. calculateSchedule() runs (frontend/src/utils/scheduling.ts) to get
   task end days for milestone plan dates
         |
5. buildTrackerSheet() (frontend/src/utils/buildTracker.ts) shapes the
   raw rows into a TrackerSheet: classified parts, DFS assembly order,
   per-station boxes, milestones, purchased checklist, pagination
         |
6. QRCode.toDataURL() renders a QR PNG encoding the tracker's own URL
         |
7. View renders paper pages with CSS Grid, injects a per-format
   @page size <style> block, and the browser Print dialog does the rest
```

---

## Item Classification

Every item in the project is classified once (`classOf` cache in `buildTracker.ts`) into one of four buckets:

| Class | Rule |
|-------|------|
| `ref` | Item number starts with `zz` -- reference-only, excluded from the sheet entirely |
| `purchased` | Item number starts with `mmc` or `spn`, OR routed only through Receiving with no fab/weld stations |
| `assembly` | Has BOM children AND (routed through a Weld/Assembly station group OR has non-reference, non-purchased-prefixed children as a routing-less fallback) |
| `made` | Everything else -- gets a row with per-station checkboxes on a fab parts page |

**IMPORTANT:** Classification depends on `workstations.station_group` (Fabrication / Weld / Assembly / QC / Outsourced) matching the same groups used by the Cost Report (see `24-VERSION-HISTORY.md` v3.6). If a routing operation points at a station with no `station_group` set, that station contributes nothing to the fab/weld signal used for classification.

---

## Assembly Ordering

Assemblies are ordered by a depth-first, post-order traversal starting from `mrp_projects.top_assembly_id`:

1. Visit the top assembly's children first (recursively), marking each visited assembly
2. Push the assembly itself onto `asmOrder` only after all its assembly children are visited (post-order — sub-assemblies print before their parents)
3. Any assemblies not reachable from `top_assembly_id` (orphaned in the project data) are appended afterward, sorted alphabetically by item number

Assembly row IDs (`A01`, `A02`, ...) are assigned in this traversal order, so a lower-numbered assembly is either a sub-assembly of a higher-numbered one or independent of it -- never the other way around.

---

## Station Columns

Two fixed column sets map `workstations.station_name` values to printed columns. Columns are **not** configurable via UI -- they are hardcoded constants exported from `buildTracker.ts`.

**Fab parts columns (`PART_COLUMNS`):**

| Column | Station(s) folded in |
|--------|----------------------|
| SAW | Saw |
| WJ | Waterjet |
| BRK | Press Brake |
| BND | Pipe Bending, Hole Punch - Iron Worker |
| DBR | Deburr |
| INS | Inspection |
| ▸STG | Part Staging (`gate: true`, `alwaysApplicable: true`) |

**Assembly matrix columns (`ASM_COLUMNS`):**

| Column | Station(s) folded in |
|--------|----------------------|
| JIG | Weld Jigging |
| LW | Light Weld |
| HW | Heavy Weld |
| WCU | Weld Cleanup |
| ASM | Mechanical Assembly, Plumbing, Wiring |
| INS | Inspection |

**Column flags:**
- `gate: true` -- rendered shaded with a heavy left border to mark a shop handoff point (e.g. ▸STG marks "ready to move to fab/weld")
- `alwaysApplicable: true` -- the box is drawn open even when the station isn't in the item's routing (currently only ▸STG, so every made-part row always shows a staging box)

**KNOWN LIMITATION:** Part-level weld operations that live in a *part's own* routing (e.g. `csp00210` having JIG/LW steps directly, rather than picking them up at the assembly level) are not surfaced as part columns -- they're only reflected in the assembly matrix. Plumbing and Wiring stations both fold into the single ASM column, so those operations are not separately trackable on the sheet.

---

## Pre-Fill / Completion Semantics

Completion semantics intentionally match `MrpShopView` exactly: **one `part_completion` row per (project, item, station)**, upserted with `qty_complete`. A station box is "done" when the recorded quantity for that (item, station) pair covers the item's full project quantity (`mrp_project_parts.quantity`, not a per-row split).

Box states, computed by `colState()` / `partBox()` in `buildTracker.ts`:

| State | Rendering | Condition |
|-------|-----------|-----------|
| Not applicable | Column blacked out / no box | Station not in the item's routing (and column isn't `alwaysApplicable`) |
| Done | Solid black box | Recorded `qty_complete` >= project quantity for every station folded into that column |
| Partial | Open box with printed tally number | Recorded `qty_complete` > 0 but < project quantity |
| Open | Open box, blank | Station applicable, nothing recorded yet |

**Duplicate rows of the same item** (e.g. a part used both directly on a parent assembly and inside a sub-assembly of that same parent) allocate partial quantity across rows in order via `allocRemaining` -- the first row printed claims completed quantity first, remaining rows get whatever is left, so the same physical inventory isn't double-counted as "done" on two rows.

The "Pre-fill recorded progress" toggle in the toolbar is a **display-only** switch in the view (not a query parameter) -- unchecking it renders every box as open regardless of what `part_completion` says, producing a blank sheet for a brand-new project run.

---

## Milestones

Seven standard milestones (`M10`-`M70`, op numbers 10-70) are always generated, derived from the schedule and completion data rather than being stored anywhere:

| ID | Op | Title | Plan date source |
|----|----|-------|-------------------|
| M10 | 10 | All purchased parts ordered | Project start date |
| M20 | 20 | All purchased received & staged | Latest scheduled end day among Receiving tasks |
| M30 | 30 | ALL PARTS CUT & DEBURRED -- TO FAB (gate) | Latest scheduled end day among Fabrication-group tasks |
| M40 | 40 | All weldments welded & cleaned | Latest scheduled end day among Weld-group tasks |
| M50 | 50 | Mechanical & final assembly complete | Latest scheduled end day among Assembly-group tasks |
| M60 | 60 | Final inspection complete | Latest scheduled end day among Inspection tasks |
| M70 | 70 | Crate & ship | Project due date |

Plan dates are computed with `addWorkingDays(startDate, endDay)` using the same working-day convention as the scheduling engine (see `20-COMMON-WORKFLOWS.md` section 15). "Actual" dates only populate once every task in that phase is complete, using the latest `completed_at` timestamp recorded for that phase's (item, station) rows.

Project `start_date` is used if set on `mrp_projects`; otherwise it's derived by subtracting the schedule's `total_days` from `due_date`.

---

## Purchased Parts Checklist

Purchased items get a compact receive checklist instead of per-station boxes:

- **Long-lead flag:** any item **not** prefixed `mmc` (i.e. `spn` or receive-only-routed `csp`/other prefixes) is flagged `longLead: true` and gets both an ORD and RCV column; plain `mmc` (McMaster-Carr) items only get RCV, since they're stock hardware with no meaningful order-lead tracking on this sheet.
- **RCV done/partial:** computed off the `Receiving` station's `part_completion` row, same done/partial logic as the fab columns.
- **ORD is never pre-filled** -- there's no data source for "ordered" in the current schema, so `ordDone` is always `false` and the box is left for the shop to mark by hand. This is a deliberate placeholder for a future purchasing-status field.
- Sort order: `mmc` items last, everything else (long-lead) first, alphabetical within each group.

---

## Print Formats and Pagination

Format is chosen via a toolbar toggle and passed as a query param (`?size=letter`); it also drives a dynamically injected `@page` CSS rule so the browser print dialog picks up the right paper size and orientation automatically.

| Format | Layout | Row cap per column | Notes |
|--------|--------|----------------------|-------|
| Tabloid (11x17) | Two columns per page, right rail (milestones/purchased/log) shares page 1 with the parts groups | 48 rows, with the rail's row count reserved out of the first page's second column budget | Whole project on one physical sheet whenever it fits |
| Letter (8.5x11 landscape) | Two columns per parts page, additional pages added as needed | 32 rows | Ends with a dedicated final "Assemblies & Status" page carrying the assembly matrix, milestones, purchased checklist, and log -- these never share a page with parts groups in letter format |

Pagination (`buildTrackerSheet()`'s final block) packs assembly groups column-by-column, splitting a group across pages/columns when it doesn't fit and marking the continuation with `cont: true` so the view can print a "(cont.)" marker on the group header instead of repeating it fully.

**Fit-to-width scaling:** the view also computes a live CSS `scale` factor so the on-screen preview fits the browser viewport; this is a display convenience only and does not affect the printed @page size.

---

## Design Decisions (User-Confirmed)

These choices were explicitly confirmed with the user before implementation and should not be "corrected" without checking back:

1. **Per-station boxes, not one box per phase.** Each fab part gets a checkbox for every individual station in its routing (SAW/WJ/BRK/BND/DBR/INS/STG), not a single "fab complete" box. This mirrors how the shop actually signs off work station by station.
2. **Heavy-X pen marking convention, with written quantity for partials.** The physical marking convention for a box on paper is a heavy X in pen; partial completions get the quantity handwritten next to/inside the box rather than a fraction of shading.
3. **Purchased items get a compact receive checklist, not per-station boxes.** Long-lead (`spn`, receive-only `csp`) items get ORD+RCV columns; `mmc` stock hardware gets RCV only.
4. **Phased rollout, web print view first.** This sheet is phase 1: a static, regenerate-and-print web view. A tablet-based interactive mode (checking boxes live on a tablet instead of paper) and a Claude-vision photo-sync pipeline (photographing a marked-up paper sheet and having it read progress back into `part_completion`) are explicitly deferred to future phases -- the row-ID scheme, corner anchors, and QR code are built now specifically so that future phase doesn't require reworking the layout.

**Approved visual mockup:** https://claude.ai/code/artifact/0f926826-c666-4904-a92b-7889314006f7

---

## One-Click Sharing (v3.9.10+)

**Feature:** Generate a PDF snapshot of the tracker and create a permanent public link in one click.

**Use Case:** Share project status with external stakeholders (customers, vendors, subcontractors) without requiring them to have login access to the PDM system.

### How It Works

**Workflow:**
1. User clicks the **Share** button in the tracker toolbar
2. System captures each `.paper` element as a high-resolution canvas (html2canvas at 2x scale)
3. Generates a multi-page PDF with correct paper dimensions (jsPDF):
   - Letter: 11in × 8.5in landscape
   - Tabloid: 17in × 11in landscape
4. Uploads PDF to Supabase Storage `shared` bucket with public read access
5. Creates metadata record in `shared_links` table (kind='tracker')
6. Returns permanent public URL: `https://{domain}/shared/tracker/{uuid}`
7. Automatically copies URL to clipboard
8. Displays success banner with shareable link

**Button States:**
- **Normal:** "Share" button with share icon
- **Processing:** "Sharing..." with disabled state (3-5 seconds typical)
- **Success:** Green banner with link (auto-clears after 8 seconds)
- **Error:** Red banner with error message (persists until dismissed)

### Technical Implementation

**Client-Side PDF Generation:**
- **html2canvas:** Captures DOM elements as canvas (each `.paper` page)
- **jsPDF:** Assembles multi-page PDF document
- **Transform handling:** Temporarily removes CSS `transform` during capture for pixel-accurate rendering, then restores after capture
- **Resolution:** 2x scale for print quality (1056px or 1632px width at 2x = 2112px or 3264px)
- **Compression:** JPEG at 0.95 quality for reasonable file size (typically 200-500KB per page)

**Upload API:**
- **Endpoint:** `POST /api/share` (multipart form data)
- **Payload:**
  - `file`: PDF blob as File object
  - `kind`: 'tracker'
  - `project_code`: Project code for linking
  - `title`: Descriptive title (e.g., "WM_0513 Build Tracker 2026-08-11")
- **Response:** `{ id, public_url, file_name, size_bytes, ... }`

**Storage:**
- **Bucket:** `shared` (Supabase Storage, public read access)
- **Path:** `tracker/{uuid}.pdf` (UUID assigned by backend)
- **Database:** `shared_links` table tracks metadata
- **Public URL:** `https://{supabase-project}.supabase.co/storage/v1/object/public/shared/tracker/{uuid}.pdf`

**Filename Convention:**
- Pattern: `TRK_{projectCode}_{date}_{LTR?}.pdf`
- Examples:
  - Tabloid: `TRK_WM_0513_2026-08-11.pdf`
  - Letter: `TRK_SPA0030_2026-08-11_LTR.pdf`

### Benefits

**External Stakeholder Access:**
- No login credentials required
- Link can be shared via email, Slack, etc.
- PDF opens directly in browser or PDF viewer
- Works on any device (desktop, tablet, mobile)

**Snapshot Preservation:**
- Captured state reflects completion status at time of sharing
- Pre-fill toggle honored (on = shows completed work, off = blank sheet)
- Permanent record of project status at specific milestone
- Multiple snapshots can be shared over project lifecycle

**Workflow Efficiency:**
- **Before (v3.9.9):** 9 steps (print to PDF, upload, copy link)
- **After (v3.9.10):** 4 steps (click Share, wait, paste link)
- Eliminates manual file management
- No local file storage needed
- Clipboard integration for immediate paste

### Managing Shared Links

**Viewing Links:**
- Navigate to Shares management page (`/shares`)
- Filter by project code to see all shared documents
- View file size, creation date, and document type

**Revoking Links:**
- Click "Revoke" button next to a link
- Deletes PDF from storage bucket
- Removes record from `shared_links` table
- Public URL becomes inaccessible

**Re-Sharing:**
- Generate fresh snapshot by clicking Share again
- New link created with updated completion status
- Old link remains valid unless manually revoked

### Dependencies

**NPM Packages:**
```json
{
  "html2canvas": "^1.4.1",  // DOM-to-canvas rendering
  "jspdf": "^4.2.1"         // PDF document generation
}
```

**Import Statement (MrpBuildTrackerView.vue):**
```typescript
import html2canvas from 'html2canvas'
import { jsPDF } from 'jspdf'
import { uploadSharedPdf } from '../services/shareApi'
```

### Code Location

**Primary Implementation:**
- **File:** `frontend/src/views/MrpBuildTrackerView.vue`
- **Function:** `shareTracker()` (lines 174-249)
- **Template:** Share button and success/error banners

**API Client:**
- **File:** `frontend/src/services/shareApi.ts`
- **Function:** `uploadSharedPdf()` - Handles multipart form upload to `/api/share`

**Backend Endpoint:**
- **File:** `backend/app/routes/share.py`
- **Endpoint:** `POST /api/share`
- **Function:** Uploads to storage, creates database record, returns public URL

### Related Features

This sharing implementation is identical to the Design Book sharing feature (v3.9.7) and uses the same:
- Backend `/api/share` endpoint
- `shared` bucket in Supabase Storage
- `shared_links` database table
- `uploadSharedPdf()` API client function
- Public URL pattern and access control

See `43-DESIGN-BOOK-IMAGE-MANAGEMENT.md` and `45-SHARED-LINKS.md` for the broader shared links architecture.

---

## Photo-Capture Readiness (Future Phase)

The sheet is deliberately over-engineered for a feature that doesn't exist yet, so the current print layout doubles as the input format for a later photo-based progress sync:

- **Printed row IDs:** every row carries a stable ID -- `F##` (fab parts, sequential across the whole sheet), `A##` (assemblies, in DFS post-order), `P##` (purchased parts), `M##` (milestones, fixed 10-70). These IDs are generated by the same pure function that will eventually parse a photographed sheet back into structured data, so ID assignment logic only has to be written once.
- **Three corner anchor squares:** printed on the page for perspective/rotation correction when a phone photo of the sheet is processed.
- **QR code:** encodes the tracker's own URL (`{origin}/mrp/tracker/{projectCode}`) so a photo of the sheet can be resolved back to the exact project/format it came from without OCR.
- **Dropout-gray shading:** background shading tuned to be a color a copier/scanner drops out but that a camera can still separate from pen marks, keeping the printed grid visually light while remaining machine-legible.

None of this is wired to an actual capture pipeline yet -- it is groundwork only.

---

## Known Issues / Notes

- **Pre-existing `PdfMeasure.vue` TypeScript errors** still fail `npm run build`. This is unrelated to the Build Tracker feature and has been flagged separately; it does not block using the tracker in dev (`npm run dev`) since it's a build-time-only failure in an unrelated file.
- **`mrp_project_parts` flat quantities can disagree with the BOM-tree rollup** -- this is a known, previously-documented BOM rollup issue (see `06-BOM-COST-ROLLUP-GUIDE.md`). The tracker sidesteps it by grouping parts from the BOM tree directly and computing each row's quantity as `bom.quantity x parent project quantity`, rather than trusting the flat `mrp_project_parts.quantity` rollup for grouped rows.
- **Part-level weld ops** (see Station Columns above) are not shown as fab-part columns; they only show up at the assembly level.
- **Plumbing and Wiring** both fold into the single ASM column in the assembly matrix -- they are not separately trackable stations on this sheet.

---

## Cross-References

- **Scheduling engine:** `20-COMMON-WORKFLOWS.md` section 15 (Project Scheduling and Capacity Planning) -- the tracker's milestone plan dates are a direct consumer of `calculateSchedule()` from `frontend/src/utils/scheduling.ts`.
- **Completion data model:** `part_completion` table, same one used by `MrpShopView` -- see `03-DATABASE-SCHEMA.md`.
- **Station groups:** `24-VERSION-HISTORY.md` v3.6 (Station Grouping and Cost Report Enhancements) -- the tracker's assembly classification and milestone phases both key off `workstations.station_group`.
- **BOM rollup caveats:** `06-BOM-COST-ROLLUP-GUIDE.md`.
