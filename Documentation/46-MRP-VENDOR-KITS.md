# MRP Vendor Kits Management

## Overview

The MRP Vendor Kits feature provides a dedicated UI for managing vendor-supplied kits/bundles at the project level. This feature extends the existing kit pricing system (see `37-KIT-BUNDLE-PRICING.md`) with a more detailed kit item tracking interface, allowing project managers to track individual parts within kits, their quantities, and unit prices.

**Use Case:** A vendor quotes a "Precision Tube Laser Bundle" for $2,400 containing 18 pre-cut tube parts. The Vendor Kits view allows you to:
1. Create the kit definition (kit number, name, vendor, total price)
2. Add individual parts to the kit with quantities and unit prices
3. Compare kit price vs calculated item-level costs
4. Toggle whether to use the kit pricing or fall back to individual part sourcing

**Version:** v3.9.11 (2026-08-11)
**Route:** `/mrp/kits`
**Component:** `frontend/src/views/MrpKitsView.vue`

---

## Architecture

### Database Tables

This feature uses a **NEW data model** distinct from the existing `project_item_source` approach documented in `37-KIT-BUNDLE-PRICING.md`.

#### 1. `project_kits` (Existing)

Stores kit/bundle definitions. Schema already exists from the original kit pricing feature.

```sql
CREATE TABLE project_kits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES mrp_projects(id) ON DELETE CASCADE,
    kit_number VARCHAR(50) NOT NULL,           -- e.g., "KIT-001"
    kit_name VARCHAR(255) NOT NULL,            -- e.g., "Tube Bundle"
    vendor VARCHAR(255),                       -- Vendor/supplier name
    price DECIMAL(12, 2) NOT NULL DEFAULT 0,   -- Total kit price
    use_kit BOOLEAN NOT NULL DEFAULT true,     -- Toggle: use kit pricing?
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT unique_kit_number_per_project UNIQUE (project_id, kit_number)
);
```

**Key Fields:**
- `use_kit` - When `true`, kit is "active" and parts use kit pricing. When `false`, kit is disabled and parts fall back to individual pricing.
- `price` - Vendor quoted price for the entire kit
- `notes` - Quote number, lead time, special instructions

---

#### 2. `kit_items` (NEW - Not Yet Implemented)

**IMPORTANT:** This table does not exist in the database yet. The frontend expects this table but the migration has not been created.

**Expected Schema:**

```sql
CREATE TABLE kit_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kit_id UUID NOT NULL REFERENCES project_kits(id) ON DELETE CASCADE,
    item_id UUID NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    quantity INTEGER NOT NULL DEFAULT 1,
    unit_price DECIMAL(12, 2),                 -- Unit price per item (optional)
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Each item can only appear once per kit
    CONSTRAINT unique_item_per_kit UNIQUE (kit_id, item_id)
);

-- Indexes
CREATE INDEX idx_kit_items_kit_id ON kit_items(kit_id);
CREATE INDEX idx_kit_items_item_id ON kit_items(item_id);
```

**Key Fields:**
- `quantity` - How many of this item are in the kit
- `unit_price` - Optional unit price for cost tracking and comparison
- `notes` - Item-specific notes (e.g., "Vendor substituted 2" tube for 1.75"")

**RLS Policies:**

```sql
ALTER TABLE kit_items ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow all for authenticated users" ON kit_items
    FOR ALL USING (auth.role() = 'authenticated');
```

---

### Relationship to Existing Kit System

This new system (via `kit_items`) is **parallel to** the existing `project_item_source` table:

| Feature | Old System (Doc 37) | New System (This Doc) |
|---------|---------------------|----------------------|
| **Table** | `project_item_source` | `kit_items` |
| **Purpose** | Mark parts as "make" or "kit" for cost calculation | Track kit contents with quantities and unit prices |
| **UI** | Kit Management Slideout on MRP Dashboard | Dedicated `/mrp/kits` view |
| **Data Model** | Source type toggle (make/kit) | Item list with qty + price |
| **Pricing** | Kit total only | Kit total + individual unit prices |
| **Use Case** | Simple "buy kit or make in-house" decision | Detailed kit composition tracking |

**IMPORTANT:** The backend API (`backend/app/routes/kits.py`) currently uses `project_item_source`. The new UI (`MrpKitsView.vue`) expects `kit_items`. These systems need to be reconciled.

**Migration Strategy (Recommended):**
1. Create `kit_items` table migration
2. Update backend API to support both tables (or migrate to `kit_items` only)
3. Optionally migrate existing `project_item_source` data to `kit_items` format
4. Update cost calculation to use `kit_items` instead of `project_item_source`

---

## Frontend UI

### Access

**Route:** `/mrp/kits`
**Navigation:** MRP Dashboard → "Vendor Kits" button (purple dot indicator in top navigation)

