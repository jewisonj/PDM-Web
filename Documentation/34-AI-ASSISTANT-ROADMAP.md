# AI Assistant Roadmap - Future Work

**Status:** Planning
**Last updated:** 2026-07-08
**Prerequisite reading:** `33-AI-ASSISTANT.md` (current architecture)

This document plans the two next major assistant capabilities, in priority
order, plus a short backlog. Both build on the existing tool pattern in
`backend/app/services/assistant_tools.py` and the approval-gated action flow.

---

## 1. McMaster-Carr Price Lookups

### Problem

Purchased parts (`mmc` prefix) carry a manually-entered `unit_price` on the
`items` table. Prices go stale, and unpriced parts silently contribute $0 to
project cost estimates (now at least flagged by `audit_project`). McMaster
part numbers are already embedded in our item data, so the price is
knowable - we just never fetch it.

### Approach

**Phase 1 - lookup tool (read-only, on demand)**

- New assistant tool `get_mcmaster_price(item_number)`:
  1. Resolve the item; extract the McMaster part number. Decide the source of
     truth first: either the item `name`/`description` contains the McMaster
     part number today, or we add a dedicated `supplier_part_number` column to
     `items` (recommended - one migration, removes parsing guesswork).
  2. Fetch the product page or use McMaster's official API if enrolled
     (McMaster offers a B2B Product Information API to account holders;
     scraping the public site is against their ToS and brittle - prefer the
     API route and ask McMaster for access with the shop's account).
  3. Return `{part_number, description, current_price, unit_of_measure,
     cached_at}`.
- Cache results in a small `supplier_prices` table
  `(part_number pk, supplier, price, uom, fetched_at)` with a staleness window
  (e.g., 30 days) so repeated BOM costing doesn't hammer the API.

**Phase 2 - price sync as an approval-gated action**

- Action tool `update_item_price(item_number, new_price)` following the
  existing approval-card pattern.
- Composite flow the model can drive: "check all mmc parts in project X
  against McMaster" -> table of stale/missing prices -> one approval card per
  changed price (or a single batch action `sync_project_supplier_prices` with
  the full diff in the card).

**Phase 3 - background staleness check**

- Nightly job (work_queue task type `price_check`) that refreshes cached
  prices for mmc parts used in **active** MRP projects only, and records
  deltas. The assistant (and later a dashboard card) can then answer "which
  purchased parts got more expensive since we quoted?"

### Open questions / risks

- API access requires a McMaster account enrollment step (their Product
  Information API needs a certificate). Without it, fallback is manual entry
  assisted by the assistant (it drafts the list, user fills prices).
- Quantity price breaks: store base each-price first; breaks are a later
  enhancement to `supplier_prices` (jsonb column).
- Other suppliers (`spn` prefix) have no API; keep the schema
  supplier-agnostic (`supplier` column) so manually-refreshed prices flow
  through the same cache and audit trail.

### Estimated scope

Phase 1: ~1 day once API access exists (tool + cache table + tests).
Phase 2: ~0.5 day (reuses action flow). Phase 3: ~1 day (worker job + delta
reporting).

---

## 2. Looking Inside Prints (PDF Content Extraction)

### Problem

The assistant can list and link prints but is blind to their contents. Users
ask things the drawing answers: finish notes, tolerances, weld callouts, hole
counts, title-block data. Today the answer is "download it and look."

### Approach

**Phase 1 - text extraction pipeline**

- On PDF upload (and once as a backfill over the ~1,500 existing files),
  extract embedded text with `pypdf`/`pdfplumber` (our prints come from Creo,
  so text is real text, not scans - no OCR needed for the common case).
- Store in a new table:
  `file_text (file_id pk/fk, extracted_text text, page_count int, extracted_at timestamptz)`
  plus a generated `tsvector` column with a GIN index for full-text search.
- Extraction runs as a `work_queue` task type (`extract_text`) so it uses the
  existing worker loop and failure/retry visibility the assistant already has.

**Phase 2 - assistant tools**

- `read_print(item_number)` - returns the extracted text of the item's latest
  PDF (capped, e.g. first 8k chars) so the model can answer "what's the
  finish note on csp00200?" directly.
- `search_prints(query)` - full-text search across all prints: "which
  drawings mention powder coat?" returns item numbers + matching snippets.

**Phase 3 - vision fallback and richer questions**

- For PDFs with little/no embedded text (scans, image-heavy drawings), render
  page 1 to PNG (`pdf2image`/poppler in the worker container) and pass the
  image to Claude directly - the Messages API accepts images, and the agent
  loop already exists. Gate this behind a size/page limit; it's slower and
  costs more tokens.
- This also unlocks "does the drawing show a weld symbol on the left flange?"
  -style geometric questions that text extraction can't answer.
- Optional later: attach the rendered page thumbnail into the chat UI when the
  assistant references a drawing, so the user sees what it's reading.

### Open questions / risks

- Revision handling: extract per file (not per item) and always answer from
  the latest iteration of the latest revision; say which rev the answer came
  from.
- Token budget: never dump full drawing text into context by default -
  snippets + targeted reads.
- Title blocks are drawn tables; text extraction returns their contents in
  reading order, which is usually enough. If field-level data is needed
  (drawn-by, date, scale), a small regex layer over known title-block labels
  beats layout parsing.

### Estimated scope

Phase 1: ~1 day (extraction task + table + backfill script). Phase 2:
~0.5 day (two tools + prompt guidance). Phase 3: ~1-2 days (worker rendering
+ image passing).

---

## Backlog (captured, not yet planned)

- **Nesting visibility:** expose `nest_jobs` / `nest_results` (material
  utilization, sheet counts) as read tools once nesting sees regular use.
- **Morning digest:** scheduled summary (projects due this week, failed
  tasks, low stock) pushed to the dashboard or email - the audit and
  low-stock tools already produce the content; this is a scheduler + delivery
  question.
- **Batch write actions:** approve a group of related changes in one card
  (e.g., all routing time updates from a time analysis) instead of one card
  each.
- **Per-user conversations:** `assistant_conversations` has no user column
  yet (matches the app's current no-auth model). Add `created_by` when the
  app grows real per-user auth.
