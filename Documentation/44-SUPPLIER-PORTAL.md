# Supplier Portal

## Overview

The Supplier Portal feature provides external suppliers with secure, limited access to view items they are manufacturing and download approved files. This enables collaboration with vendors while maintaining strict access control and audit trails.

**Use Case:** When outsourcing parts manufacturing, suppliers need access to drawings and 3D models. Instead of emailing files, the Supplier Portal provides:
- Secure login for each supplier
- Admin-controlled access to specific items
- File type restrictions (e.g., PDF and STEP only, no source CAD)
- Two-way communication via per-item comments
- Complete audit trail of what was accessed and when

**Version:** Added in v3.9.6 (2026-07-22)

---

## Architecture

### Authentication Strategy

**Separate from Supabase Auth:** Suppliers use a custom JWT-based authentication system completely independent from the main PDM user authentication. This separation ensures:
- Suppliers never get Supabase credentials
- Supplier tokens stored in separate localStorage key (`pdm_supplier_token`)
- No RLS policy conflicts between internal users and suppliers
- Simple password-based login (bcrypt hashing)

**Backend Implementation:**
- `backend/app/services/supplier_auth.py` - Password hashing (bcrypt) and JWT token creation (PyJWT)
- Tokens expire after 24 hours (configurable)
- Passwords are hashed using bcrypt with auto-generated salt

**Frontend Implementation:**
- `frontend/src/stores/supplierAuth.ts` - Pinia store managing supplier session
- Separate localStorage key: `pdm_supplier_token` (vs `pdm_user_token` for internal users)
- Automatic token refresh on navigation
- Guard routes: `/supplier-login`, `/supplier/portal`, `/supplier/item/:itemNumber`

---

## Database Schema

### Three New Tables

#### 1. `suppliers` - Supplier Account Management

Stores supplier company accounts and login credentials.

```sql
CREATE TABLE suppliers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_name    VARCHAR(255) NOT NULL UNIQUE,
    login_email     VARCHAR(255) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,          -- bcrypt hash
    is_active       BOOLEAN NOT NULL DEFAULT true,
    contact_name    VARCHAR(255),
    phone           VARCHAR(50),
    address         TEXT,
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_suppliers_login_email ON suppliers(login_email);
CREATE INDEX idx_suppliers_company_name ON suppliers(company_name);
```

**Key Fields:**

- `company_name` - Unique supplier identifier (e.g., "Acme Manufacturing")
- `login_email` - Email address for login (e.g., "portal@acme.com")
- `password_hash` - bcrypt hashed password (never stored in plaintext)
- `is_active` - Disable supplier access without deleting account
- `contact_name`, `phone`, `address` - Optional contact information
- `notes` - Admin notes about the supplier relationship

**Security:**
- Passwords are hashed using bcrypt with automatic salt generation
- Only active suppliers (`is_active=true`) can log in
- Password hash is never returned in API responses

**RLS Policies:**
- No RLS policies (table accessed only via backend service functions)
- Admin endpoints require internal PDM authentication
- Supplier endpoints require supplier JWT token

---

#### 2. `supplier_item_access` - Item Access Control

Defines which items each supplier can view and which file types they can download.

```sql
CREATE TABLE supplier_item_access (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    supplier_id     UUID NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
    item_id         UUID NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    file_types      TEXT[] NOT NULL DEFAULT '{}',   -- Allowed file extensions
    notes           TEXT,
    granted_at      TIMESTAMPTZ DEFAULT NOW(),
    granted_by      UUID REFERENCES users(id),      -- Admin who granted access

    CONSTRAINT unique_supplier_item_access UNIQUE (supplier_id, item_id)
);

CREATE INDEX idx_supplier_item_access_supplier ON supplier_item_access(supplier_id);
CREATE INDEX idx_supplier_item_access_item ON supplier_item_access(item_id);
```

**Key Fields:**

- `supplier_id` - Which supplier has access
- `item_id` - Which item they can view
- `file_types` - Array of allowed file extensions (e.g., `['pdf', 'step', 'dxf']`)
- `notes` - Admin notes about why access was granted
- `granted_at` - When access was granted
- `granted_by` - Which admin user granted access (audit trail)

**File Type Restrictions:**

Common allowed types:
- `pdf` - Drawings (PDF exports)
- `step` - 3D models (neutral CAD format)
- `dxf` - 2D flat patterns (sheet metal)

Typically **restricted** types:
- `prt` - Creo source files
- `asm` - Creo assemblies
- `drw` - Creo drawings

**Access Control Logic:**

1. Supplier sees only items with entries in `supplier_item_access` for their `supplier_id`
2. For each item, supplier can only download files matching the `file_types` array
3. Attempting to download a restricted file type returns 403 Forbidden
4. If `file_types` is empty array, supplier can view item metadata but download no files

**Constraints:**
- Each supplier can only have one access entry per item (unique on `supplier_id, item_id`)
- Deleting supplier cascades and removes all access grants
- Deleting item cascades and removes all access grants