**Component:** `frontend/src/views/MrpKitsView.vue` (1055 lines)

---

### Main Layout

The UI uses a two-column layout:

```
┌────────────────────────────────────────────────────────────────┐
│ Kit Management                     [Project Dropdown] [+ New Kit] [← Dashboard] │
├───────────────┬────────────────────────────────────────────────┤
│ VENDOR KITS   │ KIT-001 - Tube Bundle                         │
│               │ Vendor: Precision Tube Laser                  │
│ ┌───────────┐ │ Kit Price: $2,400.00  Calc Total: $2,385.50  │
│ │ KIT-001   │ │                                 [+ Add Parts] │
│ │ ACTIVE    │ │ ┌────────────────────────────────────────────┐ │
│ │ Tube      │ │ │ Part #    | Desc | Mat | Th | Qty | $ | ⌖ │ │
│ │ Bundle    │ │ │ csp00010  | Tube | CS  | -  | 2   | 15 | ⌖ │ │
│ │           │ │ │ csp00020  | Tube | CS  | -  | 2   | 18 | ⌖ │ │
│ │ 18 parts  │ │ └────────────────────────────────────────────┘ │
│ │ 36 pcs    │ │                                               │
│ │ $2,400.00 │ │                                               │
│ │           │ │                                               │
│ │ ✎ ✓ ✕    │ │                                               │
│ └───────────┘ │                                               │
│               │                                               │
│ ┌───────────┐ │                                               │
│ │ KIT-002   │ │                                               │
│ │ Frame Asm │ │                                               │
│ └───────────┘ │                                               │
└───────────────┴────────────────────────────────────────────────┘
```

---

### Features

#### 1. Project Selection

**Location:** Top header, dropdown selector

**Behavior:**
- Shows all MRP projects (`mrp_projects` table)
- Format: `{project_code} - {description}`
- Example: `WM_0513 - Water Monitor Prototype`
- Changing project reloads kit list for that project

---

#### 2. Kit List (Left Panel)

**Displays:**
- Kit number (e.g., `KIT-001`)
- Kit name (e.g., `Tube Bundle`)
- Vendor name
- Part count (e.g., `18 parts`)
- Total pieces (sum of all item quantities, e.g., `36 pcs`)
- Kit price (e.g., `$2,400.00`)
- Active badge (green `ACTIVE` badge if `use_kit = true`)

**Interactions:**
- Click a kit card to select and view details in right panel
- Selected kit has blue border
- Active kit has blue background (`#1e3a5f`)

**Actions (Bottom of Each Card):**
- **Edit (✎)** - Opens edit kit modal
- **Set Active (✓)** - Sets `use_kit = true` and disables all other kits (only one active kit per project)
- **Delete (✕)** - Deletes kit and all kit items (confirmation required)

**Empty State:**
```
No kits defined. Create one to get started.
```

---

#### 3. Kit Details (Right Panel)

**Header:**
- Kit number and name (e.g., `KIT-001 - Tube Bundle`)
- Vendor name
- Kit price (vendor quote)
- Calculated total (sum of `quantity × unit_price` for all kit items)
- Notes section (if notes exist)

**Actions:**
- **Add Parts** button - Opens part selection modal

**Parts Table:**

| Column | Description | Editable |
|--------|-------------|----------|
| Part Number | Item number (e.g., `csp00010`) | No |
| Description | Item description/name | No |
| Material | Material code (e.g., `CS`, `AL`) | No |
| Thickness | Sheet metal thickness (if applicable) | No |
| Qty | Quantity of this part in the kit | Yes (inline edit) |
| Unit Price | Price per unit (optional) | Yes (inline edit) |
| Line Total | `qty × unit_price` | Calculated |
| Actions | Remove button (✕) | - |

**Footer:**
- **Total:** Sum of all line totals

**Inline Editing:**
- Quantity: Click number, type new value, blur to save
- Unit Price: Click price, type new value, blur to save
- Changes save immediately to `kit_items` table

**Remove Item:**
- Click ✕ button
- Confirmation: `Remove {item_number} from this kit?`
- Deletes row from `kit_items`

**Empty State:**
```
No parts in this kit
```

---

#### 4. New/Edit Kit Modal

**Triggered by:**
- "+ New Kit" button (header)
- Edit (✎) button on kit card

**Form Fields:**
- **Kit Number** (required) - Text input, placeholder: `KIT-001`
- **Kit Name** (required) - Text input, placeholder: `PTL Tube Kit`
- **Vendor** (optional) - Text input, placeholder: `Precision Tube Laser`
- **Kit Price** (required) - Number input, step: `0.01`, placeholder: `0.00`
- **Notes** (optional) - Textarea, 4 rows, placeholder: `Quote number, lead time, etc.`

