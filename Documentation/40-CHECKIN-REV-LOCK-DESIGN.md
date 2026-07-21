# 40 - Check-In/Check-Out & Revision Locking Design

**Status:** Research complete, design proposal (2026-07-19)
**Goal:** Lock released parts (STEP, DXF, DRW, Creo files) so they can't be silently modified after being sent to suppliers; add real check-in/check-out; keep local Creo synced with PDM; show the PDM revision inside Creo as a parameter.

---

## 1. Current State (what exists today)

Research audit of the live system found:

| Area | State |
|---|---|
| `checkouts` table | Exists in schema + Pydantic model (`schemas.py:245`), but **no backend endpoints use it**. The only code touching it is `frontend/src/components/FileCheckIn.vue`, which is **orphaned** (imported nowhere). |
| Revision/iteration | `items.revision` (default 'A'), `items.iteration` — plain editable columns. **No revise/release endpoints, no auto-increment, no state-transition enforcement.** |
| Lifecycle states | DB CHECK constraint: `Design, Review, Released, Obsolete`. **Nothing anywhere guards writes on Released items** — `PATCH /api/items/{n}` and `POST /api/files/upload` proceed regardless of state. |
| `lifecycle_history` | Table exists, History tab reads it, but **nothing in the live path ever writes to it**. |
| File versioning | Uploads **overwrite in place**: same DB row (keyed on item + normalized filename), same storage path `pdm-files/{item}/{filename}`. Only `iteration` ticks up. **No prior versions retained.** |
| Provenance | `files.uploaded_by` exists but is **never populated** (upload endpoint omits it; upload scripts send no identity). |
| Workspace compare | `frontend/public/creojs/workspace.html` + `POST /api/workspace/compare` — matches by filename→item_number, compares **local mtime vs `files.updated_at` ±120s**. No checksum, no revision comparison. |
| Local service | `PDM-Local-Service.ps1` on port 8083 handles Check-In (POST to `/api/files/upload`) and Download. API base hardcoded to `https://pdm-web.fly.dev/api`. Wildcard CORS. |
| Auth | Backend is effectively open (service-role client, no auth dependency except `/auth/me`). Creo browser and PowerShell scripts send no token. Relies on Tailnet isolation. |
| JLink | **No JLink code exists** in the repo or Legacy/ — the legacy comparison was pure PowerShell + CreoJS file listing. Any Toolkit-level work is new. |

Net: clean slate. Nothing to unwind except deciding the fate of the orphaned `FileCheckIn.vue`.

---

## 2. How Commercial Systems Do It (research summary)

### Windchill PDMLink (the reference model)

- **Lock = database row on the object master**, not a file lock. Check-out transfers a working copy and locks the object; only the holder can modify. Check-in publishes a **new iteration** (A.1 → A.2) and releases the lock. Revision (A → B) only via deliberate **Revise**.
- **Released is enforced via state-scoped permissions**: the Check Out action is literally driven by Modify permission, and admins deny Modify at Released. The only path forward is Revise → new revision at In Work. **One rule (`can_checkout = state allows modify`) gives both rev-locking and the revise workflow.**
- Models opened without check-out are **"read-only in session"** (app-layer flag, not a Windows attribute). Attempting to modify pops "Check Out on the Fly": *Check Out / Continue / Read Only*. Even Windchill cannot prevent in-memory edits — it prevents **persistence** (save/check-in of a non-checked-out model is refused).
- Check-in rejects stale baselines (your local copy must be based on the latest iteration).

### Windchill → Creo parameter sync (the pattern we want)

- `PTC_WM_REVISION`, `PTC_WM_ITERATION`, `PTC_WM_LIFECYCLE`, etc. are **real parameters written into the Creo file** by the Workgroup Manager during upload/check-in — not session-injected magic.
- Drawings reference them as `&PTC_WM_REVISION` in formats/tables.
- Known caveats we inherit by copying this: (1) parameters don't exist until first stamp — **pre-seed them in start parts/templates** so formats never show broken references; (2) the stamped value is only as fresh as the last stamp + regen (can lag one iteration).

### Aras Innovator

- Lock is a single nullable `locked_by_id` column with a claim/unclaim action and admin force-unclaim. Exactly the right size for a small shop.
- Generations (≈ iterations) auto-bump on first save of an edit cycle; revision letter only bumps via lifecycle Revise; **at Released the revision is immutable**.
- Creo connectors (ITI, T-Systems PDM Workbench) are Toolkit apps doing the same two jobs: gate open/save on claim status, and push PLM properties into CAD parameters on save.

