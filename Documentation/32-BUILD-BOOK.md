# Manufacturing Build Book Reference

## Overview

The Build Book is a printable, day-by-day manufacturing book for a single MRP project: a cover/plan page, a station-loading calendar, sequence-numbered work packages for every primary part operation, and one kit/weld sheet per assembly. It is generated live from the same capacity-constrained scheduler (`calculateSchedule()`) that drives the Gantt (`MrpProjectTrackingView`), and it reuses the Build Tracker's classification/ordering/milestone logic (`buildTrackerSheet()`) rather than duplicating it.

Where the Build Tracker Sheet (`31-BUILD-TRACKER-SHEET.md`) is a checkbox grid the shop marks up over the life of a project, the Build Book is closer to a work-order packet: it tells the shop **what to build, in what order, with what stock, feeding which kit** -- one card per unit of work.

**Key Features:**
- Cover/plan page: project stats, milestones with plan dates, hours by station-group area, a stock-pull summary aggregated from `routing_materials`, and (as of v3.9.1) a **REFERENCE PRINTS -- READ FIRST** table listing controlled documents (see Document Items below)
- Day-by-day station-loading calendar built directly from the scheduler's `stationDays` grid
- Part I -- Work Packages: one card per (planned day, station) group of part tasks, sequence-numbered `PKG 01`, `PKG 02`, ... in dependency order. **Secondary operations (Deburr, Inspection -- `SECONDARY_STATIONS` in `buildBook.ts`) get no package cards and no print sets**: they happen at the tail of every primary op (operator judgment -- "no sharp corners, dimensions right"), so a line's "NEXT ->" points to the next *primary* station and stage-kit handoffs land on the last primary op's package. They remain per-part checkboxes on the Tracker sheet and steps in assembly kit sequences.
- Part II -- Kit & Weld Sheets: one card per weldment/assembly in the same DFS build order as the Tracker, with a kit parts list, weld/assembly sequence, a **PULL PRINTS** reference line (drawing numbers + revisions), and print availability
- Already-recorded-complete packages/lines print with filled checkboxes and a "RECORDED COMPLETE" badge, same completion semantics as the Tracker and `MrpShopView`
- **Sequence-first, dates-advisory:** package numbers (`PKG NN`) are the thing the shop should follow; planned days are printed as guidance only, so the book stays usable when the schedule drifts (see Design Decisions)
- **Section print sets (v3.9.1):** a toolbar dropdown + "Download prints" button generates a small, task-sized PDF of just one section's drawings (a reference set, one work package, or one kit) instead of the whole project's prints -- see the dedicated section below

**Architecture:** A pure data-shaping module (`buildBook.ts`, no Supabase access) composes on top of `buildTrackerSheet()` (for classification, assembly ordering, milestones) and a `ScheduleResult` (for task timing and station-day loading) to produce a `BuildBook` structure. A view component (`MrpBuildBookView.vue`) fetches the raw data plus two new queries the Tracker doesn't need (`routing_materials` and `files`), and renders the book as flowing paper "sheet" divs styled for print.

---

## Where It Lives

**Route:** `/mrp/book/:projectCode` (named `mrp-build-book`, `requiresAuth: true`)

**Entry points:**
- MRP Project Tracking (`/mrp/tracking`) -> select a project -> "📖 Build Book" button
- Build Tracker Sheet toolbar (`/mrp/tracker/:projectCode`) -> "📖 Build Book" button (cross-link between the two paper views)

**Files:**

| File | Role |
|------|------|
| `frontend/src/utils/buildBook.ts` | Pure data-shaping: work packages, kit chapters, calendar matrix, stock summary. No Supabase calls. Exports `STATION_ABBREV` and `stationAbbrev()`. |
| `frontend/src/utils/buildBook.test.ts` | 11 Vitest unit tests against a fixture project (same shape/fixture pattern as `buildTracker.test.ts`). |
| `frontend/src/views/MrpBuildBookView.vue` | Loads data from Supabase, calls `calculateSchedule()` then `buildBook()`, renders the printable book. |
| `frontend/src/router/index.ts` | Route registration for `/mrp/book/:projectCode`. |
| `frontend/src/views/MrpProjectTrackingView.vue` | "📖 Build Book" button and `openBuildBook()` navigation helper. |
| `frontend/src/views/MrpBuildTrackerView.vue` | "📖 Build Book" button in the toolbar, cross-linking to the book from the tracker sheet. |
| `backend/app/services/build_book.py` | PDF rendering: full bound book (`generate_build_book`) and section print sets (`generate_section_prints`, v3.9.1). |
| `backend/app/routes/mrp.py` | `POST /api/mrp/projects/{project_id}/section-prints` and `POST /api/mrp/projects/{project_id}/build-book` route handlers. |
| `frontend/scripts/emit-book.ts` | Dev script: computes the `BuildBook` payload with the backend service key, for exercising the PDF endpoints outside a browser session (`npx tsx scripts/emit-book.ts [PROJECT_CODE] [OUT_PATH]`). |