**Actions:**
- **Cancel** - Closes modal without saving
- **Save** - Creates/updates kit in `project_kits` table

**Validation:**
- Kit number and kit name are required
- Price defaults to `0.00`
- `use_kit` defaults to `false` (kit starts disabled)

---

#### 5. Add Parts Modal

**Triggered by:** "+ Add Parts" button in kit details panel

**Title:** `Add Parts to {kit_number}`

**Content:**
- Shows all parts from `mrp_project_parts` that are NOT already in this kit
- Format: Selectable list with checkboxes

**Part Row Display:**
- Checkbox (select/deselect)
- Part number (monospace font)
- Part name
- Material
- Quantity input (appears when selected)
- Unit price input (appears when selected)

**Behavior:**
- Click row to toggle selection
- When selected, row highlights and shows qty/price inputs
- Default quantity: `1`
- Default unit price: blank (optional)

**Actions:**
- **Cancel** - Closes modal
- **Add {N} Part(s)** - Inserts selected parts into `kit_items` table with quantities and prices

**Empty State:**
```
All project parts are already in this kit
```

---

#### 6. Use Kit Toggle

**Location:** Kit card actions (checkmark icon)

**States:**
- **Active (✓ icon, green)** - `use_kit = true`
- **Inactive (○ icon, gray)** - `use_kit = false`

**Behavior:**
- Click to toggle
- When setting a kit to active, all other kits for the project are automatically set to inactive
  - SQL: `UPDATE project_kits SET use_kit = false WHERE project_id = ?`
  - Then: `UPDATE project_kits SET use_kit = true WHERE id = ?`
- Only one kit can be active per project

**Impact:**
- Active kits contribute to project cost estimate (kit price replaces individual part costs)
- Inactive kits are ignored in cost calculations (parts fall back to individual routing costs)

---

### Theme and Styling

**Dark Theme (MRP Standard):**
- Background: `#020617` (page), `#0f172a` (panels)
- Card background: `#1e293b`
- Selected border: `#2563eb` (blue)
- Active badge: `#059669` (green)
- Text: `#e5e7eb` (primary), `#9ca3af` (secondary), `#6b7280` (tertiary)
- Price highlight: `#34d399` (green)

**Component Patterns:**
- Uses standard MRP button styles (`btn-primary`, `btn-secondary`)
- Modal overlays with dark backdrop (`rgba(0, 0, 0, 0.7)`)
- Inline editable inputs with dark styling
- Hover states on interactive elements

---

## Backend API (Expected)

The Vue component expects these API endpoints. **Not all are implemented yet** due to the missing `kit_items` table.

### Kit CRUD

#### List Kits

```
GET /api/mrp/projects/{project_id}/kits
```

**Expected Response:**

```json
[
  {
    "id": "uuid",
    "project_id": "uuid",
    "kit_number": "KIT-001",
    "kit_name": "Tube Bundle",
    "vendor": "Precision Tube Laser",
    "price": 2400.00,
    "use_kit": true,
    "notes": "Quote #12345",
    "created_at": "2026-08-01T10:00:00Z",
    "part_count": 18,      // Count from kit_items
    "total_pieces": 36     // Sum of kit_items.quantity
  }
]
```

**Queries:**
```sql
-- Get kits with part counts
SELECT
    pk.*,
    COUNT(ki.id) AS part_count,
    SUM(ki.quantity) AS total_pieces
FROM project_kits pk
LEFT JOIN kit_items ki ON ki.kit_id = pk.id
WHERE pk.project_id = ?
GROUP BY pk.id
ORDER BY pk.kit_number;
```

---

#### Create Kit

```
POST /api/mrp/projects/{project_id}/kits
```

**Request Body:**

```json
{
  "kit_number": "KIT-002",
  "kit_name": "Frame Assembly",
  "vendor": "ABC Welding",
  "price": 1500.00,
  "use_kit": false,
  "notes": "Lead time: 3 weeks"
}
```

**Response:** Created kit object

---

#### Update Kit

```
PATCH /api/mrp/projects/{project_id}/kits/{kit_id}
```

**Request Body:** (partial update)

```json
{
  "price": 1600.00,
  "notes": "Updated quote"
}
```

---

#### Delete Kit

```
DELETE /api/mrp/projects/{project_id}/kits/{kit_id}
```

**Behavior:**
- Deletes kit from `project_kits`
- Cascades to `kit_items` (all kit items are deleted)
- Confirmation required in UI

---

#### Set Active Kit

```
PATCH /api/mrp/projects/{project_id}/kits/{kit_id}
```

**Request Body:**

```json
{
  "use_kit": true
}
```

