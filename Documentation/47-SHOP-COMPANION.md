# Shop Companion (Shop Notes)

**Status:** New (2026-09-16), migration not yet applied
**Related Docs:** [03-DATABASE-SCHEMA.md](03-DATABASE-SCHEMA.md), [04-SERVICES-REFERENCE.md](04-SERVICES-REFERENCE.md), [24-VERSION-HISTORY.md](24-VERSION-HISTORY.md)

---

## Purpose

Shop-floor workers rarely sit at a PDM workstation. Shop Companion gives them a phone-first
page — `/shop` — to fire off a quick note ("this bracket doesn't fit", "missing holes on
this weldment") with photos, tagged to a project/assembly/part, without logging into the
main PDM/MRP system. Engineering triages the notes on a normal MRP page,
`/mrp/shop-notes`, using their existing staff login.

This is intentionally lightweight: no offline queue, no push notifications, one shared PIN
for the whole shop. See **Known Limitations** below.

---

## Worker Flow (`/shop`)

One-screen, phone-first form: **PIN once -> name once -> project -> (assembly) -> (part) ->
note -> photos -> Send.**

1. **PIN screen** — worker enters the shared shop PIN (4-6 digits, auto-submits at 4). On
   success the phone stores a signed device token (see Auth Model) so this step is never
   shown again on that phone (until the token expires in 365 days).
2. **Name screen** — shown once; the name is remembered on the device (`localStorage`) and
   sent as `author_name` on every note from then on.
3. **Form screen:**
   - **Project select** — populated from `GET /api/shop-notes/projects`; last-picked project
     is remembered per device. Open (non-Complete) projects sort first.
   - **Assembly / Part autocomplete** (`ShopItemPicker.vue`) — populated from
     `GET /api/shop-notes/projects/{id}/items`, which splits the project BOM into
     `assemblies` (items that have children, i.e. weldments/sub-assemblies/top assembly) and
     `parts` (every item in the project). Each part carries `parent_ids` so picking a part
     auto-fills its parent assembly (`defaultAssemblyForPart` in
     `frontend/src/utils/shopNotes.ts`). If nothing in the BOM matches what the worker
     types, the free text is kept as `assembly_text` / `part_text` instead of a linked
     item ID — the reviewer can match it up later.
   - **Note** — free text; the phone's own keyboard microphone/dictation is used for
     voice-to-text. There is no Deepgram/AI transcription step here (that's reserved for
     the treatment-log-style voice feature elsewhere in the codebase's sibling projects,
     not this app).
   - **Photos** — camera or gallery. Each photo is downscaled client-side to a 1600px-long-edge
     JPEG (`resizeImage()` in `frontend/src/utils/shopNotes.ts`, using
     `createImageBitmap`/canvas) before upload, to keep shop Wi-Fi/cellular uploads fast.
     Up to 10 photos per note, 12 MB per photo (server-enforced).
   - Send is enabled once there's a note or at least one photo (both are optional
     individually, not together).
4. **Sent screen** — confirms and returns to the form for the next note (project selection
   persists).

### Add to Home Screen (installable PWA)

`/shop` is a standalone installable PWA — but only that route. The manifest
(`frontend/public/shop.webmanifest`) and icons (`shop-icon-192.png`, `shop-icon-512.png`,
`shop-icon-512-maskable.png`) are injected into `<head>` only when `ShopNoteView.vue` mounts,
so "Add to Home Screen" on `/shop` launches straight into `/shop` (manifest `start_url`/`scope`
are both `/shop`). There is **no service worker** — this is not offline-capable, just an
installable shortcut with a standalone (chrome-less) window.

- **iPhone (Safari):** open `https://<host>/shop` -> Share button -> "Add to Home Screen" ->
  Add. Opens standalone next time from the home screen icon.
- **Android (Chrome):** open `https://<host>/shop` -> menu (⋮) -> "Add to Home screen" / "Install
  app" -> Install.

---

## Reviewer Flow (`/mrp/shop-notes`)

Normal MRP page, behind the existing Supabase staff auth. Reachable from the MRP dashboard's
**Shop Notes** nav button, which shows a live badge with the count of `new` notes
(`getShopNoteSummary()` / `GET /api/shop-notes/summary`).

- **Filters:** status (`new` / `reviewed` / `resolved` / `all`) and project, reflected in the
  URL query string.
- **Per-note editing:** one note edits at a time — reassign/fix the linked assembly and part
  (or their free-text fallback), edit the project, edit the note body itself, add
  reviewer notes.
- **Status transitions:** mark `reviewed`, mark `resolved`, or reopen back to `new`.
  `reviewed_at` is set/cleared server-side based on the status change (see `PATCH` behavior
  below).