---

#### 3. `supplier_comments` - Two-Way Communication

Enables suppliers to ask questions about items and admins to respond.

```sql
CREATE TABLE supplier_comments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    supplier_id     UUID NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
    item_id         UUID NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    author_type     VARCHAR(20) NOT NULL,           -- 'supplier' | 'admin'
    content         TEXT NOT NULL,
    is_read         BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT valid_author_type CHECK (author_type IN ('supplier', 'admin'))
);

CREATE INDEX idx_supplier_comments_supplier ON supplier_comments(supplier_id);
CREATE INDEX idx_supplier_comments_item ON supplier_comments(item_id);
CREATE INDEX idx_supplier_comments_unread ON supplier_comments(is_read) WHERE is_read = false;
```

**Key Fields:**

- `supplier_id` - Which supplier the comment thread belongs to
- `item_id` - Which item the comment is about
- `author_type` - Either `'supplier'` (from supplier portal) or `'admin'` (from admin view)
- `content` - The comment text
- `is_read` - Tracks whether admin has seen supplier comments
- `created_at` - Comment timestamp

**Comment Flow:**

1. **Supplier posts question:**
   - Author type: `'supplier'`
   - `is_read`: `false` (admin hasn't seen it yet)
   - Shows in admin dashboard unread count badge

2. **Admin views comment:**
   - Backend marks comment as read (`is_read = true`)
   - Unread count badge decrements

3. **Admin replies:**
   - Author type: `'admin'`
   - `is_read`: N/A (admin doesn't need to see their own replies as unread)
   - Supplier sees reply in their item detail view

**Unread Count Badge:**

The admin dashboard shows a badge with count of unread supplier comments:
```sql
SELECT COUNT(*)
FROM supplier_comments
WHERE author_type = 'supplier' AND is_read = false
```

This provides quick visibility into pending supplier questions.

**Constraints:**
- Deleting supplier cascades and removes all their comments
- Deleting item cascades and removes all comments about that item
- `author_type` must be either `'supplier'` or `'admin'`

---

## Backend API

### Supplier Portal Routes (`backend/app/routes/supplier.py`)

All supplier routes require a valid supplier JWT token (except login).

#### Authentication

**POST `/api/supplier/login`**

Authenticate supplier and return JWT token.

Request:
```json
{
  "login_email": "portal@acme.com",
  "password": "supplier_password"
}
```

Response (200):
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "supplier": {
    "id": "uuid",
    "company_name": "Acme Manufacturing",
    "login_email": "portal@acme.com",
    "contact_name": "John Doe",
    "phone": "555-1234"
  }
}
```

Errors:
- 401: Invalid credentials or inactive account
- 500: Server error

**Security:**
- Password verified using bcrypt
- Only active suppliers can log in
- Token expires after 24 hours

**GET `/api/supplier/me`**

Get current supplier profile (requires JWT token).

Response (200):
```json
{
  "id": "uuid",
  "company_name": "Acme Manufacturing",
  "login_email": "portal@acme.com",
  "contact_name": "John Doe",
  "phone": "555-1234"
}
```

Errors:
- 401: Invalid or expired token

---

#### Item Access

**GET `/api/supplier/items`**

List all items the supplier has access to.

Response (200):
```json
{
  "items": [
    {
      "item_number": "csp0030",
      "name": "Frame Bracket",
      "revision": "B",
      "iteration": 3,
      "lifecycle_state": "Released",
      "material": "Steel 1018",
      "thickness": 0.25,
      "file_types": ["pdf", "step", "dxf"],
      "access_notes": "Outsourced part for Project Alpha"
    }
  ]
}
```

**Business Logic:**
1. Query `supplier_item_access` for current supplier
2. Join with `items` to get item metadata
3. Return only items with active access grants
4. Include `file_types` array to show what downloads are allowed

**GET `/api/supplier/items/{item_number}`**

Get detailed information about a specific item.

Response (200):
```json
{
  "item_number": "csp0030",
  "name": "Frame Bracket",
  "revision": "B",
  "iteration": 3,
  "lifecycle_state": "Released",
  "description": "L-shaped mounting bracket",
  "material": "Steel 1018",
  "thickness": 0.25,
  "mass": 1.234,
  "file_types": ["pdf", "step", "dxf"],
  "access_notes": "Outsourced part for Project Alpha",
  "files": [
    {
      "id": "uuid",
      "file_name": "csp0030_B.pdf",
      "file_type": "pdf",
      "file_size": 245678,
      "uploaded_at": "2026-07-15T10:30:00Z",
      "can_download": true
    },
    {
      "id": "uuid",
      "file_name": "csp0030_B.step",
      "file_type": "step",
      "file_size": 1234567,
      "uploaded_at": "2026-07-15T10:30:00Z",
      "can_download": true
    },
    {
      "id": "uuid",
      "file_name": "csp0030_B.prt",
      "file_type": "prt",
      "file_size": 987654,
      "uploaded_at": "2026-07-15T10:30:00Z",
      "can_download": false
    }
  ]
}
```

**Business Logic:**
1. Verify supplier has access to this item
2. Join with `files` table to list all files
3. Mark `can_download: true` only for files matching allowed `file_types`
4. Return 403 if supplier doesn't have access

Errors:
- 403: Supplier does not have access to this item
- 404: Item not found

---

#### File Downloads

**GET `/api/supplier/files/{file_id}/download`**

Download a file (with access control).

Response (200):
- Binary file stream with appropriate Content-Type header
- Content-Disposition: attachment; filename="..."

**Business Logic:**
1. Look up file by ID
2. Verify supplier has access to the item this file belongs to
3. Check if file type is in supplier's allowed `file_types` array
4. If allowed, stream file from Supabase Storage
5. If denied, return 403

Errors:
- 403: Supplier not allowed to download this file type
- 404: File not found
- 500: File storage error

**Security:**
- All downloads require valid supplier JWT token
- Access is checked on every download (not cached)
- File type restriction enforced server-side
- Audit trail: File downloads can be logged in future enhancement

---

#### Comments

**GET `/api/supplier/comments/{item_number}`**

Get all comments for an item (supplier's own comments + admin replies).

Response (200):
```json
{
  "comments": [
    {
      "id": "uuid",
      "author_type": "supplier",
      "content": "What material should we use for this bracket?",
      "created_at": "2026-07-20T14:30:00Z"
    },
    {
      "id": "uuid",
      "author_type": "admin",
      "content": "Please use Steel 1018 as specified in the drawing.",
      "created_at": "2026-07-20T15:45:00Z"
    }
  ]
}
```

**Business Logic:**
1. Verify supplier has access to this item
2. Return all comments for this `(supplier_id, item_id)` pair
3. Include both supplier questions and admin responses
4. Sorted by `created_at` ascending (chronological)

Errors:
- 403: Supplier does not have access to this item
- 404: Item not found

**POST `/api/supplier/comments/{item_number}`**

Post a new comment/question about an item.

Request:
```json
{
  "content": "What is the tolerance for the mounting holes?"
}
```

Response (201):
```json
{
  "id": "uuid",
  "author_type": "supplier",
  "content": "What is the tolerance for the mounting holes?",
  "is_read": false,
  "created_at": "2026-07-21T10:00:00Z"
}
```

**Business Logic:**
1. Verify supplier has access to this item
2. Create comment with `author_type='supplier'` and `is_read=false`
3. Return created comment
4. Admin will see this in unread count badge

Errors:
- 403: Supplier does not have access to this item
- 400: Empty content
- 404: Item not found

---

### Admin Management Routes (`backend/app/routes/admin_suppliers.py`)

All admin routes require PDM authentication (internal user token).

#### Supplier Account Management

**GET `/api/admin/suppliers`**

List all supplier accounts.

Response (200):
```json
{
  "suppliers": [
    {
      "id": "uuid",
      "company_name": "Acme Manufacturing",
      "login_email": "portal@acme.com",
      "is_active": true,
      "contact_name": "John Doe",
      "phone": "555-1234",
      "address": "123 Factory Lane",
      "notes": "Handles all sheet metal outsourcing",
      "created_at": "2026-07-01T08:00:00Z"
    }
  ]
}
```

**GET `/api/admin/suppliers/{supplier_id}`**

Get detailed supplier information including access grants and comments.

Response (200):
```json
{
  "id": "uuid",
  "company_name": "Acme Manufacturing",
  "login_email": "portal@acme.com",
  "is_active": true,
  "contact_name": "John Doe",
  "phone": "555-1234",
  "address": "123 Factory Lane",
  "notes": "Handles all sheet metal outsourcing",
  "created_at": "2026-07-01T08:00:00Z",
  "item_access": [
    {
      "id": "uuid",
      "item_number": "csp0030",
      "item_name": "Frame Bracket",
      "file_types": ["pdf", "step", "dxf"],
      "notes": "Project Alpha outsource",
      "granted_at": "2026-07-15T10:00:00Z"
    }
  ],
  "unread_comments_count": 3
}
```

**POST `/api/admin/suppliers`**

Create a new supplier account.

Request:
```json
{
  "company_name": "Acme Manufacturing",
  "login_email": "portal@acme.com",
  "password": "initial_password",
  "contact_name": "John Doe",
  "phone": "555-1234",
  "address": "123 Factory Lane",
  "notes": "Handles sheet metal parts"
}
```

Response (201):
```json
{
  "id": "uuid",
  "company_name": "Acme Manufacturing",
  "login_email": "portal@acme.com",
  "is_active": true,
  "created_at": "2026-07-22T10:00:00Z"
}
```

**Security:**
- Password is automatically hashed with bcrypt before storing
- Password hash is never returned in responses

**PATCH `/api/admin/suppliers/{supplier_id}`**

Update supplier account information.

Request (partial update):
```json
{
  "is_active": false,
  "notes": "Paused relationship due to quality issues"
}
```

Response (200):
```json
{
  "id": "uuid",
  "company_name": "Acme Manufacturing",
  "is_active": false,
  "notes": "Paused relationship due to quality issues",
  "updated_at": "2026-07-22T11:00:00Z"
}
```

**IMPORTANT:** To change password, include `password` field in request. It will be hashed before storing.

**DELETE `/api/admin/suppliers/{supplier_id}`**

Delete a supplier account (cascades to access grants and comments).

Response (204):
- No content

**Warning:** This permanently deletes the supplier and all associated access grants and comment history.

---

#### Item Access Management

**POST `/api/admin/suppliers/{supplier_id}/access`**

Grant supplier access to an item.

Request:
```json
{
  "item_number": "csp0030",
  "file_types": ["pdf", "step", "dxf"],
  "notes": "Outsourced for Project Alpha"
}
```

Response (201):
```json
{
  "id": "uuid",
  "item_number": "csp0030",
  "item_name": "Frame Bracket",
  "file_types": ["pdf", "step", "dxf"],
  "notes": "Outsourced for Project Alpha",
  "granted_at": "2026-07-22T10:00:00Z"
}
```

**Business Logic:**
1. Look up item by item_number
2. Create access grant linking supplier to item
3. Store allowed file types array
4. Track which admin granted access (for audit trail)

Errors:
- 404: Item not found
- 409: Access already granted (update instead)

**PATCH `/api/admin/suppliers/{supplier_id}/access/{access_id}`**

Update an existing access grant (change file types or notes).

Request:
```json
{
  "file_types": ["pdf", "step"],
  "notes": "Removed DXF access per security review"
}
```

Response (200):
```json
{
  "id": "uuid",
  "item_number": "csp0030",
  "file_types": ["pdf", "step"],
  "notes": "Removed DXF access per security review",
  "granted_at": "2026-07-22T10:00:00Z"
}
```

**DELETE `/api/admin/suppliers/{supplier_id}/access/{access_id}`**

Revoke supplier access to an item.

Response (204):
- No content

**Use Case:** Revoke access when project is complete or relationship ends.

---

#### Comment Management

**GET `/api/admin/comments/unread`**

Get count of unread supplier comments (for dashboard badge).

Response (200):
```json
{
  "unread_count": 5
}
```

**GET `/api/admin/suppliers/{supplier_id}/comments`**

Get all comments from a specific supplier (across all items).

Response (200):
```json
{
  "comments": [
    {
      "id": "uuid",
      "item_number": "csp0030",
      "item_name": "Frame Bracket",
      "author_type": "supplier",
      "content": "What material should we use?",
      "is_read": false,
      "created_at": "2026-07-20T14:30:00Z"
    }
  ]
}
```

**POST `/api/admin/comments/{comment_id}/mark-read`**

Mark a supplier comment as read.

Response (200):
```json
{
  "id": "uuid",
  "is_read": true
}
```

**Business Logic:**
- Automatically called when admin views supplier detail page
- Decrements unread count badge
- Only applies to comments with `author_type='supplier'`

**POST `/api/admin/suppliers/{supplier_id}/comments/{item_number}`**

Post an admin reply to a supplier question.

Request:
```json
{
  "content": "Please use Steel 1018 as specified in the drawing."
}
```

Response (201):
```json
{
  "id": "uuid",
  "author_type": "admin",
  "content": "Please use Steel 1018 as specified in the drawing.",
  "created_at": "2026-07-20T15:45:00Z"
}
```

**Business Logic:**
1. Create comment with `author_type='admin'`
2. Supplier will see this reply in their item detail view
3. No `is_read` flag needed (admins don't track their own replies)

---

## Frontend Implementation

### Supplier Portal Views

#### Login Page (`frontend/src/views/supplier/SupplierLoginView.vue`)

**Route:** `/supplier-login`

Simple login form with email and password fields.

**Features:**
- Form validation (required fields)
- Error display for invalid credentials
- Redirect to portal after successful login
- "Remember me" functionality via localStorage

**UI:**
```
┌─────────────────────────────────────┐
│   PDM Supplier Portal               │
│                                     │
│   Email:    [__________________]    │
│   Password: [__________________]    │
│                                     │
│        [ Log In ]                   │
│                                     │
│   Contact your PDM admin if you     │
│   need login credentials.           │
└─────────────────────────────────────┘
```

---

#### Supplier Portal Home (`frontend/src/views/supplier/SupplierPortalView.vue`)

**Route:** `/supplier/portal`

Grid view of all items the supplier has access to.

**Features:**
- Responsive card grid layout
- Item cards showing:
  - Item number (large, prominent)
  - Item name
  - Revision/iteration
  - Material and thickness
  - Allowed file types badges
- Click card to view item detail
- Logout button in header
- Company name displayed in header

**UI:**
```
┌──────────────────────────────────────────────────────────────┐
│  PDM Supplier Portal            Acme Manufacturing  [Logout] │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Your Items (12)                                            │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  CSP0030     │  │  WMA2012     │  │  BRK5510     │      │
│  │  Frame Bkt   │  │  Tube Mount  │  │  Base Plate  │      │
│  │  Rev B       │  │  Rev A       │  │  Rev C       │      │
│  │  Steel 1018  │  │  Aluminum    │  │  Steel       │      │
│  │  [PDF][STEP] │  │  [PDF][DXF]  │  │  [PDF]       │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

#### Supplier Item Detail (`frontend/src/views/supplier/SupplierItemView.vue`)

**Route:** `/supplier/item/:itemNumber`

Detailed view of a single item with files and comments.

**Features:**
- Item metadata display (name, revision, material, etc.)
- File list with download buttons
  - Files supplier can download shown in primary color
  - Restricted files shown grayed out with lock icon
- Comment thread with supplier questions and admin responses
- Form to post new questions
- Back button to return to portal

**UI:**
```
┌──────────────────────────────────────────────────────────────┐
│  ← Back to Portal                  Acme Manufacturing        │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  CSP0030 - Frame Bracket                                    │
│  Revision B, Iteration 3                                     │
│  Material: Steel 1018, Thickness: 0.25"                      │
│  Status: Released                                            │
│                                                              │
│  ─── Files ─────────────────────────────────────────────────│
│                                                              │
│  📄 csp0030_B.pdf          [Download]                       │
│  🧊 csp0030_B.step         [Download]                       │
│  📐 csp0030_B.dxf          [Download]                       │
│  🔒 csp0030_B.prt          (Restricted)                     │
│                                                              │
│  ─── Questions & Comments ──────────────────────────────────│
│                                                              │
│  💬 You (2 days ago):                                       │
│     What material should we use for this bracket?           │
│                                                              │
│  💬 Admin (2 days ago):                                     │
│     Please use Steel 1018 as specified in the drawing.      │
│                                                              │
│  ─── Ask a Question ────────────────────────────────────────│
│                                                              │
│  [____________________________________________]              │
│  [____________________________________________]              │
│                                         [Submit Question]    │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

### Admin Views

#### Supplier Management (`frontend/src/views/admin/AdminSuppliersView.vue`)

**Route:** `/admin/suppliers`

**Access:** Admin users only

Table of all supplier accounts with create/edit capabilities.

**Features:**
- Sortable/filterable table
- Active/inactive status badges
- Unread comments count badge per supplier
- Click row to view supplier detail
- "Create Supplier" button
- Toggle active/inactive status inline
- Delete supplier with confirmation

**UI:**
```
┌──────────────────────────────────────────────────────────────┐
│  Supplier Management                    [+ Create Supplier]  │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Company Name      Email              Status    Comments     │
│  ─────────────────────────────────────────────────────────  │
│  Acme Mfg          portal@acme.com    Active    (3 unread)  │
│  Beta Industries   portal@beta.com    Active    (0)         │
│  Gamma Works       portal@gamma.com   Inactive  (0)         │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

#### Supplier Detail (`frontend/src/views/admin/AdminSupplierDetailView.vue`)

**Route:** `/admin/suppliers/:id`

**Access:** Admin users only

Comprehensive supplier management page with three sections:
1. Account information
2. Item access grants
3. Comment threads

**Features:**

**Section 1: Account Info**
- Edit company name, email, contact info
- Change password
- Toggle active/inactive status
- Delete supplier account

**Section 2: Item Access**
- Table of granted items
- Add new item access:
  - Search for item by number
  - Select allowed file types (checkboxes for PDF, STEP, DXF, etc.)
  - Add notes about why access was granted
- Edit existing access (change file types or notes)
- Revoke access with confirmation

**Section 3: Comments**
- All comment threads for this supplier
- Grouped by item
- Unread comments highlighted
- Mark as read button
- Reply to supplier questions inline
- Auto-mark as read when viewing

**UI:**
```
┌──────────────────────────────────────────────────────────────┐
│  ← Back to Suppliers                                         │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Acme Manufacturing                              [Active] ▼  │
│                                                              │
│  ─── Account Information ───────────────────────────────────│
│                                                              │
│  Company Name: [Acme Manufacturing__________]               │
│  Login Email:  [portal@acme.com_____________]               │
│  Password:     [••••••••] [Change Password]                 │
│  Contact:      [John Doe____________________]               │
│  Phone:        [555-1234____________________]               │
│  Notes:        [Handles sheet metal parts___]               │
│                                                              │
│               [Save Changes]  [Delete Supplier]              │
│                                                              │
│  ─── Item Access (5 items) ─────────────────────────────────│
│                                                              │
│  [+ Grant Access to Item]                                   │
│                                                              │
│  Item Number  Name         File Types      Actions          │
│  ──────────────────────────────────────────────────────────│
│  CSP0030      Frame Bkt    PDF STEP DXF    [Edit] [Revoke] │
│  WMA2012      Tube Mount   PDF DXF         [Edit] [Revoke] │
│                                                              │
│  ─── Comments & Questions (3 unread) ───────────────────────│
│                                                              │
│  📌 CSP0030 - Frame Bracket                                 │
│     💬 Acme (2 days ago): [UNREAD]                          │
│        What material should we use for this bracket?        │
│                                                              │
│     Reply: [_____________________________________]          │
│            [Send Reply]                                     │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

### Dashboard Integration

The main admin dashboard displays an unread comments badge:

```
┌──────────────────────────────────────────────────────────────┐
│  PDM Dashboard                                               │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  [ Items ]  [ Projects ]  [ Suppliers (3) ]  [ Settings ]   │
│                                  └─ Unread comment badge    │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

Clicking the badge navigates to `/admin/suppliers` where unread counts are shown per supplier.

---

## Security Considerations

### Authentication & Authorization

**CRITICAL:** Suppliers use completely separate authentication from PDM users.
- Supplier JWT tokens stored in `localStorage.pdm_supplier_token`
- PDM user JWT tokens stored in `localStorage.pdm_user_token`
- No cross-contamination between auth systems
- Supplier routes check supplier token; admin routes check user token

### Access Control Enforcement

**Server-Side Validation (Required):**
Every API request validates:
1. Token is valid and not expired
2. Supplier has access to requested item
3. File type is in allowed list (for downloads)

**Client-Side UI (User Experience):**
Frontend hides/disables restricted actions, but **never relies on this for security**.

### File Type Restrictions

**Why restrict file types?**
- Source CAD files (`prt`, `asm`, `drw`) contain proprietary design data
- Suppliers only need neutral formats (`pdf`, `step`, `dxf`) for manufacturing
- Prevents unauthorized redistribution of full CAD models

**Common Configurations:**
- **Sheet metal vendor:** `['pdf', 'dxf']` - Drawings and flat patterns only
- **Machining vendor:** `['pdf', 'step']` - Drawings and 3D models
- **Assembly vendor:** `['pdf']` - Drawings only (no CAD)

### Password Security

**Hashing:**
- bcrypt with automatic salt generation (cost factor: 12)
- Passwords never stored in plaintext
- Password hashes never returned in API responses

**Password Changes:**
- Only admins can change supplier passwords
- Suppliers cannot self-reset (must contact admin)
- Consider implementing password expiration policy (future enhancement)

### Audit Trail

**Currently Logged:**
- Who granted item access (`granted_by` field)
- When access was granted (`granted_at` timestamp)
- All comments timestamped

**Future Enhancement:**
- Log all file downloads with timestamp
- Track login attempts (successful and failed)
- Export audit logs to CSV

---

## Common Workflows

### Admin: Creating a New Supplier

1. Navigate to `/admin/suppliers`
2. Click "Create Supplier"
3. Fill in form:
   - Company name (required, unique)
   - Login email (required, unique)
   - Initial password (required)
   - Contact info (optional)
   - Notes (optional)
4. Click "Create"
5. Share login credentials with supplier securely (e.g., phone call, encrypted email)

**IMPORTANT:** The initial password should be communicated securely and the supplier should be instructed to change it immediately (future enhancement: force password change on first login).

---

### Admin: Granting Item Access

1. Navigate to `/admin/suppliers/:id` (supplier detail)
2. Scroll to "Item Access" section
3. Click "Grant Access to Item"
4. Enter item number (auto-complete)
5. Select allowed file types:
   - ☑ PDF (drawings)
   - ☑ STEP (3D models)
   - ☑ DXF (flat patterns)
   - ☐ PRT (source CAD - usually not allowed)
6. Add notes (why access is needed)
7. Click "Grant Access"

**Result:** Supplier can now see this item in their portal and download allowed file types.

---

### Admin: Responding to Supplier Questions

**Option 1: Dashboard Badge**
1. Notice unread comments badge on dashboard
2. Click "Suppliers" with badge count
3. See unread counts per supplier
4. Click supplier row to view detail
5. Scroll to "Comments" section
6. See unread questions highlighted
7. Type reply in text box
8. Click "Send Reply"
9. Comment marked as read automatically

**Option 2: Direct Navigation**
1. Navigate to `/admin/suppliers`
2. See suppliers with unread comment counts
3. Click supplier with unread comments
4. Follow steps 5-9 above

---

### Supplier: Viewing Items and Downloading Files

1. Log in at `/supplier-login`
2. See grid of accessible items at `/supplier/portal`
3. Click an item card
4. View item detail at `/supplier/item/:itemNumber`
5. See list of files with download status:
   - Green download buttons for allowed files
   - Gray locked icons for restricted files
6. Click "Download" to download allowed files
7. File downloads directly to browser

---

### Supplier: Asking Questions

1. Navigate to item detail page
2. Scroll to "Questions & Comments" section
3. See previous questions and admin responses
4. Type new question in text box
5. Click "Submit Question"
6. Question appears in thread with timestamp
7. Admin receives notification via unread count badge
8. Wait for admin response (shown in same thread)

---

## Database Migrations

### Migration Files

**File:** `backend/migrations/044_create_supplier_portal_tables.sql`

```sql
-- Create suppliers table
CREATE TABLE suppliers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_name    VARCHAR(255) NOT NULL UNIQUE,
    login_email     VARCHAR(255) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    contact_name    VARCHAR(255),
    phone           VARCHAR(50),
    address         TEXT,
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_suppliers_login_email ON suppliers(login_email);
CREATE INDEX idx_suppliers_company_name ON suppliers(company_name);

-- Create supplier_item_access table
CREATE TABLE supplier_item_access (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    supplier_id     UUID NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
    item_id         UUID NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    file_types      TEXT[] NOT NULL DEFAULT '{}',
    notes           TEXT,
    granted_at      TIMESTAMPTZ DEFAULT NOW(),
    granted_by      UUID REFERENCES users(id),

    CONSTRAINT unique_supplier_item_access UNIQUE (supplier_id, item_id)
);

CREATE INDEX idx_supplier_item_access_supplier ON supplier_item_access(supplier_id);
CREATE INDEX idx_supplier_item_access_item ON supplier_item_access(item_id);

-- Create supplier_comments table
CREATE TABLE supplier_comments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    supplier_id     UUID NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
    item_id         UUID NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    author_type     VARCHAR(20) NOT NULL,
    content         TEXT NOT NULL,
    is_read         BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT valid_author_type CHECK (author_type IN ('supplier', 'admin'))
);

CREATE INDEX idx_supplier_comments_supplier ON supplier_comments(supplier_id);
CREATE INDEX idx_supplier_comments_item ON supplier_comments(item_id);
CREATE INDEX idx_supplier_comments_unread ON supplier_comments(is_read) WHERE is_read = false;
```

**Applied:** 2026-07-22

---

## Files Added/Modified

### Backend

**New Files:**
- `backend/app/models/supplier_schemas.py` - Pydantic models for supplier data
- `backend/app/services/supplier_auth.py` - JWT token creation and password hashing
- `backend/app/routes/supplier.py` - Supplier portal API endpoints
- `backend/app/routes/admin_suppliers.py` - Admin supplier management endpoints

**Modified Files:**
- `backend/app/main.py` - Added supplier route imports and registration
- `backend/requirements.txt` - Added PyJWT and bcrypt dependencies

### Frontend

**New Files:**
- `frontend/src/types/supplier.ts` - TypeScript interfaces for supplier types
- `frontend/src/stores/supplierAuth.ts` - Pinia store for supplier authentication
- `frontend/src/views/supplier/SupplierLoginView.vue` - Supplier login page
- `frontend/src/views/supplier/SupplierPortalView.vue` - Supplier items grid
- `frontend/src/views/supplier/SupplierItemView.vue` - Supplier item detail
- `frontend/src/views/admin/AdminSuppliersView.vue` - Admin supplier management
- `frontend/src/views/admin/AdminSupplierDetailView.vue` - Admin supplier detail

**Modified Files:**
- `frontend/src/router/index.ts` - Added supplier and admin routes
- `frontend/src/views/DashboardView.vue` - Added supplier unread comments badge

### Database

**New Tables:**
- `suppliers` - Supplier account management
- `supplier_item_access` - Item access control
- `supplier_comments` - Two-way communication

---

## Configuration

### Environment Variables

**Backend (`backend/.env`):**

```bash
# Supplier JWT Configuration
SUPPLIER_JWT_SECRET=your-secure-random-secret-here
SUPPLIER_JWT_EXPIRATION_HOURS=24
SUPPLIER_BCRYPT_ROUNDS=12
```

**Security Notes:**
- `SUPPLIER_JWT_SECRET` should be a strong random string (minimum 32 characters)
- Never commit secrets to version control
- Use different secrets for development and production
- Rotate secrets periodically

### Frontend Router Guards

Supplier routes require supplier authentication:
```typescript
{
  path: '/supplier/portal',
  name: 'SupplierPortal',
  component: () => import('@/views/supplier/SupplierPortalView.vue'),
  meta: { requiresSupplierAuth: true }
}
```

Admin routes require PDM authentication with admin role:
```typescript
{
  path: '/admin/suppliers',
  name: 'AdminSuppliers',
  component: () => import('@/views/admin/AdminSuppliersView.vue'),
  meta: { requiresAuth: true, requiresAdmin: true }
}
```

---

## Testing

### Manual Test Scenarios

**Supplier Authentication:**
- ✓ Log in with valid credentials
- ✓ Reject invalid password
- ✓ Reject inactive supplier
- ✓ Token persists in localStorage
- ✓ Token expires after 24 hours
- ✓ Logout clears token

**Item Access Control:**
- ✓ Supplier sees only granted items
- ✓ Supplier cannot access non-granted items (403)
- ✓ Supplier sees correct file type restrictions
- ✓ Download allowed files succeeds
- ✓ Download restricted files fails (403)

**Comments:**
- ✓ Supplier can post questions
- ✓ Admin sees unread count badge
- ✓ Admin can reply to questions
- ✓ Supplier sees admin replies
- ✓ Comments persist across sessions

**Admin Management:**
- ✓ Create new supplier
- ✓ Edit supplier info
- ✓ Change supplier password
- ✓ Toggle active/inactive status
- ✓ Delete supplier (cascades to access and comments)
- ✓ Grant item access
- ✓ Edit access (change file types)
- ✓ Revoke access

---

## Future Enhancements

### Priority 1 (Near-term)

**Download Audit Logging:**
Track all file downloads with:
- Which supplier
- Which file
- When downloaded
- IP address (optional)

**Purpose:** Security audit trail, usage analytics

**Password Management:**
- Force password change on first login
- Password expiration policy (e.g., 90 days)
- Self-service password reset (email link)

**Notifications:**
- Email admin when supplier posts question
- Email supplier when admin replies
- Weekly digest of unread comments

### Priority 2 (Medium-term)

**Bulk Access Grants:**
- Grant access to all items in a project at once
- Template access patterns (e.g., "Sheet Metal Vendor" = PDF + DXF)

**Advanced File Controls:**
- Revision-specific access (allow only Rev A, not Rev B)
- Expiring access (revoke after project completion)
- Download limits (max 10 downloads per file)

**Reporting:**
- Export access grant history
- Export comment threads to PDF
- Supplier activity dashboard (which suppliers are active)

### Priority 3 (Long-term)

**Multi-Supplier Collaboration:**
- Allow suppliers to see parts from other suppliers (read-only)
- Shared comment threads (supplier A sees supplier B's questions)

**Advanced Authentication:**
- Two-factor authentication (TOTP)
- SSO integration (SAML, OAuth)
- IP whitelisting

**Mobile App:**
- Native iOS/Android app for suppliers
- Push notifications for admin replies
- QR code scanning for quick item lookup

---

## Troubleshooting

### Supplier Cannot Log In

**Symptoms:** "Invalid credentials" error

**Checklist:**
1. Verify supplier account exists in `suppliers` table
2. Check `is_active` is `true`
3. Verify password was hashed correctly (bcrypt format)
4. Check login email is correct (case-sensitive)
5. Test password hash verification manually

**Common Causes:**
- Supplier marked inactive
- Password not hashed (stored as plaintext by mistake)
- Email typo

---

### Supplier Cannot See Items

**Symptoms:** Empty portal, no items listed

**Checklist:**
1. Verify supplier is logged in (token in localStorage)
2. Check `supplier_item_access` table for this supplier
3. Verify items referenced in access grants still exist
4. Check item lifecycle state (Released items preferred)

**Common Causes:**
- No access grants created yet
- Items were deleted
- Database query error

---

### Supplier Cannot Download Files

**Symptoms:** Download button grayed out or 403 error

**Checklist:**
1. Verify file type is in `file_types` array for this access grant
2. Check file exists in Supabase Storage
3. Verify file has correct `file_type` metadata
4. Check backend logs for storage errors

**Common Causes:**
- File type not in allowed list (e.g., trying to download PRT when only PDF allowed)
- File was deleted from storage
- Storage permissions issue

---

### Unread Comments Not Showing

**Symptoms:** Badge shows 0 but supplier posted questions

**Checklist:**
1. Verify comments have `author_type='supplier'`
2. Check `is_read=false`
3. Refresh dashboard to update badge
4. Check backend query for unread count

**Common Causes:**
- Comments marked as read accidentally
- Author type set incorrectly
- Frontend cache not refreshed

---

### Admin Cannot Create Supplier

**Symptoms:** Create supplier fails with error

**Checklist:**
1. Check for duplicate company_name
2. Check for duplicate login_email
3. Verify password meets minimum requirements
4. Check admin user has permission

**Common Causes:**
- Unique constraint violation (company name or email already exists)
- Empty required fields
- Database connection issue

---

## Related Documentation

- **03-DATABASE-SCHEMA.md** - Main database schema (add supplier tables to this doc)
- **04-SERVICES-REFERENCE.md** - Backend API configuration
- **26-SECURITY-HARDENING.md** - Security best practices
- **02-PDM-COMPLETE-OVERVIEW.md** - System overview (mention supplier portal)

---

## Glossary

**Supplier Portal:** Web interface for external vendors to access approved files and communicate with PDM admin.

**File Type Restriction:** Access control that limits which file formats a supplier can download (e.g., PDF and STEP only, no source CAD).

**Access Grant:** Permission entry linking a supplier to an item with allowed file types.

**Unread Count Badge:** UI indicator showing how many supplier comments await admin response.

**Cascading Delete:** When a supplier is deleted, all related access grants and comments are automatically deleted.

**bcrypt:** Cryptographic hashing algorithm for secure password storage.

**JWT (JSON Web Token):** Authentication token format used for supplier sessions.

---

**Document Status:** Complete
**Last Updated:** 2026-07-22
**Version:** v3.9.6