**Backend Logic:**
```sql
-- Disable all other kits
UPDATE project_kits SET use_kit = false WHERE project_id = ?;

-- Enable this kit
UPDATE project_kits SET use_kit = true WHERE id = ?;
```

---

### Kit Items

#### List Kit Items

```
GET /api/mrp/projects/{project_id}/kits/{kit_id}/items
```

**Query (used by Vue component):**

```sql
SELECT
    ki.*,
    i.item_number,
    i.description,
    i.material,
    i.thickness
FROM kit_items ki
JOIN items i ON ki.item_id = i.id
WHERE ki.kit_id = ?
ORDER BY i.item_number;
```

**Expected Response:**

```json
[
  {
    "id": "uuid",
    "kit_id": "uuid",
    "item_id": "uuid",
    "quantity": 2,
    "unit_price": 15.50,
    "notes": null,
    "item_number": "csp00010",
    "description": "TUBE 2X2X.125 28.43 LONG",
    "material": "CS",
    "thickness": null
  }
]
```

---

#### Add Items to Kit (Bulk)

```
POST /api/mrp/projects/{project_id}/kits/{kit_id}/items
```

**Request Body:**

```json
[
  {
    "item_id": "uuid",
    "quantity": 2,
    "unit_price": 15.50
  },
  {
    "item_id": "uuid",
    "quantity": 1,
    "unit_price": 22.00
  }
]
```

**Response:** Array of created `kit_items`

---

#### Update Kit Item

```
PATCH /api/mrp/projects/{project_id}/kits/{kit_id}/items/{item_id}
```

**Request Body:**

```json
{
  "quantity": 3,
  "unit_price": 16.00
}
```

---

#### Remove Item from Kit

```
DELETE /api/mrp/projects/{project_id}/kits/{kit_id}/items/{item_id}
```

**Behavior:** Deletes row from `kit_items`

---

### Available Items

#### List Items Not in Kit

```
GET /api/mrp/projects/{project_id}/available-items?exclude_kit={kit_id}
```

**Query:**

```sql
SELECT
    i.id,
    i.item_number,
    i.name,
    i.material,
    i.thickness
FROM mrp_project_parts mpp
JOIN items i ON mpp.item_id = i.id
WHERE mpp.project_id = ?
AND i.id NOT IN (
    SELECT item_id FROM kit_items WHERE kit_id = ?
)
ORDER BY i.item_number;
```

**Used by:** Add Parts modal to show parts that can be added to the kit

---

## Data Flow

### Loading Kits

```
User selects project
  ↓
GET /api/mrp/projects/{project_id}/kits
  ↓
Response includes:
  - Kit details
  - part_count (from kit_items count)
  - total_pieces (from SUM(kit_items.quantity))
  ↓
Display kit cards in left panel
```

---

### Selecting a Kit

```
User clicks kit card
  ↓
GET /api/mrp/projects/{project_id}/kits/{kit_id}/items
  (or use nested query from list endpoint)
  ↓
Response includes:
  - kit_items with joined item details
  - item_number, description, material, thickness
  ↓
Display parts table in right panel
  ↓
Calculate total: SUM(quantity × unit_price)
```

---

### Adding Parts to Kit

```
User clicks "+ Add Parts"
  ↓
GET /api/mrp/projects/{project_id}/available-items?exclude_kit={kit_id}
  ↓
Display modal with selectable parts
  ↓
User selects parts, enters qty/price
  ↓
Click "Add {N} Part(s)"
  ↓
POST /api/mrp/projects/{project_id}/kits/{kit_id}/items
Body: [{ item_id, quantity, unit_price }, ...]
  ↓
Reload kit items
```

---

### Inline Editing

```
User changes quantity in table
  ↓
onChange event
  ↓
PATCH /api/kit-items/{item_id}
Body: { quantity: newQty }
  ↓
Update local state
  ↓
Recalculate total
```

---

## Cost Calculation Integration

**IMPORTANT:** The cost estimate logic will need to be updated to use `kit_items` instead of `project_item_source`.

### Current Logic (Doc 37)

```sql
-- Check if item is in a kit
SELECT source_type, kit_id
FROM project_item_source
WHERE project_id = ? AND item_id = ?;

-- If source_type = 'kit' and kit.use_kit = true:
--   Skip individual cost, part is covered by kit price
-- Else:
--   Calculate routing cost
```

### Proposed Logic (This Feature)

```sql
-- Check if item is in an active kit
SELECT ki.kit_id
FROM kit_items ki
JOIN project_kits pk ON ki.kit_id = pk.id
WHERE ki.item_id = ? AND pk.project_id = ? AND pk.use_kit = true;

-- If found:
--   Skip individual cost, part is covered by kit price
-- Else:
--   Calculate routing cost
```

**Kit Total Cost:**