**Run the unit tests:**

```bash
cd frontend
npx vitest run
```

As of v3.9.1, `npx vitest run` runs 44 tests total across three files: `scheduling.test.ts` (13), `buildTracker.test.ts` (17), `buildBook.test.ts` (14) -- the buildTracker and buildBook counts grew from 15/11 (v3.9) to cover `isDocumentItem()`, `purchasedDisplay()`/`purchasedSource()`, and `printRefs`.

**WATCH OUT:** as of 2026-07-07 there is one pre-existing failing test in `buildBook.test.ts` (line ~181, a `next` station assertion expecting `'DBR'` but receiving `null` on a fixture part) -- unrelated to the section-prints/document-item/purchased-display work in this release. Confirm this is still failing (and not newly broken) before assuming it's this same known issue.

---

## Data Flow

```
1. User selects a project in MRP Project Tracking (/mrp/tracking)
   and clicks "Build Book" (or clicks it from the Build Tracker toolbar)
         |
2. Router navigates to /mrp/book/{projectCode}
   (MrpBuildBookView.vue mounts)
         |
3. View queries Supabase (same base pattern as MrpBuildTrackerView, plus two
   new queries this feature added):
   mrp_projects, mrp_project_parts (+ items), bom, routing (+ workstations),
   part_completion, workstations,
   routing_materials (+ raw_materials join)   <- NEW for stock pulls
   files (file_type = PDF)                     <- NEW for print availability
         |
4. calculateSchedule() runs (frontend/src/utils/scheduling.ts) to get
   per-task start/end days and station-day loading (stationDays)
         |
5. buildBook() (frontend/src/utils/buildBook.ts) internally calls
   buildTrackerSheet() first (classification, DFS assembly order, milestones,
   per-assembly part groups), then layers on:
     - work packages: part tasks grouped by (start_day, station_id)
     - kit chapters: one per assembly row from the tracker sheet
     - calendar matrix: schedule.stationDays -> hours per day per station
     - stock pull aggregation: routing_materials x project quantity,
       aggregated only at each part's FIRST routed station
         |
6. View renders flowing "sheet" divs (cover, calendar, packages, kits)
   styled for 8.5x11 portrait print with break-inside: avoid on cards
```

---

## Relationship to the Build Tracker Sheet

The Build Book does **not** re-derive classification, assembly ordering, or milestones -- it calls `buildTrackerSheet()` internally (forcing `format: 'tabloid'`, which is irrelevant to the book since pagination fields aren't used) and reads off:

- `sheet.asmRows` -- ordered assembly list (DFS post-order), reused as the kit chapter order
- `sheet.milestones` -- printed as-is on the cover page
- `sheet.fabTotal` / `sheet.asmTotal` / `sheet.purchasedTotal` -- printed as cover-page stat counts
- `sheet.pages[].colA/colB` groups -- re-merged by assembly `rid` (`groupByRef` in `buildBook.ts`) to recover each kit's part list, since the Tracker's groups may be split across print columns/pages

This means any change to classification rules, assembly DFS ordering, or milestone derivation in `buildTracker.ts` (see `31-BUILD-TRACKER-SHEET.md`) automatically flows through to the Build Book -- there is exactly one place those rules live.

**What the Book adds on top of the Tracker's model:**

| Concept | Source |
|---------|--------|
| Work packages (`PKG NN`) | `schedule.tasks` for part items, grouped by `(start_day, station_id)` |
| "Next station" per line | Per-item routed station order derived from `routing`, sorted by `sequence` |
| "For kit" / "Stage kits" refs | BOM parent lookup: which assembly (from `sheet.asmRows`) directly consumes this part |
| Stock pull lists | `routing_materials` joined to `raw_materials`, aggregated at each item's first routed operation only |
| Kit "READY BY" column | The package that produces each kit part -- found via the part's *last* routed task's package |
| Print availability | `files` table, `file_type = 'PDF'`, matched by `item_id`; assembly print (`hasPrint`) and `partPrints`/`parts.length` ratio |
| Day-by-day calendar | `schedule.stationDays[code][day].used_minutes`, converted to hours |

---

## Work Packages (Part I)

A **package** is one card representing all the part tasks the scheduler placed on the same `(start_day, station_id)` pair. Packages are built from `schedule.tasks`, filtered to exclude assembly-level tasks (`asmSet`, i.e. anything that is itself a row in `sheet.asmRows`) -- weld/assembly operations belong to kit chapters (Part II), not work packages.

**Grouping key:** `${start_day}|${station_id}`. Groups are sorted by `start_day` ascending, then by the station's `sort_order` (from `workstations.sort_order`) -- this is what makes `PKG 01`, `PKG 02`, ... a stable dependency-respecting sequence, not an arbitrary one.

**Sequence numbering:** `seq` is a simple incrementing counter over the sorted groups; `id` is `PKG ${String(seq).padStart(2, '0')}` (e.g. `PKG 04`). This ID is what "governs" per the design decision below -- the printed `date` field is informational only.

**Per-package fields:**

| Field | Meaning |
|-------|---------|
| `stationName` / `stationAbbrev` | The station this package runs at (abbreviated via `STATION_ABBREV`, see below) |
| `estMin` | Sum of `duration_min` across all tasks in the package. Note: duration calculation respects `time_basis` (v3.9.8) — per-unit operations multiply by quantity, per-line-item operations use fixed time. |
| `lines[]` | One row per part: item number, name, qty, est minutes, `next` (abbreviated next station or `null` if this is the item's last routed op), `feeds` (assembly rids this part belongs to), `done` |
| `stockPull[]` | Materials to pull for this package -- **only** included if this package is at the item's **first** routed station (`idx === 0` in the item's route order); prevents the same stock line appearing on every downstream package for the same part |
| `stageFor[]` | Assembly rids whose kit this package's output completes -- populated when a line has no `next` station (i.e. this package produces the part's final state) |
| `done` | `true` when every task in the package is already recorded complete (`t.is_complete`) |

