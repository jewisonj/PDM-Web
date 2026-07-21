# 43 — Design Book Image Management System

**Status:** COMPLETE
**Date:** 2026-07-21
**Version:** 3.9.5
**Related:** [36-MASTER-DESIGN-BOOK-PLAN.md](36-MASTER-DESIGN-BOOK-PLAN.md), [15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md](15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md)

---

## Overview

The Design Book Image Management System allows users to upload, organize, and manage images that are embedded in the Master Design Book's III-00 (General Reference) section. This document describes the three key improvements made to the system:

1. **Image Hash Detection** — Auto-detects when images change and triggers III-00 section re-rendering
2. **Route Ordering Fix** — Corrected FastAPI route order to prevent catch-all interception
3. **Upload Form State** — Preserves project context across multiple uploads

---

## 1. Image Hash Detection for Design Book Re-rendering

### Problem

When images were added, modified, or removed from the Design Book image library, the III-00 (General Reference) section was not detected as changed during the Check & Update workflow. The section would not re-render with updated images.

### Root Cause

The Master Design Book diffing algorithm compares content hashes to detect changes. The III-00 descriptor's hash input did not include any image-related data. When images changed in the `design_book_images` table, the descriptor payload remained the same, so the content hash stayed unchanged.

### Solution

Added `_compute_image_hash()` function that:
1. Queries all images for the template project
2. Builds a deterministic string from image IDs and updated_at timestamps
3. Returns SHA-256 hash of the concatenated data

This hash is injected into the III-00 descriptor's payload before hashing:

```python
# backend/app/services/master_design_book.py (lines 1896-1903)

# Inject image hash into general_reference descriptor to trigger re-render when images change
if book.get("template_project_id"):
    image_hash = _compute_image_hash(supabase, book["template_project_id"])
    for d in non_spine:
        if d.get("kind") == "general_reference":
            d.setdefault("payload", {})["_image_hash"] = image_hash
            break
```

### How It Works

1. Before hashing descriptors, compute image hash from project's images
2. Find the III-00 (general_reference) descriptor
3. Inject `_image_hash` into its `payload` dictionary
4. When the descriptor is hashed, the image hash participates
5. If images changed, hash changes → section detected as changed → re-renders

### Benefits

- **Automatic change detection** — Adding/removing images triggers III-00 re-render
- **Accurate revision tracking** — Change notices show when images changed
- **No manual intervention** — System detects and handles image changes transparently
- **Deterministic** — Same images always produce same hash
- **Lightweight** — Only queries IDs and timestamps, not full image data

---

## 2. Route Ordering Fix in design_book_images.py

### Problem

When accessing `/api/design-book-images/list` or `/api/design-book-images/upload`, the API returned 404 or responded with the wrong handler. The parameterized `/{image_id}` route was catching all paths.

### Root Cause

FastAPI route matching is order-dependent. The parameterized route `@router.get("/{image_id}")` was defined before specific paths like `/list` and `/upload`. Since `/{image_id}` matches any path segment, it intercepted requests intended for `/list` and `/upload`.

### Solution

Reorganized routes to place specific paths BEFORE parameterized routes:

**Before:**
```python
@router.get("")  # Empty path for list
async def list_images(...):
    ...

@router.get("/{image_id}")  # Catches everything!
async def get_image(image_id: UUID):
    ...
```

**After:**
```python
# Specific paths FIRST
@router.get("/list")  # Changed from "" to "/list"
async def list_images(...):
    ...

@router.post("/upload")
async def upload_image(...):
    ...

# Parameterized routes LAST
@router.get("/{image_id}")
async def get_image(image_id: UUID):
    ...
```

### Frontend Update

Changed API call from `/api/design-book-images` to `/api/design-book-images/list`

### Benefits

- **Predictable routing** — API endpoints work as documented
- **No UUID validation errors** — Frontend can call `/list` without errors
- **Clear separation** — Specific operations vs. ID-based lookups

---

## 3. Upload Form State Fix in MrpDesignBookImagesView.vue

### Problem

After uploading an image in the Design Book Images view, the project ID was cleared from the upload form. Subsequent uploads lost the project association, requiring the user to re-select the project each time.

### Root Cause

The `resetUploadForm()` function cleared ALL form fields after successful upload, including `uploadProjectId`. When viewing images in a Design Book context (where `bookCode` is set and the project ID is pre-selected), clearing `uploadProjectId` lost this context.

### Solution

Modified `resetUploadForm()` to preserve `uploadProjectId` when in Design Book context:

```javascript
function resetUploadForm() {
  uploadFile.value = null
  uploadPreview.value = null
  uploadCaption.value = ''
  uploadNotes.value = ''
  uploadCategoryId.value = ''
  // Keep uploadProjectId if we're in a design book context
  if (!bookCode.value) {
    uploadProjectId.value = ''
  }
  uploadItemSearch.value = ''
  uploadItemId.value = ''
  uploadWidthPct.value = 100
}
```

**Logic:** If `bookCode` is set (Design Book mode), preserve the project ID. Otherwise (standalone image management), clear it.

### Benefits

- **Reduces clicks** — No need to re-select project after each upload
- **Prevents errors** — Images automatically tagged with correct project
- **Better UX** — Context preservation matches user mental model

---

## Files Changed