### Lightweight systems & failure modes to design against

- SolidWorks PDM / Autodesk Vault / Git-LFS all use the **read-only file attribute** pattern: Get = read-only copy, Check Out = clear attribute + DB lock, Check In = restore. Documented failures: attribute/lock desync, CAD app stripping the read-only bit itself (Inventor does this!), stale local caches, Save-As bypass.
- Consensus: **the read-only bit is a deterrent, not enforcement.** Verify at check-in with content hashes; treat out-of-band edits as conflicts.
- Family tables: many item numbers in one physical file. **Lock at the generic file level; instances are co-locked.**

### Creo-specific facts (no Windchill)

- Creo **refuses to save** an object retrieved from a write-protected directory (native behavior) — unless `override_store_back`/`save_object_in_current` are set. **Ours are not set — keep it that way.**
- `save_objects` config controls whether incidental assembly saves rewrite unchanged children — worth setting to `changed_and_specified` to protect released children in assemblies.
- No native session-level lock without Windchill. A Toolkit/CreoJS save-event listener that vetoes the save is the closest DIY equivalent.

---

## 3. Creo-Side Capability Assessment (CreoJS)

| Capability | Verdict | Mechanism |
|---|---|---|
| Read parameters | ✅ Proven | `model.ListParams()`, `model.GetParam()` |
| Write/create parameters (`PDM_REV` etc.) | ✅ Documented, untested here | `pfcParameterOwner.CreateParam(name, value)`; confirm setter syntax via `help("pfcParameter")` in the CreoJS toolbar |
| Parameters on `.drw` | ⚠️ Should work (`pfcDrawing` extends `pfcModel`), must test | |
| HTTP to backend | ✅ Proven (workspace.html) | `fetch()` — **but** the app loads from `file://` so its Origin is `null`; direct calls to :8001 fail CORS. Route via local service :8083 (wildcard CORS) or serve the app over http. |
| **Save interception + veto** | ⚠️ **Documented in PTC's CreoJS docs, unverified in our install** | `session.AddActionListener({OnBeforeModelSave})` + `CCpfcXCancelProEAction.Throw()` to cancel the save. **This is the linchpin — build a 10-line PoC before architecting around it.** |
| Get file path / working dir / session models | ✅ Proven | `GetOrigin()`, `GetCurrentDirectory()`, `ListModels()` |
| Creo disk version (`.prt.N`) | ⚠️ Partial | Parse from `ListFiles(..., FILE_LIST_ALL, ...)`; `pfcModel.GetVersion()` is Windchill-only |
| Download file into working dir | ✅ Documented | CreoJS-native `downloadFile(url, path, handler)` — requires `web_link_file_write YES` in config.pro (**not currently set**). Alternative: keep using local service `/api/download`. |
| Open/erase models programmatically | ✅ Proven | `RetrieveModel()`, `model.Erase()` — note descriptor resolves against working dir, not absolute paths |
| Block in-session editing | ❌ Impossible without Windchill | Accept: we block **persistence**, not edits |
| JLink fallback | Only if the CreoJS listener fails | Java Toolkit `OnBeforeModelSave` is battle-tested; ~1-2 days for a minimal save-veto app via `protk.dat`. No existing JLink code to inherit. |

---

## 4. Proposed Design

### Core principles (stolen from Windchill/Aras)