**Stock pull aggregation:** `qty` for a stock pull line is `mats.qty * projQty.get(item_id)` summed across every part in the package that draws that material, i.e. the *project* quantity of raw material to physically pull, not a per-part quantity. `parts` counts how many distinct parts draw from that material within the package.

---

## Kit & Weld Sheets (Part II)

One **kit chapter** (`BookKit`) per row in `sheet.asmRows`, i.e. every weldment/assembly in the project, in the same DFS post-order build sequence as the Build Tracker's assembly matrix (sub-assemblies print before their parents).

**Per-kit fields:**

| Field | Meaning |
|-------|---------|
| `startDay` / `endDay` | Min/max `start_day`/`end_day` across all of this assembly's own scheduled tasks (its weld/assembly operations, not its parts' fab operations) |
| `weldSeq[]` | The assembly's own routed tasks, sorted by `sequence`, each with station name/abbrev, est minutes, and `done` |
| `parts[]` | The kit's part list, recovered from the Tracker's merged group for this assembly's `rid`. Each part row carries `readyBy` (the package `id` that produces it, or `null` if the part has no routing) and `readyDay` |
| `childAsms[]` | Direct BOM children of this assembly that are themselves assemblies (i.e. required sub-assemblies to have on hand before this kit can start) |
| `hasPrint` | Whether the assembly's own `item_id` has a PDF row in `files` |
| `partPrints` | Count of this kit's parts that have a PDF in `files`, printed as `n/m` alongside `hasPrint` |
| `printRefs` | (v3.9.1) Ordered list of `{ item_number, revision }` to physically pull for this kit -- the assembly's own drawing (if it has a print) followed by each part's drawing (if it has a print), deduplicated by `item_id` within the kit. Rendered as the **PULL PRINTS** line on the kit sheet. |

**READY BY derivation:** a part's `readyBy` package is found by taking the part's *last* routed station, looking up which package occupies that `(item_id's last station, its start_day)` slot, and reading that package's `id`. If the part has no routing at all, `readyBy` is `null` and the kit sheet prints `—`.

**Weld sequence notes:** each `weldSeq[]` step carries a `notes` field pulled from `routing.notes` for that `(item_id, station_id)` pair (`stepNotes` map in `buildBook.ts`). Assembly-method notes entered in the Routing Editor -- e.g. "clamp doors square before tacking" -- print directly under the step in the kit's SEQUENCE table (`step-note` CSS class) rather than living only in the routing UI.

**Prints note:** the "PRINTS: assembly ✓/— · parts n/m" line is a **phase 1 status indicator only**. The actual PDF pages are not embedded in the web view -- that's explicitly phase 2 (see below), reusing the same download/stamp/merge machinery as `print_packet.py`. The **PULL PRINTS** line (`printRefs`) is a lighter-weight companion shipped in v3.9.1: it doesn't embed the PDFs either, but at least tells the shop which drawing numbers and revisions to physically go pull before starting the kit.

---

## Document Items (Controlled Documents)