- **Delete:** removes the note, its photo rows, and the underlying storage objects (best
  effort — DB delete always succeeds even if storage cleanup fails; orphaned storage objects
  are harmless).
- **Photo lightbox:** click a photo thumbnail to view full-size; photos are served through
  short-lived (1-hour) signed URLs, never public.

---

## Auth Model

Two independent auth paths hit the same `/api/shop-notes/*` router:

| Actor | Credential | Token | Lifetime | Endpoints |
|---|---|---|---|---|
| Shop worker | Shared shop PIN (`Settings.shop_pin`, env `SHOP_PIN`, default `1010`) | Custom HS256 JWT (`type: "shop"`) | 365 days | login, projects, project items, create note |
| Reviewer (staff) | Existing Supabase Auth session | Supabase access token | Normal Supabase session lifetime | everything, including reviewer-only summary/list/patch/delete |

- **`POST /api/shop-notes/login`** — body `{ "pin": "1010" }`. Verifies with
  `hmac.compare_digest` (constant-time) against `Settings.shop_pin`. On success returns a JWT
  signed with a secret derived from `f"shop_{settings.supabase_service_key[:32]}"` (so it
  doesn't need its own secret env var, but does mean rotating `SUPABASE_SERVICE_ROLE_KEY`
  invalidates all shop device tokens). Token expires in 365 days.
- **Worker/staff endpoints** (`require_shop_or_staff` dependency) accept *either* a valid shop
  JWT *or* a valid Supabase session token — this lets a staff member also use `/shop` from
  their own phone without re-entering the PIN.
- **Reviewer-only endpoints** (`require_staff` dependency) — `summary`, `GET` list, `GET`
  single, `PATCH`, `DELETE` — require a real Supabase staff session; a shop device token is
  rejected (401 "Staff login required").
- There is **one PIN for the whole shop** — it does not identify who filed a note. The
  `author_name` field (worker-typed, remembered per device) is the only identity signal, and
  it is not verified against any user table.

---

## API Endpoints

All under `/api/shop-notes` (see `backend/app/routes/shop_notes.py`).

### Worker-facing

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/login` | none (PIN in body) | Exchange shop PIN for a 365-day shop JWT |
| GET | `/projects` | shop or staff | List projects (open first, then Complete), for the project picker |
| GET | `/projects/{project_id}/items` | shop or staff | BOM split into `assemblies` (have children) and `parts` (all project items), each part carrying `parent_ids` |
| POST | `` (multipart) | shop or staff | Create a note: `note`, `author_name`, `project_id`, `assembly_item_id`/`assembly_text`, `part_item_id`/`part_text`, `photos[]` (files) |

### Reviewer-facing (staff Supabase token required)

| Method | Path | Description |
|---|---|---|
| GET | `/summary` | Counts per status (`new`/`reviewed`/`resolved`) for the dashboard badge |
| GET | `` | List notes, filter by `status` and/or `project_id`, `limit` (max 500) |
| GET | `/{note_id}` | Single note with joined project/assembly/part and signed photo URLs |
| PATCH | `/{note_id}` | Update status, note text, project/assembly/part links (or their text fallback), reviewer notes; `clear_assembly`/`clear_part` flags to explicitly unlink |
| DELETE | `/{note_id}` | Delete note + photo rows + storage objects |

`GENERATE_DXF`-style background processing is not involved here — notes are synchronous
inserts, photos are uploaded inline during the `POST` request.

---

## Database Schema

Migration: `backend/migrations/2026-09-16_shop_notes.sql` — **NOT YET APPLIED to Supabase.**
Must be run manually (Supabase SQL editor or MCP) before the feature works in any environment.

```sql
-- Private bucket for note photos, served only through backend-issued signed URLs
insert into storage.buckets (id, name, public)
values ('shop-note-photos', 'shop-note-photos', false)
on conflict (id) do nothing;