```sql
-- Sum all active kit prices
SELECT SUM(price) AS kit_cost
FROM project_kits
WHERE project_id = ? AND use_kit = true;
```

**Alternative (Item-Level Costing):**

If you want to use `kit_items.unit_price` for cost calculations:

```sql
-- Calculate kit cost from items
SELECT SUM(ki.quantity * COALESCE(ki.unit_price, 0)) AS kit_cost
FROM kit_items ki
JOIN project_kits pk ON ki.kit_id = pk.id
WHERE pk.project_id = ? AND pk.use_kit = true;
```

This allows comparing vendor quote (`pk.price`) vs calculated item total.

---

## Use Cases

### 1. Creating a New Vendor Kit

**Scenario:** Vendor quotes a tube laser kit for $2,400 containing 18 parts.

**Steps:**

1. Navigate to `/mrp/kits`
2. Select project from dropdown
3. Click "+ New Kit"
4. Enter:
   - Kit Number: `KIT-001`
   - Kit Name: `Precision Tube Laser Bundle`
   - Vendor: `Precision Tube Laser`
   - Price: `2400.00`
   - Notes: `Quote #PTL-2026-123, Lead time: 2 weeks`
5. Click "Save"
6. Kit appears in left panel (inactive by default)

---

### 2. Adding Parts to a Kit

**Scenario:** Add the 18 tube parts that are included in the vendor kit.

**Steps:**

1. Click the kit card (e.g., `KIT-001`)
2. Click "+ Add Parts" button
3. Modal shows all project parts not yet in this kit
4. Select parts (click row or checkbox)
5. For each selected part:
   - Enter quantity (e.g., `2` if vendor includes 2 of this part)
   - Enter unit price (optional, e.g., `15.50` per part)
6. Click "Add {N} Part(s)"
7. Parts appear in the kit details table

---

### 3. Editing Kit Item Quantities

**Scenario:** Vendor revised quote to include 3 of a part instead of 2.

**Steps:**

1. Select the kit
2. Find the part in the table
3. Click the quantity field
4. Type new quantity: `3`
5. Click outside the field (blur event)
6. Change saves automatically
7. Line total and kit total recalculate

---

### 4. Activating a Kit

**Scenario:** You've decided to purchase the vendor kit instead of making parts in-house.

**Steps:**

1. Click the checkmark (✓) button on the kit card
2. Kit badge changes to green "ACTIVE"
3. All other kits for this project are automatically deactivated
4. Project cost estimate now uses kit price instead of individual part routing costs

**Impact:**
- Parts in this kit are excluded from routing cost calculations
- Kit price is added to project total cost
- Build Book and cost reports reflect kit sourcing

---

### 5. Comparing Kit Price vs Item Total

**Scenario:** Verify vendor quote matches sum of individual item prices.

**Steps:**

1. Select the kit
2. Look at kit details header:
   - **Kit Price:** $2,400.00 (vendor quote)
   - **Calculated Total:** $2,385.50 (sum of item quantities × unit prices)
3. Difference: $14.50 (vendor markup or discount)

**Use:** Identify pricing discrepancies, negotiate better rates, or validate vendor quotes.

---

### 6. Removing a Part from a Kit

**Scenario:** Vendor removed a part from the bundle (no longer included).

**Steps:**

1. Select the kit
2. Find the part in the table
3. Click the ✕ button in the Actions column
4. Confirm: `Remove {item_number} from this kit?`
5. Part is deleted from the kit
6. Part count and total pieces update
7. Calculated total recalculates

---

### 7. Deactivating a Kit

**Scenario:** Vendor kit is out of stock; temporarily build parts in-house.

**Steps:**

1. Click the green checkmark (✓) on the active kit card
2. Toggle switches to inactive (gray ○)
3. "ACTIVE" badge disappears
4. Parts in this kit now fall back to individual routing costs
5. Project cost estimate recalculates using in-house costs

**To Reactivate:** Click the gray circle (○) to toggle back to active.

---

### 8. Deleting a Kit

**Scenario:** Project scope changed; kit no longer needed.

**Steps:**

1. Click the ✕ (delete) button on the kit card
2. Confirm: `Delete kit "KIT-001"? This will remove all part assignments.`
3. Kit is deleted from `project_kits`
4. All `kit_items` for this kit are deleted (CASCADE)
5. Parts return to default in-house sourcing

---

## Implementation Status

### Completed

- ✅ Frontend UI (`MrpKitsView.vue`) - Full CRUD interface
- ✅ Routing integration (`/mrp/kits` route)
- ✅ MRP Dashboard navigation button

### In Progress / Missing