### Image Hash Detection
- `backend/app/services/master_design_book.py` (lines 246-267) — Added `_compute_image_hash()` function
- `backend/app/services/master_design_book.py` (lines 1896-1903) — Injected image hash into III-00 descriptor payload

### Route Ordering Fix
- `backend/app/routes/design_book_images.py` (lines 158, 348+) — Reorganized routes, changed `/` to `/list`
- `frontend/src/views/MrpDesignBookImagesView.vue` (line ~180) — Updated API call to `/list`

### Upload Form State
- `frontend/src/views/MrpDesignBookImagesView.vue` (lines 293-306) — Modified `resetUploadForm()` to preserve project ID

---

## How the System Works Now

### Upload Workflow

1. User navigates to Design Book Images view with a book code (e.g., `/mrp/design-book-images/spa-standard`)
2. System loads the design book and auto-selects its template project
3. User uploads images with captions, notes, and categories
4. Images are stored in Supabase `design-book-images` bucket
5. Database records created in `design_book_images` table
6. **Project ID persists** across uploads — no need to re-select

### Image Organization

- **Categories** — System categories (Build Area, Safety, Branding) + custom categories
- **Project Association** — Images linked to template project via `project_id`
- **Item Association** — Optional link to specific parts via `item_id`
- **Metadata** — Caption, notes, display width (25%/50%/75%/100%)

### Design Book Integration

1. User adds/modifies/removes images in image library
2. User clicks "Check for Changes" in Master Design Book view
3. **Image hash computed** from all project images (IDs + timestamps)
4. Image hash injected into III-00 descriptor payload
5. **III-00 content hash changes** (because payload changed)
6. Section detected as changed → marked for re-rendering
7. Update generates new III-00 PDF with current image set
8. Change notice shows `"SECTION III-00 REVISED — IMAGES UPDATED"`

### Image Rendering in III-00

- Images rendered in **2x2 grid layout** on "BUILD AREA PHOTOS" pages
- Each photo shows caption and notes below the image frame
- Width controlled by `width_pct` setting (25%, 50%, 75%, or 100%)
- Missing images handled gracefully (logged, skipped in layout)

---

## API Reference

### List Images
```
GET /api/design-book-images/list
Query params: category_id, project_id, item_id, search, limit, offset
Returns: Array of image records
```

### Upload Image
```
POST /api/design-book-images/upload
Form data: file, caption, notes, category_id, item_id, project_id, width_pct
Returns: Created image record
```

### Get Image
```
GET /api/design-book-images/{image_id}
Returns: Single image record with category and item relations
```

### Update Image
```
PATCH /api/design-book-images/{image_id}
Body: { caption?, notes?, category_id?, item_id?, project_id?, width_pct? }
Returns: Updated image record
```

### Delete Image
```
DELETE /api/design-book-images/{image_id}
Returns: { message: "Image deleted" }
```

### Get Signed URL
```
GET /api/design-book-images/{image_id}/url
Returns: { url, filename, expires_in }
```

---

## Database Schema

### design_book_images

```sql
CREATE TABLE design_book_images (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  file_name TEXT NOT NULL,
  file_path TEXT NOT NULL,  -- 'design-book-images/{folder}/{filename}'
  file_size INTEGER,
  mime_type TEXT,
  caption TEXT,
  notes TEXT,
  width_pct INTEGER DEFAULT 100 CHECK (width_pct IN (25, 50, 75, 100)),
  category_id UUID REFERENCES design_book_image_categories(id),
  item_id UUID REFERENCES items(id),
  project_id UUID REFERENCES mrp_projects(id),
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);
```

### design_book_image_categories

```sql
CREATE TABLE design_book_image_categories (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT UNIQUE NOT NULL,
  description TEXT,
  icon TEXT,
  is_system BOOLEAN DEFAULT false,
  sort_order INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT now()
);
```

**System Categories:**
- Build Area (icon: 🏗️, sort: 1)
- Safety & Compliance (icon: ⚠️, sort: 2)
- Branding & Marketing (icon: 🎨, sort: 3)

---

## Key Lessons

### Route Ordering (Pitfall #43)
- **Always define specific paths before parameterized paths** in FastAPI routers
- Parameterized routes act as catch-alls that intercept any path
- Test all endpoints after route reorganization
- Use explicit path prefixes (`/list`, `/upload`) instead of empty strings

### Context Preservation
- **Preserve workflow context** when resetting forms between operations
- Check for ambient state (like `bookCode`, `projectId`) before clearing fields
- Design reset logic based on use cases: standalone vs. workflow-embedded
- Test multi-step workflows to catch context loss issues

### Change Detection
- **Include related data in hash inputs** when that data affects rendered output
- Use deterministic hashing for cache invalidation and change detection
- Compute hashes from source data (DB queries), not rendered artifacts
- Test change detection with add/modify/delete scenarios

---

## Related Documentation

- **[36-MASTER-DESIGN-BOOK-PLAN.md](36-MASTER-DESIGN-BOOK-PLAN.md)** — Master Design Book architecture
- **[15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md](15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md)** — Pitfall #43 (detailed)
- **[24-VERSION-HISTORY.md](24-VERSION-HISTORY.md)** — Version history (v3.9.5)

---

**Last Updated:** 2026-07-21
**Version:** 3.9.5
**Status:** Complete
