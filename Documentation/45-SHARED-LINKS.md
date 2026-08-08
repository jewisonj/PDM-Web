# Shared Links - Permanent Public Links for Project PDFs

**Status:** Implemented
**Added:** 2026-08-07
**UI:** `/mrp/shares` (Shared Links page), plus 🔗 Share buttons on Project
Tracking, Build Tracker, and Build Book views.

## Why

Build books, tracker sheets (11x17 / letter), design books, and print packets
need to go to customers and the shop with "just a link." Signed URLs from the
private buckets expire after 1 hour, and Supabase Dashboard sharing is
awkward. Two separate problems were conflated as "too large":

1. **Link expiry** - signed URLs die after an hour; solved here with a public
   bucket whose URLs never expire.
2. **The project-wide upload size limit (~50MB)** - files bigger than this
   cannot be uploaded to Supabase Storage at all, regardless of per-bucket
   `file_size_limit` settings (the `design-books` bucket's 150MB setting has
   no effect past the global cap). The build book generator already skips
   storage above 45MB for this reason. **Fix: Supabase Dashboard -> Project
   Settings -> Storage -> "Upload file size limit"** - on a paid plan this can
   be raised (500MB is plenty for the biggest bound book); on the free plan
   50MB is a hard cap.

## How it works

- A **public** storage bucket `shared` serves objects at permanent URLs:
  `{SUPABASE_URL}/storage/v1/object/public/shared/{kind}/{project}/{file}.pdf`
  No login, no expiry. Anyone with the link can view/download.
- The `shared_links` table is the registry (kind, project, title, path, URL,
  size). The Shared Links page lists links with Copy and Revoke. Revoking
  deletes the object - the URL dies immediately.
- Re-sharing the same document overwrites the same path, so **the link stays
  stable** while the content updates (nice for "the current tracker sheet").

## Flows

| Document | How to share |
|----------|--------------|
| Tracker sheet (11x17 or letter) | Print -> Save as PDF in the browser, then drop the file on the Shares page (project preselected via the 🔗 Share button) |
| Build book (browser-printed) | Same print-to-PDF -> drop flow |
| Print packet | One click - "Share print packet" on the Shares page copies the stored packet server-side |
| Design book | One click - "Share design book" on the Shares page copies the full PDF from storage |

## API

- `POST /api/share` - multipart PDF upload (`file`, `kind`, `project_code?`, `title?`) -> link row
- `POST /api/share/from-storage` - `{bucket, path, kind, project_code?, title?}` -> link row
- `POST /api/share/print-packet/{project_id}` - share the project's generated packet
- `POST /api/share/design-book/{book_code}` - share the design book's full PDF
- `GET /api/share?project_code=` - list links
- `DELETE /api/share/{id}` - revoke (deletes object + row)

Uploads over 150MB return a 413 explaining the limit. Note: the Supabase spend
cap can reduce the effective limit to ~50MB; disable spend cap for full 150MB.
Migration:
`backend/migrations/2026-08-07_shared_links.sql`.

## Why not Google Drive / SharePoint?

Considered and deliberately deferred: both need OAuth app setup + token
storage for an unattended backend, add a second place documents live, and
their "anyone with the link" behavior is org-policy dependent. Supabase was
already hosting these files - the actual gaps were link expiry and the upload
cap, both addressed above. If books routinely exceed the raised limit someday,
a Drive uploader can slot behind the same `shared_links` registry
(`public_url` just points at Drive instead).

## Future: On-Demand Streaming (No Storage Limits)

For very large files that exceed Supabase upload limits (especially with spend
cap enabled), consider adding **on-demand streaming endpoints**:

- `/api/public/design-book/{token}/{book_code}.pdf` - generates fresh PDF and
  streams directly, no storage needed
- `/api/public/tracker/{token}/{project_code}.pdf?size=letter|tabloid` - would
  need server-side HTML→PDF rendering (Playwright or WeasyPrint)

**Trade-offs:**
- Pro: No size limits (nothing uploaded to storage)
- Pro: Always serves current/fresh content
- Con: Slower (generates on each request)
- Con: More server load
- Con: Link fails if server is down

The shared link would be the API URL itself. Not yet implemented but noted for
future if storage limits become a recurring issue.