**Convention:** an item number whose third letter is `d` (e.g. `csd00010`, `wmd0100`) is a **controlled document**, not a physical part -- design books, build-reference PDFs, work instructions. `isDocumentItem()` in `buildTracker.ts`:

```typescript
export function isDocumentItem(itemNumber: string): boolean {
  return /^[a-z]{2}d\d/i.test(itemNumber)
}
```

**Classification:** `buildTrackerSheet()`'s classifier checks `isDocumentItem()` before the purchased/assembly/made checks and assigns class `'doc'`. Document items are **excluded from all work rows** on both the Tracker and the Book -- they never get a station checkbox, never appear in a work package, and are not counted in `fabTotal`/`asmTotal`/`purchasedTotal`.

**Where they show up instead:** the Build Book's cover page lists every document item in the project under **"REFERENCE PRINTS -- READ FIRST"** (`book.referenceDocs`, built in `buildBook.ts` by filtering `mrp_project_parts` for `isDocumentItem(items.item_number)`), with item number, title, revision, and a PDF-on-file indicator. This is the shop's cue to open/read the reference doc before starting fab work, without it cluttering the package/kit sequence tables.

**Check-in flow** (how a document item gets into a project): there is no dedicated "upload a document" UI as of this writing. The manual process is:
1. Create the item normally in the PDM item browser (item number pattern `??d####`, e.g. `csd00010`).
2. Upload its PDF the same way any drawing is uploaded.
3. Attach it to the project via **MRP Dashboard -> manual part add** -- this inserts an `mrp_project_parts` row with `is_manual = true`.

**Why `is_manual` matters here:** the Dashboard's BOM-reload logic only deletes `mrp_project_parts` rows where `is_manual = false` (rows sourced from the actual BOM upload). A manually-added document item survives every subsequent BOM reload for that project, so it doesn't need to be re-attached every time the BOM is refreshed from Creo/PDM. See `frontend/src/views/MrpDashboardView.vue` for the reload query (`.eq('is_manual', false)` on delete, `.eq('is_manual', true)` on the preserved read, `is_manual: true` on manual insert).

---

## Purchased-Item Display Convention

**Convention:** shop-facing printed documents (Tracker, Build Book) show the **supplier's own part number**, not the internal PDM item number, for purchased items. Internal `mmc*` (McMaster-Carr) and `spn*` (other supplier) item numbers are PDM bookkeeping -- the floor doesn't need to know them.

`purchasedDisplay()` and `purchasedSource()` in `buildTracker.ts`:

```typescript
export function purchasedDisplay(itemNumber: string, supplierPn?: string | null): string {
  const n = itemNumber.toLowerCase()
  if (n.startsWith('mmc') || n.startsWith('spn')) {
    return (supplierPn || itemNumber.slice(3)).toUpperCase()
  }
  return itemNumber
}

export function purchasedSource(itemNumber: string, supplierName?: string | null): string {
  if (supplierName) return supplierName
  const n = itemNumber.toLowerCase()
  if (n.startsWith('mmc')) return 'McMaster-Carr'
  if (n.startsWith('spn')) return 'Supplier'
  return '--'
}
```

- **Display:** `items.supplier_pn` if set, else the item number with its 3-letter prefix stripped, uppercased (e.g. `mmc91290a115` with no `supplier_pn` prints as `91290A115`).
- **Source column:** the Build Tracker's purchased-parts checklist table gained a **SOURCE** column (`items.supplier_name` if set, else "McMaster-Carr" for `mmc*`, "Supplier" for `spn*`, else `--`) so the shop knows where a listed part actually comes from, not just its internal bookkeeping prefix.
- Non-purchased item numbers pass through `purchasedDisplay()` unchanged (fab parts still show their real PDM item number).
- Consumed at `buildTracker.ts` line ~563 (`displayNumber` / `source` fields on the purchased-parts row builder) and rendered in the Tracker's purchased table header (`SOURCE` column, `MrpBuildTrackerView.vue`).

---

## Station Abbreviations

`buildBook.ts` exports a `STATION_ABBREV` map that **mirrors the backend's `print_packet.py` `STATION_ABBREV`** -- keep these two in sync if either changes:

```typescript
export const STATION_ABBREV: Record<string, string> = {
  'Receiving': 'RCV', 'Saw': 'SAW', 'Deburr': 'DBR', 'Waterjet': 'WJ',
  'Press Brake': 'PB', 'Weld Jigging': 'JIG', 'Light Weld': 'LW',
  'Heavy Weld': 'HW', 'Weld Cleanup': 'WCU', 'Pipe Bending': 'PIP',
  'Hole Punch - Iron Worker': 'HP', 'Part Staging': 'STG',
  'Mechanical Assembly': 'ASM', 'Plumbing': 'PLM', 'Wiring': 'WIR',
  'Inspection': 'INS', 'Galvanizing': 'GAL', 'Paint and Paint Prep': 'PNT',
}
```

