# 38 — Kit Sourcing & Reference Items in the Build Documents

**Status:** PLANNED (decisions locked with Jack 2026-07-10)
**Affects:** Master Design Book (36), Build Book (32), Build Tracker (31)
**Depends on:** 37-KIT-BUNDLE-PRICING.md (`project_kits`, `project_item_source`)

---

## 1. Problem

v3.9.3 added **vendor kit sourcing**: a part can be bought as part of a finished-part
bundle (`project_item_source.source_type='kit'`) instead of made in-house. The shop
receives it, inspects it, and routes it to its area — no saw, no waterjet.

The kit-pricing work touched costing, routing UI, and the dashboard. It did **not**
touch `buildBook.ts`, `masterDesignBook.ts`, or `scheduling.ts`. So today the
published Master Design Book (rev 1) still instructs the shop to saw 18 tubes that
are in fact bought pre-cut in **KIT-001 "Tube Laser Bundle"** (Precision Tube Laser).

Separately, `zzz`-prefixed reference items must stay out of the build documents.

## 2. Ground truth (verified against the live DB, 2026-07-10)

| Fact | Value | Consequence |
|---|---|---|
| Kits on SPA0030 | `KIT-001` Tube Laser Bundle, 18 parts, `use_kit=true` | The template's sourcing |
| Kit parts' current routing | `Saw → (Waterjet) → Deburr → Inspection` | All 18 are saw-primary |
| `routing` table has a `project_id`? | **No** — routing is global per item | Cannot make routing project-specific by editing rows |
| Kit parts also used by | `SPA001`, `TEST-PROG01` (all 18) | Editing routing would silently rewrite those projects |
| Kit parts with `routing_materials` | **18 of 18** | Would wrongly print "PULL STOCK: 2x6 tube" on a *receiving* booklet |
| Kit parts with children (sub-assemblies) | **0** | All leaf parts; assembly-level kits are out of scope for now |
| In-project assemblies consuming kit parts | `csa00030`, `csa00060`, `csa00070`, `csa00100`, `csa00110`, `csa00150` | 6 Section II booklets must keep listing them |
| `zzz` in published book rev 1 | **0 sections** | Already excluded — incidentally, not by design |
| Items matching `zz*` but not `zzz*` | 3 (`zz_hingebody`, `zzc551436`, `zzc561020`) | Narrowing the ref test to `zzz` would reclassify them |

### 2.1 The two landmines

**Landmine A — kit parts would vanish from Section II.**
`buildTracker.classify()` maps *"has Receiving and no Fab/Weld"* → `'purchased'`
(buildTracker.ts:396), and assembly part groups only accept `'made'` parts
(buildTracker.ts:483). So naively giving kit parts a receive-only routing **deletes
them from the stage-set tables** — the welder building the Lower Frame loses the list
of tubes that go into it. Verified: `csp00010` currently appears in exactly two
sections, `I-SAW-1` and `II-CSA00030`. It must keep the second.

**Landmine B — `excludeFromManufacturing()` must never be used by the build docs.**
The helper added in the kit-pricing commit excludes `mmc`/`spn` as well as `zzz`.
The design book **needs** purchased items: they are the spine BUY LIST and the
`I-RCV` receiving packages. Wiring that helper into the book would silently delete
the purchasing story. It is currently dead code; keep it dashboard-only.

## 3. Decisions (Jack, 2026-07-10)

1. **The master book follows the template project's sourcing.** It documents how we
   build one *today*. Sourcing changes rev the book and issue a change notice.
2. **Kit-supplied parts route `Receiving → Inspection → Part Staging`.** Inspection is
   a secondary station (folds into Receiving), so each part appears in an `I-RCV-*`
   booklet and an `I-STG-*` staging booklet — literally "received, inspected, and
   routed to their respective areas."
3. **`use_kit` is ignored by the build documents.** It is a *pricing* toggle (cost
   sensitivity, vendor out-of-stock). The book follows `source_type='kit'` only, so a
   cost experiment can never rev a controlled document. A genuine sourcing change
   means reassigning parts to `make`.
4. **Section II is renamed "STAGE SET".** Vendor kits keep the word KIT everywhere
   (`KIT-001`), matching the new UI. Section II booklets become
   `STAGE SET — PARTS REQUIRED`; Section I's `FOR KIT` column becomes `FOR SET` and
   `STAGE KITS:` becomes `STAGE SETS:`.

### 3.1 Open recommendation (proceeding unless overridden)

`classify()` has always treated the whole **`zz*` family** as reference. The new
`isReferenceOnlyItem()` helper tests `zzz` only. Narrowing `classify()` to match would
turn `zzc551436` / `zzc561020` (no routing, reference-only, live in another project's
BOM) into makeable parts. **Recommendation:** broaden the shared helper to `^zz` and
have both `classify()` and the dashboard call it. One definition, no behavior change,
and the dashboard correctly stops counting `zzc*` reference items.

## 4. Design

### 4.1 New input (optional, backward compatible)