- ⚠️ **Database Migration** - `kit_items` table does not exist yet
- ⚠️ **Backend API Routes** - Existing `/api/mrp/projects/{project_id}/kits` endpoints use `project_item_source` (Doc 37 system), not `kit_items`
- ⚠️ **Cost Calculation Updates** - Need to update `backend/app/services/cost_estimate.py` to support `kit_items`

### Required Work

1. **Create Migration: `kit_items` table**

   File: `backend/migrations/2026-08-11_kit_items.sql`

   ```sql
   CREATE TABLE kit_items (
       id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
       kit_id UUID NOT NULL REFERENCES project_kits(id) ON DELETE CASCADE,
       item_id UUID NOT NULL REFERENCES items(id) ON DELETE CASCADE,
       quantity INTEGER NOT NULL DEFAULT 1,
       unit_price DECIMAL(12, 2),
       notes TEXT,
       created_at TIMESTAMPTZ DEFAULT NOW(),

       CONSTRAINT unique_item_per_kit UNIQUE (kit_id, item_id)
   );

   CREATE INDEX idx_kit_items_kit_id ON kit_items(kit_id);
   CREATE INDEX idx_kit_items_item_id ON kit_items(item_id);

   ALTER TABLE kit_items ENABLE ROW LEVEL SECURITY;

   CREATE POLICY "Allow all for authenticated users" ON kit_items
       FOR ALL USING (auth.role() = 'authenticated');
   ```

2. **Update Backend API Routes**

   File: `backend/app/routes/kits.py`

   - Add endpoints for `kit_items` CRUD
   - Modify `GET /api/mrp/projects/{project_id}/kits` to return `part_count` and `total_pieces` from `kit_items`
   - Add `GET /api/mrp/projects/{project_id}/kits/{kit_id}/items`
   - Add `POST /api/mrp/projects/{project_id}/kits/{kit_id}/items` (bulk insert)
   - Add `PATCH /api/kit-items/{item_id}` (update qty/price)
   - Add `DELETE /api/kit-items/{item_id}`
   - Add `GET /api/mrp/projects/{project_id}/available-items?exclude_kit={kit_id}`

3. **Update Cost Calculation**

   File: `backend/app/services/cost_estimate.py`

   - Query `kit_items` instead of (or in addition to) `project_item_source`
   - Exclude parts found in active kits from individual cost calculations
   - Add kit price to project total

4. **Database Schema Documentation**

   File: `Documentation/03-DATABASE-SCHEMA.md`

   - Add `kit_items` table definition
   - Add relationship diagram: `project_kits 1--* kit_items`

5. **Reconcile Dual Kit Systems**

   **Decision Required:** Keep both systems or migrate to one?

   **Option A: Keep Both**
   - `project_item_source` → Simple "make vs kit" toggle (Doc 37 UI)
   - `kit_items` → Detailed kit composition (this UI)
   - Use case: Routing page uses `project_item_source`, Kits view uses `kit_items`

   **Option B: Migrate to `kit_items` Only**
   - Deprecate `project_item_source`
   - Migrate existing data to `kit_items`
   - Update all cost calculations to use `kit_items`
   - Remove Kit Management Slideout from MRP Dashboard (superseded by `/mrp/kits`)

---

## Related Documentation

- **37-KIT-BUNDLE-PRICING.md** - Original kit pricing feature using `project_item_source`
- **38-KIT-SOURCING-IN-BUILD-DOCS.md** - Kit display in Build Book and Design Book
- **39-KIT-SOURCING-STEP-EXPORT.md** - Exporting STEP files for kit orders
- **03-DATABASE-SCHEMA.md** - Database schema reference (needs `kit_items` table added)
- **04-SERVICES-REFERENCE.md** - Backend API reference (needs kit_items endpoints added)
- **20-COMMON-WORKFLOWS.md** - MRP workflows (add vendor kits workflow)

---

## Migration Plan

### Phase 1: Database Setup

1. Create `kit_items` migration
2. Run migration on dev environment
3. Test table creation and constraints
4. Verify RLS policies

### Phase 2: Backend API

1. Add kit_items CRUD endpoints
2. Update kits list endpoint to include counts from kit_items
3. Add available items endpoint
4. Test endpoints with Postman/curl

### Phase 3: Cost Integration

1. Update cost_estimate.py to query kit_items
2. Exclude kit items from individual cost calculations
3. Add unit tests for kit cost logic
4. Test with sample project data

### Phase 4: Frontend Testing

1. Test CRUD operations in `/mrp/kits`
2. Verify inline editing saves correctly
3. Test kit activation toggle
4. Verify cost totals calculate correctly

### Phase 5: Documentation

1. Update 03-DATABASE-SCHEMA.md
2. Update 04-SERVICES-REFERENCE.md
3. Update 20-COMMON-WORKFLOWS.md
4. Update 00-TABLE-OF-CONTENTS.md

---