`stationAbbrev(name)` falls back to the first three uppercased characters of the station name for anything not in the map, so a new workstation added without updating this list still prints *something* reasonable rather than erroring.

Press Brake prints as `PB` everywhere: the Build Book's `STATION_ABBREV`, the backend print packet, and (aligned 2026-07-06) the Build Tracker's `PART_COLUMNS` column label. The Tracker's internal column *key* remains `BRK` in code; only the printed label changed.

---

## Cover / Plan Page

The first printed sheet is a project-level summary, not tied to any single package or kit:

- **Stats row:** est hours (`summary.totalHours`, from summing `schedule.tasks` duration), work days (`schedule.total_days`), package count, fab part count, weldment/assembly count, purchased count (the latter three sourced from `sheet.fabTotal`/`asmTotal`/`purchasedTotal`)
- **Milestones table:** `sheet.milestones` verbatim (op 10-70, same derivation as the Tracker -- see `31-BUILD-TRACKER-SHEET.md`)
- **Hours by area:** `summary.byGroup`, station-group hours (`workstations.station_group`) summed across `schedule.tasks`, sorted descending
- **Stock pull summary:** project-wide aggregate (not per-package) of `routing_materials`, i.e. the same aggregation logic as a package's `stockPull` but run once across every part's first-op materials for the whole project

---

## Day-by-Day Calendar

Built directly from `schedule.stationDays`, the same grid the scheduler uses internally for capacity constraints -- the calendar is not a separate estimate, it is a direct visualization of the schedule's own working state.

- **Rows:** one per working day that has *any* non-zero station usage (days with zero usage across every station are skipped)
- **Columns:** every station code that appears anywhere in `schedule.stationDays`, sorted by `workstations.sort_order`
- **Cells:** `used_minutes / 60` (hours), plus the list of package IDs (`p.id`) whose `day` and `stationName` match that cell, so the calendar doubles as an index back into Part I

---

## Sequence-First, Dates-Advisory (Design Decision)

**This was an explicit user-confirmed decision (2026-07-06), not a default:** package numbers (`PKG NN`) govern the order the shop should work in; the printed planned day/date on each package is advisory guidance, not a hard constraint. The book's cover page states this directly: *"WORK THE PACKAGES IN ORDER — PKG numbers govern, printed days are the plan."*