```ts
export interface KitSourceInput {
  item_id: string
  kit_number: string      // 'KIT-001'
  kit_name: string        // 'Tube Laser Bundle'
  vendor: string | null   // 'Precision Tube Laser'
}
// TrackerInputs / BookInputs / MasterBookInputs gain:  kitSources?: KitSourceInput[]
```

Fetched from `project_item_source` (where `source_type='kit'`) joined to
`project_kits`, scoped to the project. **`use_kit` is not read.** Omitting the input
reproduces today's behavior exactly, so `MrpBuildTrackerView` and the per-project
Build Book are unaffected until they pass it.

### 4.2 Routing synthesis (before `calculateSchedule`)

For every kit-sourced item, **discard its routing rows and its `routing_materials`**,
then synthesize (times are **per unit**, `KIT_SUPPLIED_ROUTING` in buildTracker.ts):

| seq | station | est_time_min |
|---|---|---|
| 10 | Receiving (005) | 1 |
| 20 | Inspection (050) | 2 |
| 30 | Part Staging (020) | 1 |

⚠ **Do not use the 5-min house norm here.** That norm is the cost of an *individually
purchased* item (unpack, count and log one McMaster box); a bundle arrives as a single
shipment of many pre-cut parts. Measured on SPA0030: the 18 bundled tubes cost **193
min** of in-house work (saw averages **2.89 min/unit**, not 20). At 5/5/5 the
synthesized routing charged **435 min** — buying finished parts *added* 4 hours of
labor and lengthened the schedule by a day. At 1/2/1 it charges 116 min and the book
shortens, as it must. These are per-unit constants and easy to tune.

Suppressing `routing_materials` is what stops the receiving booklet from telling the
shop to pull raw tube stock for parts the vendor already cut.

Because this is derived from the **per-project** `project_item_source`, the global
`routing` table is never touched — SPA001 and TEST-PROG01 keep sawing these parts.

### 4.3 New item class `kit_supplied`

`classify()` gains a class that is **purchased-like for work, made-like for membership**:

| Behavior | `made` | `kit_supplied` | `purchased` |
|---|---|---|---|
| Appears in Section II stage-set tables | yes | **yes** | no |
| Appears in spine BUY LIST | no | **no** (the bundle is one line) | yes |
| Work packages from routing | yes | yes (RCV/STG) | yes (RCV) |
| Pulls raw stock | yes | **no** | no |
| Binds its print | yes | **yes** (needed for incoming inspection) | no |

Classification order: `zz*` → ref, `[a-z]{2}d\d` → doc, **kit-sourced → kit_supplied**,
`mmc`/`spn` → purchased, assembly, receiving-only → purchased, else made.
A kit-sourced item *with children* is out of scope — log a warning and treat as
assembly (buying a pre-welded weldment would retire its Section II booklet; revisit
if that ever happens).

### 4.4 Rendering changes

- **Section I receiving booklet** gains a bundle band:
  `BUNDLE KIT-001 TUBE LASER BUNDLE — PRECISION TUBE LASER — VERIFY 18 PARTS AGAINST PRINTS ON RECEIPT`
- **Kit-supplied line rows** reuse the existing purchased `source` mechanism, so the
  description reads `2X2 TUBE -- KIT-001`. No new column, no width surgery.
- **Spine BUY LIST** gains a `BUNDLES` block above the loose purchased parts:
  kit number, name, vendor, part count. **No prices** — the design book is a build
  document, not a quote.
- **Spine checklist** RCV row reads `Work package - receive & inspect 18 bundle parts`.
- **Section II rename** per decision 4.
- `renderer_version` → **2** (printed labels changed; per 36 §3.4 this is mandatory).

### 4.5 Change-notice reason derivation

Today a `renderer_version` bump suppresses all other reason clauses
(`master_design_book.py::derive_reasons`). That would hide the *why* — the shop would
see "LAYOUT UPDATE" and never learn the tubes are now bought. **Change:** on a
renderer bump, prepend `LAYOUT UPDATE (renderer vN->vM)` but still list up to two data
reasons. The floor gets both facts.

### 4.6 pkg_position no longer hashed (found during Phase B)

Kit sourcing removes saw packages, which resequences every downstream work package's
global build-order ordinal (`PKG 07` → `PKG 05`). That ordinal was in the section
hash (Documentation/36 §2.3 claimed "PKG 04 is printed on the card") — but the master
book prints the stable section code (`I-SAW-1`), never the PKG number. So hashing it
**phantom-revs byte-identical booklets** on any resequence: verified that `I-PB-1` and
8 other packages differ from rev 1 in `display.pkg_position` **only** — same day, same
lines, same prints.

Fix: `masterDesignBook.ts` drops `pkg_position` from the descriptor `display` (keeps
`day`, which IS printed and must rev on a move); the backend `derive_reasons` drops the
`RESEQUENCED PKG` clause. Build order lives in the spine checklist, which revs anyway.