## Design Decisions

### Why a Separate View Instead of a Modal?

The original kit feature (Doc 37) used a slideout modal on the MRP Dashboard. This new UI uses a dedicated full-page view.

**Reasons:**
- **More space** - Kit management with item lists needs more screen real estate
- **Better UX** - Dedicated view allows for richer interactions (inline editing, multi-column tables)
- **Separation of concerns** - Dashboard focuses on high-level project overview; kits view focuses on detailed kit composition
- **Future expansion** - Easier to add features like bulk import, kit templates, historical pricing

---

### Why Track Unit Prices?

The `unit_price` field in `kit_items` allows tracking individual item costs within a kit.

**Benefits:**
- **Vendor quote verification** - Compare vendor's total quote against sum of individual item prices
- **Cost transparency** - See which items contribute most to kit cost
- **Negotiation data** - Identify overpriced items to negotiate with vendor
- **Alternative sourcing** - If vendor price for one item is too high, source it separately

**Optional Field:**
- Unit price is optional (can be NULL)
- If not provided, calculated total will be zero (kit price is used instead)
- If provided, offers detailed cost breakdown

---

### Why Only One Active Kit Per Project?

The UI enforces only one active kit per project (activating a kit deactivates all others).

**Reasons:**
- **Simplifies cost calculation** - Only one kit price contributes to project total
- **Avoids double-counting** - Prevents parts from being counted in multiple kits
- **Matches real-world workflow** - Typically choose ONE vendor bundle, not multiple

**Future Enhancement:**
- If multiple active kits are needed, update backend to support it
- Cost calculation would sum all active kit prices
- UI would need to handle multi-kit activation (remove auto-deactivate logic)

---

### Why Separate from `project_item_source`?

The new `kit_items` table is separate from the existing `project_item_source` table (Doc 37).

**Reasons:**
- **Different data models** - `project_item_source` is a simple "make vs kit" toggle; `kit_items` tracks detailed kit composition
- **Different UIs** - Routing page uses simple toggle; Kits view uses detailed table
- **Non-breaking change** - Existing features continue to work while new feature is developed
- **Migration flexibility** - Can keep both systems or migrate to one later

**Tradeoff:**
- Increases complexity (two overlapping systems)
- Requires decision on which to use for cost calculations

**Recommendation:**
- Migrate to `kit_items` only (deprecate `project_item_source`)
- Provides richer data model for future enhancements
- Single source of truth for kit sourcing

---

## Testing Checklist

### Database

- [ ] `kit_items` table created with correct schema
- [ ] Foreign key constraints work (kit_id, item_id)
- [ ] Unique constraint prevents duplicate items in a kit
- [ ] CASCADE delete works (deleting kit deletes kit_items)
- [ ] RLS policies allow authenticated users to CRUD

### Backend API

- [ ] `GET /api/mrp/projects/{project_id}/kits` returns kits with part_count and total_pieces
- [ ] `POST /api/mrp/projects/{project_id}/kits` creates kit
- [ ] `PATCH /api/mrp/projects/{project_id}/kits/{kit_id}` updates kit
- [ ] `DELETE /api/mrp/projects/{project_id}/kits/{kit_id}` deletes kit and cascades to kit_items
- [ ] `GET /api/mrp/projects/{project_id}/kits/{kit_id}/items` returns kit items with item details
- [ ] `POST /api/mrp/projects/{project_id}/kits/{kit_id}/items` bulk inserts kit items
- [ ] `PATCH /api/kit-items/{item_id}` updates quantity/unit_price
- [ ] `DELETE /api/kit-items/{item_id}` removes item from kit
- [ ] `GET /api/mrp/projects/{project_id}/available-items?exclude_kit={kit_id}` returns items not in kit

### Frontend UI

- [ ] Project dropdown loads all MRP projects
- [ ] Selecting project loads kits for that project
- [ ] Kit cards display correct data (number, name, vendor, price, counts)
- [ ] Clicking kit card loads kit items in right panel
- [ ] Active badge shows for kits with `use_kit = true`
- [ ] "+ New Kit" opens modal with form
- [ ] Saving new kit creates kit and reloads list
- [ ] Edit button opens modal with pre-filled data
- [ ] Updating kit saves changes
- [ ] Delete button confirms and deletes kit
- [ ] "+ Add Parts" modal shows available items
- [ ] Selecting parts enables qty/price inputs
- [ ] Adding parts inserts kit_items and reloads table
- [ ] Inline editing quantity saves on blur
- [ ] Inline editing unit price saves on blur
- [ ] Removing item from kit confirms and deletes
- [ ] Calculated total matches sum of line totals
- [ ] Activating kit deactivates all other kits
- [ ] Deactivating kit removes active badge

### Cost Calculation