**Why:** the schedule is a live, capacity-constrained projection that will drift the moment real shop conditions deviate from the plan (a machine down, a late purchased part, a rework). A book that hard-pins the shop to calendar dates becomes wrong and confusing almost immediately. A book whose dependency-respecting sequence stays valid regardless of *when* each package actually gets worked remains useful for the life of the project. Package grouping by `(start_day, station_id)` still respects true dependency order (a part can't appear in an earlier package than the parts/materials it needs), so following `PKG 01, PKG 02, PKG 03...` in order is always safe even if the printed days no longer match reality.

**Practical effect:** if you regenerate the book after a schedule shift, package numbering can change (a package that was `PKG 07` might become `PKG 05` after conditions change), but the *relative* dependency order among any two packages does not change without an actual BOM/routing/schedule structural change. Always work from the most recently printed/generated book, and don't try to "reconcile" old PKG numbers against a new printout.

---

## Recorded-Complete Rendering

Uses the exact same completion source as the Build Tracker and `MrpShopView` -- `part_completion` rows, `qty_complete` vs. project quantity, no separate "book completion" concept:

- A package **line** shows a filled checkbox (`cb pfd` CSS class) when `ScheduledTask.is_complete` is true (the scheduler itself marks tasks complete based on `part_completion` coverage, same logic consumed by the Tracker)
- A package **card** gets a `is-done` styling (grayed header) and a "✔ RECORDED COMPLETE" badge when *every* line in the package is complete
- Kit weld-sequence steps and kit part rows use the same filled-checkbox convention independently

This means printing the book mid-project (after some shop-floor progress has been recorded) produces a book where already-finished work is visually distinct, same intent as the Tracker's pre-fill toggle -- except the Book has no pre-fill *toggle*; recorded completion always renders, since the book is meant to be regenerated and reprinted as work progresses rather than marked up by hand like the Tracker.

---

## Print Layout

- **Format:** letter portrait only (8.5in x 11in, 0.5in margins) -- unlike the Tracker, there is no format toggle
- **`@page` rule:** `size: 8.5in 11in; margin: 0.5in;` injected via a scoped `<style>` `@media print` block
- **Flow:** each top-level section (cover, calendar, work packages, kit chapters) is a `.sheet` div with `page-break-after: always`, so each section starts on a fresh page; individual `.card` elements (packages, kits) use `break-inside: avoid` / `page-break-inside: avoid` so a card is never split across a page boundary
- **Screen preview:** dark MRP chrome toolbar (`#020617` background) frames a light "paper" column (`max-width: 856px`) so the book previews similarly to how it will print, without a fit-to-width scale factor (unlike the Tracker, which computes one for its wider tabloid layout)

---

## Section Print Sets (v3.9.1)

**The headline feature of this release.** Instead of one giant bound PDF of every print in the project, the shop can pull a small, task-sized print set for exactly the section they're about to work: the reference docs, a single work package, or a single kit.

### UI

The Build Book toolbar (`MrpBuildBookView.vue`) has a **print-set dropdown** and a **"⬇ Download prints"** button, next to the existing "Print (8.5x11 portrait)" button:

```html
<select v-model="selectedSection" class="section-select" :disabled="!book">
  <option value="">— Print set —</option>
  <optgroup v-for="g in sectionGroups" :key="g" :label="g">
    <option v-for="s in sections.filter(s => s.group === g)" :key="s.key" :value="s.key">
      {{ s.label }}
    </option>
  </optgroup>
</select>
<button :disabled="generatingPdf || !selectedSection" @click="downloadSectionPrints">
  {{ generatingPdf ? 'Gathering…' : '⬇ Download prints' }}
</button>
```

The dropdown is grouped into three `optgroup`s, built by the `sections` computed property from the already-loaded `book`:

| Optgroup | Source | One entry per |
|---|---|---|
| **Reference** | `book.referenceDocs` | The whole project (single "Design Reference Prints" entry, only shown if the project has any document items) |
| **Work packages** | `book.packages` | Each `PKG NN` (label: `PKG NN — Station Name`) |
| **Kits** | `book.kits` | Each assembly/weldment (label: `A## — Assembly Name`) |

Each entry carries `items: { item_number, qty }[]` -- for a work package, the package's line items with their package quantities; for a kit, the assembly itself plus every kit part with their kit quantities; for the reference set, every document item with `qty: null` (quantity is meaningless for a reference doc).

### Request / Response

**Endpoint:** `POST /api/mrp/projects/{project_id}/section-prints`

**Request body:**
```json
{
  "label": "PKG 03 — Waterjet",
  "items": [
    { "item_number": "csp00210", "qty": 4 },
    { "item_number": "csp00215", "qty": 2 }
  ]
}
```

**Response:** the PDF bytes directly (`Content-Type: application/pdf`, `Content-Disposition: attachment; filename="{project_code}_{sanitized_label}.pdf"`), plus response headers `X-Pages`, `X-Prints-Bound`, `X-Missing` that the frontend reads to show a "`N` prints · `M` missing" status message next to the button.

### Backend: `generate_section_prints()`

`backend/app/services/build_book.py`, called from the route handler in `backend/app/routes/mrp.py` (`POST /projects/{project_id}/section-prints`):

1. **Dedupe by item number**, summing quantities across duplicate entries (e.g. the same hardware item appearing on two lines in a kit), preserving first-seen order.
2. **Resolve PDF paths** for every item number via `_fetch_pdf_paths()` (items -> newest PDF `files` row, same helper the full book uses).
3. **Parallel download** of every resolvable PDF (`ThreadPoolExecutor(max_workers=8)`) -- this is what keeps generation fast; sequential downloads of 20-30 PDFs would take much longer.
4. **Cover page**: item list table (`PART #` / `QTY` / `PRINT`) with `MISSING` printed in the PRINT column for any item with no resolvable PDF on file, so the shop immediately sees what they'll need to chase down instead of just getting a short packet with no explanation.
5. **Per-print QTY stamp**: `_stamp_qty()` overlays a white-backed box in the top-right margin of each print's **first page only** -- `QTY N` in large bold text plus the section label in small text underneath. Uses `page.merge_page()` (pypdf) with a one-page reportlab overlay sized to that page's own `mediabox`, so it works regardless of the source drawing's page size. Reference-doc entries (`qty: null`) are not stamped -- there's no meaningful per-doc quantity.
6. **Merge**: cover page + every resolved print, in request order, via `pypdf.PdfWriter`.
7. **Return the raw bytes directly** -- no storage upload, no signed URL round-trip. The route wraps it in a plain FastAPI `Response` (see the StreamingResponse gotcha below).

### Verified Output Sizes (2026-07-07 testing)

| Set | Pages | Prints | Size | Gen time |
|---|---|---|---|---|
| PKG 03 (Waterjet) | 27 | 26 | 6.9 MB | ~11s |
| Design Reference (csd00010 project) | 4 | -- | 10.9 MB | -- |

### Relationship to the Full Book PDF (`POST /build-book`)

The full-book PDF endpoint (`POST /api/mrp/projects/{project_id}/build-book`, `generate_build_book()`) **still exists and still works** -- it renders the entire cover/calendar/packages/kits text plus every reference doc and kit print bound into one document (107 pages / 62 prints / 54 MB on the same test project). **It no longer has a UI entry point.** Two reasons this release moved away from it as the primary workflow:

1. **Storage limit:** Supabase's per-project storage upload cap is roughly 50 MB; a 54 MB full book exceeds it, so `generate_build_book()`'s own "best-effort" storage step (see `max_store = 45 * 1024 * 1024` in `build_book.py`) silently skips storing a book of that size -- it still streams back to the browser that generated it, but there is no saved copy to re-download later.
2. **Shop preference:** a 100+ page bound book is unwieldy to carry to a machine for one operation. The section print sets give the shop exactly what they need for the task in front of them, at a fraction of the size and generation time.

The full-book endpoint is not deprecated -- it's still reachable directly via `curl`/API client and may get a UI entry point again later (e.g. an end-of-project archival copy) -- but section print sets are the day-to-day workflow as of v3.9.1.

### Engineering Notes

- **Never use `StreamingResponse` over a `BytesIO` for a binary PDF response.** Starlette's `StreamingResponse` iterates the file-like object line-by-line (`readline()`-style), which for binary data means splitting on stray `\n` byte values -- observed throughput was on the order of 80 KB/s, turning a multi-MB PDF into a multi-minute download. Both `/section-prints` and `/build-book` return a plain `fastapi.Response(content=pdf_bytes, media_type="application/pdf")` instead, since the PDF is already fully assembled in memory. See the inline comment at `backend/app/routes/mrp.py` line ~603.
- **reportlab's built-in Helvetica/WinAnsi encoding cannot render non-ASCII glyphs** like `✓` or `▸` -- text drawn via `canvas.drawString()` with these characters either throws or silently drops the character depending on reportlab version. All backend-generated PDF text (cover pages, stamps, section headers) must stick to plain ASCII; use words ("YES"/"MISSING"/"DONE") instead of glyphs where the web UI would use a checkmark or arrow icon. This does not affect the Vue web view, which renders in the browser and has full Unicode/emoji support (e.g. the `📖` book emoji on toolbar buttons, `✔` on the web Book view).
- `frontend/scripts/emit-book.ts` is a dev script that computes the same `BuildBook` payload the browser would (using the backend's service-role key from `backend/.env`) and writes it to a JSON file -- useful for hitting `/build-book` or eyeballing the payload shape without opening a browser session: `npx tsx scripts/emit-book.ts [PROJECT_CODE] [OUT_PATH]`.

---

## Design Decisions (User-Confirmed, 2026-07-06)

These choices were explicitly confirmed with the user before implementation:

1. **Structure = plan + packages + kits, all three sections, not a subset.** The cover/plan page, day-by-day packages, and kit/weld chapters were all requested together as the phase-1 scope, not staged in.
2. **Sequence-first, dates-advisory.** See the dedicated section above -- PKG numbers are the operative ordering; planned days are guidance.
3. **Prints embedded via phase-2 backend PDF, not phase-1 web view.** The web view only shows print *availability* (checkmark + n/m ratio); actually merging PDF pages into the book is deferred to the backend PDF edition.
4. **Delivery: web view first, PDF endpoint next.** Matches the Tracker's phased pattern -- ship the live, regenerate-on-load web page as phase 1, then add a backend-rendered downloadable/archivable PDF as phase 2.

---

## Phase 2 (Built, v3.9.1 -- Superseded as the Primary Workflow by Section Print Sets)

The originally-planned phase 2 backend PDF endpoint was built: `POST /api/mrp/projects/{project_id}/build-book` (`generate_build_book()` in `backend/app/services/build_book.py`) takes the same `BuildBook` JSON structure the web view renders and produces a full bound PDF --

- **reportlab** for the generated pages (cover, calendar, package cards, kit cards) -- mirrors the structure already proven in the web view
- **pypdf** merges in per-kit part prints, reusing the download/stamp/merge machinery originally built for `print_packet.py` (see `04-SERVICES-REFERENCE.md` / print packet generation)
- Each kit chapter gets its assembly print plus every part's current PDF embedded directly after that kit's text pages (first-use dedup -- a part shared across kits only gets its print bound once, at the first kit that uses it), plus reference docs bound behind the cover
- Verified output: 107 pages / 62 prints / 54 MB on a representative project
- Storage: best-effort upload to the `print-packets` bucket at `{project_code}/{project_code}_build_book.pdf`, skipped automatically above ~45 MB (Supabase's project-wide storage upload cap is roughly 50 MB) -- the PDF still streams back to the browser regardless of whether the storage copy succeeds

**Status as of v3.9.1: exists and works, but has no UI entry point.** The 54 MB result exceeds the practical storage limit and is unwieldy for a shop worker to carry around for one operation. **Section Print Sets** (see the dedicated section above) shipped in the same release as the practical day-to-day replacement -- same underlying download/stamp/merge machinery, scoped to one section instead of the whole project. See that section for the full rationale.

`hasPrint`/`partPrints`/`printRefs` on `BookKit` remain the signal both the full-book renderer and the section-prints endpoint use to know which prints are available without re-querying.

---

## Known Issues / Notes

- Uses `format: 'tabloid'` internally when calling `buildTrackerSheet()` purely to satisfy that function's required parameter -- the Book does not use any tabloid-specific pagination fields from the returned sheet, so this has no visible effect on the Book's own (letter-only) layout.
- Inherits every classification/ordering caveat documented for the Build Tracker (`31-BUILD-TRACKER-SHEET.md`): `mrp_project_parts` flat-quantity vs. BOM-tree rollup disagreement, part-level weld ops not surfacing outside the assembly context, Plumbing/Wiring folding into a single station bucket at the assembly level.
- `routing_materials` and `files` queries are new additions specific to the Book -- the Tracker does not query either table. If a part has no `routing_materials` rows, its packages simply print with no `stockPull` section (not an error state).
- No format toggle and no pre-fill toggle -- both are deliberate simplifications versus the Tracker for phase 1.
- **(v3.9.1)** The full-book PDF endpoint (`POST /build-book`) has no UI entry point -- see the Section Print Sets and Phase 2 sections above. It is not deleted or deprecated in code, just not wired to a button.
- **(v3.9.1)** Backend-generated PDF text (cover pages, stamps) is ASCII-only -- reportlab's default Helvetica/WinAnsi encoding cannot render `✓`/`▸`-style glyphs used elsewhere in the web UI. Use words, not icons, in any new backend PDF text.
- **(v3.9.1)** Never wrap a fully-in-memory PDF `bytes` object in `StreamingResponse` -- it iterates line-by-line and is orders of magnitude slower than a plain `Response`. See the Engineering Notes under Section Print Sets.

---

## Known Data Notes (Spa Project Routing)

Not code, but worth recording since it shaped what the Book's kit sequences render for at least one live project (2026-07-07):

- `csa00080` gained a **Plumbing** routing step.
- `csa00010` routing sequence became **Weld Cleanup -> Mechanical Assembly (doors) -> Vinyl Wrap -> Inspection**. Vinyl Wrap is a new workstation, station code `047`.
- Assembly-method notes entered on individual routing steps (`routing.notes`) now render inline under the corresponding step in each kit's **SEQUENCE** table on the Build Book (see `weldSeq[].notes` in the Kit & Weld Sheets section above) -- e.g. door-hanging or wrap-application instructions show up right where the shop needs them instead of only living in the Routing Editor.
- The Build Tracker's printed Press Brake column label changed from `BRK` to `PB`, matching the Build Book's `STATION_ABBREV` and the backend print packet's abbreviation, for cross-document consistency. The Tracker's internal column *key* is still `BRK` in code -- only the printed label changed (documented previously, see the Station Abbreviations section above).

---

## Cross-References

- **Build Tracker Sheet:** `31-BUILD-TRACKER-SHEET.md` -- classification, DFS assembly ordering, milestone derivation, and completion semantics, all reused directly by the Book via `buildTrackerSheet()`.
- **Scheduling engine:** `20-COMMON-WORKFLOWS.md` section 15 (Project Scheduling and Capacity Planning) -- `calculateSchedule()` from `frontend/src/utils/scheduling.ts` is the Book's primary data source for packages, kit timing, and the calendar.
- **Section print sets workflow:** `20-COMMON-WORKFLOWS.md` section 17 (Printing a Manufacturing Build Book).
- **Completion data model:** `part_completion` table -- see `03-DATABASE-SCHEMA.md`.
- **Manual project parts (`is_manual`):** `mrp_project_parts` table -- see `03-DATABASE-SCHEMA.md`; consumed by the Document Items check-in flow above.
- **Print packet machinery:** existing `print_packet.py` download/stamp/merge pattern -- see `04-SERVICES-REFERENCE.md`. Both `generate_build_book()` and `generate_section_prints()` follow the same fetch/stamp/merge shape.
- **BOM rollup caveats:** `06-BOM-COST-ROLLUP-GUIDE.md`.