1. **The lock lives in the database, at the item level.** One checkout row covers all the item's files (STEP, DXF, DRW, Creo). Family tables lock at the generic.
2. **`can_checkout = lifecycle_state in ('Design', 'Review')`.** Released/Obsolete items cannot be checked out — the only path is **Revise** (new revision letter, iteration 1, state back to Design). This single rule *is* the rev-lock.
3. **Enforce at the server, deter at the client.** The backend guards are the real lock (they can't be bypassed by clearing a file attribute). Creo-side layers (read-only bits, save-veto, UI gating) are UX and accident prevention.
4. **Released binaries are immutable snapshots.** On release, copy the item's current files to a frozen storage path. What you sent the supplier stays byte-identical forever, even after a revise.

### 4.1 Backend (Phase 1 — the real lock)

New endpoints on `items.py` (or a new `lifecycle.py` route):

- `POST /api/items/{item_number}/checkout` — body: `{user}`. 409 if already checked out by someone else, or if state is Released/Obsolete (message: "Released — use Revise"). Inserts `checkouts` row. Returns current files + revision so the client can sync before editing.
- `POST /api/items/{item_number}/checkin` — requires holding the lock. Bumps `items.iteration`, writes `lifecycle_history`, deletes the checkout row. (File uploads happen via the existing upload endpoint, which now stamps `uploaded_by`.)
- `POST /api/items/{item_number}/undo-checkout` — deletes lock, no bump. Admin can force.
- `POST /api/items/{item_number}/release` — state → Released, writes `lifecycle_history`, **snapshots all current files** to `pdm-files/{item}/released/{rev}/{filename}` (immutable copies), refuses if item is checked out.
- `POST /api/items/{item_number}/revise` — only from Released/Obsolete. Revision letter +1 (A→B), iteration → 1, state → Design, `lifecycle_history` row. Working files carry forward.

Guards added to **existing** endpoints:

- `POST /api/files/upload`: **409 if item is Released/Obsolete** ("Revise first"); 409 if checked out by a different user; require/record uploader identity; store `content_hash` (SHA-256) on the files row.
- `PATCH /api/items/{item_number}`: block edits of `revision`/`lifecycle_state` via generic update (transitions go through the endpoints above); optionally block all edits on Released except via revise.
- `POST /api/workspace/compare`: return `revision`, `iteration`, `lifecycle_state`, `checked_out_by`, and `content_hash` per item so the Creo app can show real status and detect true divergence (hash beats ±120s mtime).

Schema tweaks (one migration):

- `checkouts`: add `baseline_iteration INT` (stale-baseline rejection at check-in — Windchill's out-of-date protection) and `workstation TEXT`.
- `files`: add `content_hash TEXT`.
- No new tables needed. `lifecycle_history` finally gets used.

Identity (pragmatic v1): the local service and upload scripts send an `X-PDM-User` header from a config value (`Jack`, `Dan`, `Shop`). Not security — attribution. Real Supabase-JWT auth on write endpoints can come later; the Tailnet remains the security boundary.

### 4.2 Creo integration (Phase 2 — workspace.html becomes the PDM panel)

Extend the existing workspace-compare app:

- **Status columns**: PDM Rev / Iter / State / Lock-holder per row (from the enriched compare endpoint). Color-code: green = in sync, amber = local newer (needs check-in), blue = vault newer (needs update), red = Released (locked), padlock = checked out by someone else.
- **Check Out action**: calls backend checkout → local service clears read-only attribute on the local files → optionally downloads latest vault copy first if local is stale (compare will say). Refuse checkout when the vault is newer until the user updates — prevents editing a stale base.
- **Check In action** (extends the existing one): stamp parameters (below) → `model.Save()` → upload files (Creo + neutral formats) → backend checkin (iteration bump, lock release) → local service sets read-only attribute back.
- **Update action**: download latest vault files into the working dir (local service `/api/download` as today, or CreoJS `downloadFile` if we enable `web_link_file_write`), then `reloadModelFromDisk` (already implemented).
- **Release / Revise buttons** in the PDM web UI (ItemDetailView), not in Creo — deliberate actions belong in the browser where the release checklist lives.

### 4.3 Parameter stamping (Phase 2 — the `&PDM_REV` on drawings)

Copy Windchill's PTC_WM_* pattern with our own names:

- On check-in (and on demand via a "Stamp" button), CreoJS writes real parameters into the model: `PDM_REV`, `PDM_ITERATION`, `PDM_STATE`, `PDM_NUMBER` via `CreateParam`/value-set, then saves.
- Drawing formats reference `&PDM_REV` (and `&todays_date` etc. as today).
- **Pre-seed `PDM_REV=-`, `PDM_STATE=DESIGN` in start parts/templates** so formats never break on new models (Windchill's #1 gotcha).
- Accept the inherent lag: the stamp reflects the last check-in. The stamp happens *before* the upload within the same check-in flow, so the uploaded file contains its own correct rev.
- Verify parameter writing on `.drw` files early — documented as probable but untested.

### 4.4 Save-veto listener (Phase 3 — the "Check Out on the Fly" equivalent)

**Prototype first** (this is the highest-uncertainty, highest-payoff piece):

```javascript
// PoC: does our Creo 10 build support this?
session.AddActionListener({
  OnBeforeModelSave: function (descr) {
    // fetch lock state from localhost:8083 (sync via XHR or pre-cached state)
    // if item is Released or not checked out by me:
    CCpfcXCancelProEAction.Throw();   // veto the save — do NOT catch this
  }
});
```

- If it works: register it from the workspace app on load; on veto, show "Item csp0030 is Released (Rev B). Revise in PDM to edit." — our version of Windchill's dialog.
- If it doesn't: fall back to a minimal JLink app (`protk.dat`, ~1-2 days) that does only this, while CreoJS keeps everything else. A page-lifecycle caveat applies either way: a CreoJS listener likely dies if the user navigates the embedded browser away — JLink persists for the whole session.

### 4.5 Filesystem deterrents (Phase 3 — defense in depth)

- Local service sets **read-only attribute** on all local CAD files not checked out (sweep on demand + after check-in). Creo natively refuses to store back to write-protected sources — real friction, not just a warning. Keep `override_store_back` unset (verified currently unset).
- Set `save_objects changed_and_specified` in config.pro so saving an assembly doesn't rewrite unchanged (possibly released) children.
- Never trust the attribute: check-in always verifies `content_hash` of the local baseline vs. vault; out-of-band edits surface as conflicts instead of silent overwrites.

### 4.6 What we deliberately do NOT build

- Blocking in-session edits (impossible without Windchill; we block persistence).
- Save-As policing (Toolkit-heavy, low value for a 3-user shop).
- Per-file locks (item-level is the right granularity here).
- Full auth on day one (attribution header first; JWT enforcement later).

---

## 5. Phased Plan

| Phase | Scope | Effort | Value |
|---|---|---|---|
| **0. PoC spikes** | (a) `OnBeforeModelSave` + cancel in Creo 10; (b) `CreateParam` on a `.prt` and a `.drw`; (c) confirm param setter syntax | ~half day in Creo | De-risks the whole design |
| **1. Server lock** | Checkout/checkin/release/revise endpoints, Released guard on upload & item PATCH, `lifecycle_history` writes, release snapshots, content hashes, `X-PDM-User` attribution | Backend only, no Creo changes | **The actual rev-lock — suppliers-safe from here on** |
| **2. Creo panel** | Enriched compare (rev/state/lock/hash), checkout/checkin/update actions in workspace.html, parameter stamping, start-part seeding, Release/Revise UI in web frontend | Medium | Daily-driver workflow |
| **3. Enforcement layers** | Save-veto listener (or JLink fallback), read-only attribute sweeps, `save_objects` config | Small-medium | Accident-proofing |
| **4. Hardening** | Real auth on write endpoints, force-unclaim admin UI, stale-baseline rejection UX, family-table generic detection | As needed | Polish |

Phase 1 alone delivers the business need (released parts can't be silently overwritten). Everything after improves ergonomics and closes bypass routes.

---

## 6. Open Questions / Decisions for Jack

1. **Snapshot scope on release** — all file types (Creo + STEP + DXF + PDF) or neutral formats only? (Proposal: all.)
2. **Revision scheme** — letters only (A→B→C) as today? What about the supplier-facing docs that already show revs?
3. **Should Check-In from Creo auto-upload STEP/DXF too**, or stay Creo-files-only with the export pipeline handling neutrals as today?
4. **`FileCheckIn.vue`** — delete the orphan or rebuild it on the new endpoints as the web-side checkout UI?
5. **Where does Shop fit** — shop account should probably be viewer-only (no checkout); enforce per-role once auth lands.

---

## 7. Sources

- PTC: Checking Out Objects, Check Out on the Fly (CS44835, CS110902), WM parameters on drawings (CS24526, CS149310, CS262975), param↔attribute mapping, ACL Modify→Checkout, Revise behavior, Toolkit lock thread (community/33235), read-only directory save behavior.
- Aras: Item Claiming docs, versioning discipline, PDM Workbench / ITI Creo connectors.
- Failure modes: Autodesk KB (Inventor strips read-only bit), SolidWorks PDM cache desync articles, Git-LFS locking proposal & issues, SAP ECTR family-table handling.
- Internal: `.claude/agents/creojs-reference.md`, `workspace.html`, `PDM-Local-Service.ps1`, `Documentation/15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md`.