**One-time transition cost:** rev-1 stored these sections *with* pkg_position, so on the
rev 1 → 2 publish all 9 rev once (as `REVISED`). They shift position under kit sourcing
regardless, so this does not increase the rev-2 count — and every *future* update is now
clean (a resequence no longer reprints identical booklets). ⚠ JACK decides at publish
(Phase E) whether the one-time transition is acceptable.

## 5. Measured impact on SPA0030 (engine run, 2026-07-10)

**Rev 1 → 2 dry-run (`/check`): 22 changed, 1 added (`I-STG-3`), 2 retired
(`I-SAW-2`, `I-WJ-3`), 10 unchanged.** Of the 22 changed:
- **13 real:** `I-RCV-1`/`I-STG-2` (gained bundle parts), `I-SAW-1`/`I-WJ-2` (lost
  them), 6 assemblies whose tube rows flip to `KIT-001` / ready-by-staging,
  `II-CSA00150`/`160` (plan-day shift), `00-SPINE` (checklist + bundles block).
- **9 position-only:** byte-identical booklets, the pkg_position transition above.


| | in-house | KIT-001 sourced |
|---|---|---|
| Saw package lines | 26 | **8** |
| Total hours | 192.3 | **191.0** |
| Working days | 18 | 18 |
| Fabricated part rows | 58 | **36** |
| Kit-supplied part rows | 0 | **22** |

- `I-SAW-*` collapses from 26 lines to 8 — the visible change on the floor.
- `I-RCV-*` and `I-STG-*` absorb the 18 parts (22 rows: a part used by two assemblies
  appears in both stage sets).
- Six Section II booklets keep their tube rows, but `READY BY` flips from `I-SAW-1` to
  the **staging** package and the description gains `-- KIT-001`. (`READY BY` is the
  *last primary* op that finishes a part, and a bundled part is ready for the welder
  once it is staged — not when it is received.)
- **Total hours barely move (−1.3 h) and the schedule stays 18 days.** These tubes were
  cheap to saw (2.89 min/unit); the bundle's value is dollars and saw-station relief,
  not labor hours. Welding remains the bottleneck. An earlier draft of this plan
  predicted a large schedule contraction — that was wrong, and the D-day churn in the
  change notice will be correspondingly smaller.
- Section identity holds: Section II codes are `item_number`-keyed (stable REPLACE);
  Section I codes are `{station_code, occurrence}`-keyed, so a collapsed saw package
  retires cleanly and new `I-RCV`/`I-STG` occurrences insert.

## 6. Implementation phases

**Phase A — engine (shared, backward compatible)**
1. `buildTracker.ts`: broaden the reference helper to `^zz`; have `classify()` use it;
   add `kit_supplied` class + `kitSources` input; include `kit_supplied` in assembly
   part groups; exclude it from the purchased buy list.
2. New `applyKitSourcing(routing, routingMaterials, kitSources)` helper: synthesize
   RCV→INS→STG, drop raw-material rows. Applied before `calculateSchedule`.
3. `buildBook.ts`: `bundles[]` on the output; `sourcedFrom` on kit part rows; summary
   counts (`fabParts` down, new `kitSupplied`).
4. Vitest: kit part stays in Section II; leaves Saw; no stock pull; buy list excludes
   it; bundle surfaces; `zzc*` still reference; determinism holds.

**Phase B — master book**
5. `masterDesignBook.ts`: accept + canonically sort `kitSources`; skip `zz*` in the
   BOM-rollup qty gate; emit bundle info on the spine descriptor and the RCV package.
6. `designBook.ts`: fetch `project_item_source` + `project_kits` in `buildMasterModel`.

**Phase C — renderer**
7. `master_design_book.py`: STAGE SET rename, bundle band, BUNDLES block on the buy
   list, `renderer_version = 2`, `derive_reasons` keeps data reasons on a renderer bump.
8. `verify_quantities`: skip `zz*`.
9. Pytest: renderer strings, bundle band, reason derivation with renderer bump.

**Phase D — per-project docs (keeps the two books from disagreeing)**
10. Wire `kitSources` into `MrpBuildBookView` and `MrpBuildTrackerView`. Without this,
    the project build book would tell the shop to saw parts the master book says to
    receive.

**Phase E — publish**
11. Dry-run `/check` on `spa-standard`, review the diff, publish rev 2, verify the
    change notice names both the sourcing change and the layout update.

## 7. Risks

| Risk | Mitigation |
|---|---|
| Kit parts silently dropped from Section II | `kit_supplied` class + explicit vitest |
| Receiving booklet tells shop to pull raw stock | Suppress `routing_materials`; test |
| Global routing edits leak into SPA001 / TEST-PROG01 | Never touch `routing`; synthesize per-project |
| `use_kit` pricing experiment revs a controlled doc | Book reads `source_type` only |
| Renderer bump hides the sourcing reason from the floor | Keep data reasons on renderer bump |
| Narrowing ref test to `zzz` reclassifies `zzc*` | Broaden shared helper to `^zz` |
| Two books disagree (project vs master) | Phase D wires both |