- [ ] Parts in active kits are excluded from individual cost calculations
- [ ] Kit price is added to project total cost
- [ ] Deactivating kit causes parts to fall back to routing costs
- [ ] Multiple projects with different kit sourcing calculate correctly
- [ ] Cost estimate API returns correct kit_cost category

---

## Future Enhancements

### 1. Kit Templates

**Concept:** Save common kit definitions as templates for reuse across projects.

**Tables:**
```sql
CREATE TABLE kit_templates (
    id UUID PRIMARY KEY,
    template_name VARCHAR(255),
    vendor VARCHAR(255),
    notes TEXT
);

CREATE TABLE kit_template_items (
    id UUID PRIMARY KEY,
    template_id UUID REFERENCES kit_templates(id),
    item_id UUID REFERENCES items(id),
    quantity INTEGER,
    notes TEXT
);
```

**UI:**
- "Save as Template" button on kit details
- "New Kit from Template" option in create kit modal
- Template library view for browsing and managing templates

---

### 2. Kit Price History

**Concept:** Track vendor price changes over time.

**Table:**
```sql
CREATE TABLE kit_price_history (
    id UUID PRIMARY KEY,
    kit_id UUID REFERENCES project_kits(id),
    price DECIMAL(12, 2),
    effective_date DATE,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**UI:**
- Price history chart on kit details
- "View Price History" button
- Alert when vendor raises price

---

### 3. Kit Lead Time Tracking

**Concept:** Track vendor lead times and order dates.

**Schema Updates:**
```sql
ALTER TABLE project_kits
ADD COLUMN lead_time_weeks INTEGER,
ADD COLUMN last_order_date DATE,
ADD COLUMN expected_delivery_date DATE;
```

**UI:**
- Lead time field in kit form
- Order date tracking
- Expected delivery calculation
- Alerts for late deliveries

---

### 4. Kit Revision Control

**Concept:** Track changes to kit composition over time.

**Use Case:** Vendor changes kit contents (adds/removes parts). Need to track what was ordered vs what was received.

**Implementation:**
- Add `revision` field to `project_kits`
- Create snapshot of `kit_items` when kit is ordered
- Compare received items against snapshot

---

### 5. Bulk Import from CSV

**Concept:** Import kit items from vendor-provided CSV files.

**UI:**
- "Import Items" button in kit details
- File upload modal
- CSV parsing and validation
- Preview before import

**CSV Format:**
```csv
part_number,quantity,unit_price,notes
csp00010,2,15.50,
csp00020,2,18.00,Upgraded to 2" tube
```

---

## Troubleshooting

### Issue: "Failed to create kit: relation 'kit_items' does not exist"

**Cause:** `kit_items` table migration has not been run.

**Solution:**
1. Create migration file `backend/migrations/2026-08-11_kit_items.sql` (see schema above)
2. Run migration on Supabase
3. Verify table exists: `SELECT * FROM kit_items LIMIT 1;`

---

### Issue: Kit items not loading in details panel

**Cause:** Backend API endpoint missing or using wrong table.

**Solution:**
1. Verify endpoint exists: `GET /api/mrp/projects/{project_id}/kits/{kit_id}/items`
2. Check backend code uses `kit_items` table (not `project_item_source`)
3. Check browser console for API errors

---

### Issue: Inline editing not saving

**Cause:** PATCH endpoint missing or incorrect.

**Solution:**
1. Verify endpoint: `PATCH /api/kit-items/{item_id}`
2. Check request payload includes `quantity` or `unit_price`
3. Check backend logs for errors
4. Verify RLS policies allow UPDATE on `kit_items`

---

### Issue: Adding parts shows "All project parts are already in this kit" when parts exist

**Cause:** Available items query incorrect.

**Solution:**
1. Verify query excludes items already in kit
2. Check `exclude_kit` parameter is passed to API
3. Verify `kit_items` has correct foreign keys

---

### Issue: Activating kit doesn't deactivate others

**Cause:** Backend toggle logic missing.

**Solution:**
1. Verify `setActiveKit()` function in Vue component
2. Backend should update ALL kits for project, setting `use_kit = false`
3. Then set target kit `use_kit = true`
4. Check SQL queries in backend route

---

### Issue: Cost estimate doesn't reflect kit pricing

**Cause:** Cost calculation not updated to use `kit_items`.

**Solution:**
1. Update `backend/app/services/cost_estimate.py`
2. Query `kit_items` to find parts in active kits
3. Exclude those parts from individual cost calculations
4. Add kit price to total

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| v1.0 | 2026-08-11 | Initial documentation. Frontend UI complete, backend pending. |

---

**Last Updated:** 2026-08-11
**Status:** In Development (Frontend complete, backend/database pending)
**Author:** Claude Code (documentation agent)