create table public.shop_notes (
  id uuid primary key default gen_random_uuid(),
  project_id uuid references public.mrp_projects(id) on delete set null,
  assembly_item_id uuid references public.items(id) on delete set null,
  part_item_id uuid references public.items(id) on delete set null,
  assembly_text text,        -- free text if no BOM match (reviewer can fix later)
  part_text text,
  note text not null default '',
  author_name text,
  status text not null default 'new' check (status in ('new', 'reviewed', 'resolved')),
  reviewer_notes text,
  reviewed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.shop_note_photos (
  id uuid primary key default gen_random_uuid(),
  note_id uuid not null references public.shop_notes(id) on delete cascade,
  file_path text not null,   -- "<bucket>/<path>", same convention as design_book_images
  file_size bigint,
  mime_type text,
  sort_order int not null default 0,
  created_at timestamptz not null default now()
);
```

**Indexes:** `shop_notes(status, created_at desc)`, `shop_notes(project_id)`,
`shop_notes(part_item_id)`, `shop_note_photos(note_id)`.

**Trigger:** `trg_shop_notes_updated_at` keeps `updated_at` current on every update.

**RLS:** Enabled on both tables with **no anon/authenticated policies** — the backend talks to
them exclusively via the Supabase service-role (admin) client, same pattern as other
backend-owned tables. There is no direct frontend Supabase access to these tables.

**Note for supabase agent:** this migration needs to be applied (`insert into storage.buckets`
+ two `create table` + trigger) before Shop Companion works anywhere. It is additive only —
no existing tables are touched.

---

## Setup Steps

1. **Apply the migration** — run `backend/migrations/2026-09-16_shop_notes.sql` against the
   Supabase project (SQL editor or MCP). Confirms:
   - `shop-note-photos` storage bucket exists (private)
   - `shop_notes` and `shop_note_photos` tables exist with RLS enabled
2. **Set the shop PIN** (optional — defaults to `1010`) — add to `backend/.env`:
   ```bash
   SHOP_PIN=1234
   ```
   Restart the backend after changing it (see Gotcha #1 in Doc 15 — services cache old
   config). Changing the PIN does **not** invalidate already-issued device tokens; tokens
   only stop being issued for anyone who tries to log in again with the old PIN.
3. **Share the `/shop` URL** with shop-floor workers, e.g. `https://<your-domain>/shop`.
4. **Add to Home Screen** on each worker's phone (see instructions above) so it behaves like
   an app icon.
5. Confirm reviewer access: any existing staff user can open `/mrp/shop-notes` with their
   normal PDM login; no extra setup needed there.

---

## Known Limitations

- **No offline queue.** If a worker's phone loses connectivity mid-form, `Send` will fail and
  the note/photos are not queued for retry — the worker must resend once back online. Not
  IndexedDB-backed like a true offline-first PWA.
- **No notifications.** Reviewers must check `/mrp/shop-notes` manually; there is no
  email/SMS/push alert when a new note comes in. The dashboard badge count is the only signal.
- **Shared PIN, no per-worker identity.** One PIN for the entire shop; `author_name` is
  free-typed and unverified. This is fine for triage but not an audit trail.
- **Device tokens live 365 days** and are tied to the service-role key fragment — rotating
  `SUPABASE_SERVICE_ROLE_KEY` silently invalidates every shop device's token (all workers
  would need to re-enter the PIN).
- **No service worker / true offline PWA support** — `/shop` is installable (manifest +
  icons) but does not cache assets or work without network.
- **Photo storage is not deduplicated or size-audited** beyond the 12 MB/photo,
  10-photos/note caps; there is no cleanup job for orphaned storage objects from failed
  deletes (rare, and considered harmless per the code comment).

---

## Files

**Backend:**
- `backend/migrations/2026-09-16_shop_notes.sql` (new, unapplied)
- `backend/app/services/shop_auth.py` (new) — PIN verification, shop JWT create/decode
- `backend/app/routes/shop_notes.py` (new) — all `/api/shop-notes/*` endpoints
- `backend/app/config.py` — added `shop_pin` setting (default `"1010"`, env `SHOP_PIN`)
- `backend/app/main.py`, `backend/app/routes/__init__.py` — router registration
- `backend/tests/test_shop_notes.py` (new)

**Frontend:**
- `frontend/src/views/ShopNoteView.vue` (new) — `/shop` worker form
- `frontend/src/views/MrpShopNotesView.vue` (new) — `/mrp/shop-notes` reviewer page
- `frontend/src/components/ShopItemPicker.vue` (new) — assembly/part autocomplete
- `frontend/src/services/shopNotesApi.ts` (new) — API client, device token/name/project
  storage helpers (`shopDevice`)
- `frontend/src/utils/shopNotes.ts` (new) — pure helpers: item filtering, parent-assembly
  lookup, photo resizing
- `frontend/src/utils/shopNotes.test.ts` (new)
- `frontend/src/router/index.ts` — added `/shop` (`shopRoute: true`, no auth) and
  `/mrp/shop-notes` routes
- `frontend/src/views/MrpDashboardView.vue` — "Shop Notes" nav button + new-note badge
- `frontend/public/shop.webmanifest`, `frontend/public/shop-icon-192.png`,
  `frontend/public/shop-icon-512.png`, `frontend/public/shop-icon-512-maskable.png` (new)

**Cross-reference for other agents:**
- `supabase` agent: new tables/bucket, migration not yet applied
- `mrp` agent: new dashboard nav item + badge on `MrpDashboardView.vue`
- `style` agent: `ShopNoteView.vue` is phone-first/dark (`#020617` background), distinct from
  the rest of PDM-Web's desktop-first light/dark MRP split — review for consistency if styled
  further
