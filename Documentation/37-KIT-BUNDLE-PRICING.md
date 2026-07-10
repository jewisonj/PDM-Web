# Kit and Bundle Pricing System

## Overview

The Kit/Bundle Pricing feature enables tracking vendor-supplied bundles of parts as an alternative to in-house manufacturing. This feature allows project managers to evaluate the cost savings (or penalties) of purchasing pre-fabricated kits versus building components in-house.

**Use Case:** A vendor offers a "Tube Bundle" for $850 that includes 12 pre-cut, pre-welded parts. Instead of routing each part through in-house operations (cutting, welding, finishing), you can mark those parts as belonging to the kit and compare the total in-house cost against the kit price.

**Version:** Added in v3.9.3 (2026-07-09)

---

## Architecture

### Two Database Tables

#### 1. `project_kits` - Vendor Bundle Definitions

Stores information about kits purchased for a specific MRP project.

```sql
CREATE TABLE project_kits (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id  UUID NOT NULL REFERENCES mrp_projects(id) ON DELETE CASCADE,
    kit_number  VARCHAR(50) NOT NULL,           -- e.g., "KIT-001"
    kit_name    VARCHAR(255) NOT NULL,          -- e.g., "Tube Bundle"
    vendor      VARCHAR(255),                   -- Vendor/supplier name
    price       DECIMAL(12, 2) NOT NULL DEFAULT 0,  -- Total kit price
    use_kit     BOOLEAN NOT NULL DEFAULT true,  -- Toggle: use kit pricing?
    notes       TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT unique_kit_number_per_project UNIQUE (project_id, kit_number)
);
```

**Key Fields:**

- `kit_number` - User-defined identifier (e.g., `KIT-001`, `VENDOR-BUNDLE-A`)
- `kit_name` - Human-readable name (e.g., "Tube Bundle", "Pre-Welded Frame Kit")
- `vendor` - Optional vendor/supplier name
- `price` - Total price for the entire kit (all parts included)
- `use_kit` - **Toggle switch**: When `true`, kit pricing is used; when `false`, parts fall back to in-house routing costs

**RLS Policies:** Authenticated users can read and modify all kits (simple small-team policy).

#### 2. `project_item_source` - Per-Part Sourcing Decisions

Tracks how each part is sourced within a project.

```sql
CREATE TABLE project_item_source (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id  UUID NOT NULL REFERENCES mrp_projects(id) ON DELETE CASCADE,
    item_id     UUID NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    source_type VARCHAR(20) NOT NULL DEFAULT 'make',  -- 'make' | 'kit'
    kit_id      UUID REFERENCES project_kits(id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT unique_item_source_per_project UNIQUE (project_id, item_id),
    CONSTRAINT valid_source_type CHECK (source_type IN ('make', 'kit')),
    CONSTRAINT kit_id_required_for_kit_source CHECK (
        (source_type = 'kit' AND kit_id IS NOT NULL) OR
        (source_type = 'make' AND kit_id IS NULL)
    )
);
```

**Key Fields:**

- `source_type` - Either `'make'` (use in-house routing) or `'kit'` (part of a vendor bundle)
- `kit_id` - References the kit this part belongs to (only when `source_type='kit'`)

**Default Behavior:** If a part has no entry in `project_item_source`, it defaults to `'make'`.

**Constraints:**
- Each part can only have one source per project (unique on `project_id, item_id`)
- If `source_type='kit'`, `kit_id` must be set
- If `source_type='make'`, `kit_id` must be `NULL`

---

## Backend API

### Kit CRUD Endpoints

All kit endpoints are under `/api/mrp/projects/{project_id}/kits`.

#### List Kits with Cost Comparison

```
GET /api/mrp/projects/{project_id}/kits
```

**Returns:** Array of kits with enriched cost data.

**Response:**

```json
[
  {
    "id": "uuid-here",
    "project_id": "uuid-here",
    "kit_number": "KIT-001",
    "kit_name": "Tube Bundle",
    "vendor": "ABC Fabrication",
    "price": 850.00,
    "use_kit": true,
    "notes": "Pre-welded bundle, includes 12 parts",
    "part_count": 12,
    "inhouse_cost": 1240.50,
    "inhouse_labor": 940.50,
    "inhouse_material": 300.00,
    "savings": 390.50,
    "savings_percent": 31.5
  }
]
```

**Cost Calculation Logic:**

1. Fetch all parts assigned to each kit
2. For each part, calculate in-house cost:
   - **Labor cost** - Sum of routing step costs (hourly rate × est_time_min / 60)
   - **Material cost** - Routing materials (sheet metal weight × $/lb, or tube length × $/ft)
   - **Outsourced cost** - Cost overrides for outsourced operations
3. Multiply by part quantity from `mrp_project_parts`
4. Sum across all parts in the kit
5. Compare against kit price:
   - `savings = inhouse_cost - kit_price`
   - `savings_percent = (savings / inhouse_cost) × 100`

**Positive savings** = Kit is cheaper than in-house
**Negative savings** = Kit is more expensive than in-house

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
  "vendor": "XYZ Welding",
  "price": 1200.00,
  "use_kit": true,
  "notes": "Includes powder coating"
}
```

---

#### Get Single Kit with Parts List

```
GET /api/mrp/projects/{project_id}/kits/{kit_id}
```

**Response:**

```json
{
  "id": "uuid-here",
  "kit_number": "KIT-001",
  "kit_name": "Tube Bundle",
  "vendor": "ABC Fabrication",
  "price": 850.00,
  "use_kit": true,
  "notes": "Pre-welded bundle",
  "parts": [
    {
      "item_id": "uuid-here",
      "item_number": "wsp20030",
      "name": "Tube, Main Frame"
    },
    {
      "item_id": "uuid-here",
      "item_number": "wsp20031",
      "name": "Tube, Cross Member"
    }
  ]
}
```

---

#### Update Kit

```
PATCH /api/mrp/projects/{project_id}/kits/{kit_id}
```

**Request Body:** (only include fields to update)

```json
{
  "price": 900.00,
  "use_kit": false
}
```

---

#### Delete Kit

```
DELETE /api/mrp/projects/{project_id}/kits/{kit_id}
```

**Behavior:**
- Deletes the kit from `project_kits`
- All parts assigned to this kit are automatically reverted to `source_type='make'`
- Confirmation prompt in UI warns that parts will revert to in-house routing

---

### Item Source Endpoints

#### List Item Sources

```
GET /api/mrp/projects/{project_id}/item-sources
```

**Returns:** Map of `item_id -> source info` for all parts with explicit source assignments.

**Response:**

```json
{
  "uuid-of-part-1": {
    "source_type": "kit",
    "kit_id": "uuid-of-kit",
    "kit_number": "KIT-001",
    "kit_name": "Tube Bundle"
  },
  "uuid-of-part-2": {
    "source_type": "make",
    "kit_id": null,
    "kit_number": null,
    "kit_name": null
  }
}
```

Parts not in this map default to `source_type='make'`.

---

#### Set Item Source

```
PUT /api/mrp/projects/{project_id}/items/{item_id}/source
```

**Request Body:**

```json
{
  "source_type": "kit",
  "kit_id": "uuid-of-kit"
}
```

Or to revert to in-house:

```json
{
  "source_type": "make"
}
```

**Validation:**
- `source_type` must be `'make'` or `'kit'`
- If `source_type='kit'`, `kit_id` is required and must belong to the same project
- Upserts the record (inserts if new, updates if exists)

---

#### Remove Item Source (Revert to Default)

```
DELETE /api/mrp/projects/{project_id}/items/{item_id}/source
```

Deletes the source override, causing the item to default to `'make'`.

---

### Bulk Operations

#### Add Multiple Parts to Kit

```
POST /api/mrp/projects/{project_id}/kits/{kit_id}/parts
```

**Request Body:**

```json
["uuid-of-part-1", "uuid-of-part-2", "uuid-of-part-3"]
```

Upserts all item sources to `source_type='kit'` for this kit.

---

#### Remove Multiple Parts from Kit

```
DELETE /api/mrp/projects/{project_id}/kits/{kit_id}/parts
```

**Request Body:**

```json
["uuid-of-part-1", "uuid-of-part-2"]
```

Sets all matching item sources to `source_type='make'`.

---

### Kit Warnings

```
GET /api/mrp/projects/{project_id}/kits/{kit_id}/warnings
```

**Returns warnings if:**
- `use_kit=false` but parts are still assigned to the kit

**Response:**

```json
{
  "warnings": [
    {
      "type": "kit_disabled_with_parts",
      "message": "Kit 'Tube Bundle' is disabled but 12 parts are still assigned. These parts will use in-house routing.",
      "parts": [
        { "item_id": "uuid", "item_number": "wsp20030", "name": "Tube, Main Frame" }
      ]
    }
  ]
}
```

---

## Frontend UI

### 1. Kit Management Slideout

**Component:** `frontend/src/components/KitManagementSlideout.vue`

**Access:** MRP Dashboard → **Manage Kits** button (top-right toolbar)

**Features:**

- **Kit List View**
  - Shows all kits for the selected project
  - Display cards with:
    - Kit number and name
    - Vendor
    - Part count
    - Kit price vs in-house cost
    - Savings amount and percentage (green if positive, red if negative)
    - Use Kit toggle (checkmark icon)
  - Click a kit card to expand and view assigned parts

- **Add/Edit Kit Form**
  - Kit Number (auto-suggested: `KIT-001`, `KIT-002`, etc.)
  - Kit Name (freeform text)
  - Vendor (optional)
  - Price (numeric, USD)
  - Notes (optional freeform)

- **Kit Toggle (`use_kit`)**
  - Green checkmark icon = Active (kit pricing is used)
  - Gray circle icon = Disabled (parts fall back to in-house routing)
  - Click to toggle
  - When disabled, shows warning badge: "Kit pricing disabled - parts use in-house routing"

- **Delete Kit**
  - Trash icon on each kit card
  - Confirmation prompt: "Delete kit 'Tube Bundle'? Parts in this kit will revert to in-house routing."

- **Footer Summary**
  - Shows total kit cost (sum of all active kits)

**Dark Theme Styling:** Matches MRP dashboard dark theme (`#0f172a` background, `#38bdf8` accents)

---

### 2. Part Sourcing UI on Routing Page

**Component:** `frontend/src/views/MrpRoutingView.vue`

**Location:** Below routing operations table, above raw materials section

**Features:**

- **Source Selection Section**
  - Only visible when a project filter is active
  - Title: "Part Sourcing for Project [PROJECT-CODE]"
  - Two radio buttons:
    - **Make In-House** (default)
    - **Part of Kit** (enables kit dropdown)
  - Kit dropdown: Lists all kits from the project with format `[KIT-001] Tube Bundle ($850.00)`
  - Save button (updates source via `PUT /api/mrp/projects/{project_id}/items/{item_id}/source`)

- **Behavior**
  - On load, fetches item source for the current part and project
  - Pre-selects "Make In-House" or "Part of Kit" based on database record
  - If "Part of Kit" is selected, pre-selects the kit from the dropdown
  - When saved, shows toast notification: "Part source updated"

**Design Notes:**
- Uses project filter from URL query params (`?project=uuid-here`)
- Only displays sourcing UI when project filter is set
- If no project filter, displays: "Select a project filter to configure part sourcing"

---

## Cost Estimate Integration

**File:** `backend/app/services/cost_estimate.py`

**Function:** `compute_project_cost_estimate(project_id: str) -> dict`

This function calculates the total project cost estimate, factoring in kit pricing:

### Cost Calculation Logic

1. **Load all project parts** from `mrp_project_parts` (with quantities)
2. **Load active kits** where `use_kit=true`
3. **Load item sources** to determine which parts are in active kits
4. **For each part:**
   - **If part is in an active kit:**
     - Skip individual costing (kit price covers it)
     - Mark as `"in_kit": true` in response
     - Add kit info to the item
   - **If part is a supplier part (`is_supplier_part=true`):**
     - Use `unit_price` from items table
     - Add to `total_purchased` category
   - **Otherwise (in-house make part):**
     - Calculate labor cost from routing (hourly rate × est_time_min / 60)
     - Calculate material cost from routing_materials
     - Calculate outsourced cost from outsourced operations
     - Add to respective totals

5. **Sum kit costs:** Add up all active kit prices
6. **Calculate subtotal:** `labor + material + outsourced + purchased + kit_cost`
7. **Apply overhead multiplier:** `total = subtotal × overhead_multiplier`

### Response Structure

```json
{
  "project_id": "uuid-here",
  "labor_cost": 3450.00,
  "material_cost": 1200.50,
  "outsourced_cost": 850.00,
  "purchased_cost": 450.00,
  "kit_cost": 850.00,
  "overhead_multiplier": 1.35,
  "subtotal": 6800.50,
  "total": 9180.68,
  "items": [
    {
      "item_id": "uuid",
      "item_number": "wsp20030",
      "name": "Tube, Main Frame",
      "quantity": 2,
      "is_supplier_part": false,
      "in_kit": true,
      "kit_info": {
        "kit_id": "uuid",
        "kit_number": "KIT-001",
        "kit_name": "Tube Bundle"
      },
      "labor_cost": 0,
      "material_cost": 0,
      "outsourced_cost": 0,
      "unit_cost": 0,
      "extended_cost": 0
    },
    {
      "item_id": "uuid",
      "item_number": "wsp20040",
      "name": "Bracket",
      "quantity": 4,
      "is_supplier_part": false,
      "in_kit": false,
      "labor_cost": 15.50,
      "material_cost": 8.25,
      "outsourced_cost": 0,
      "unit_cost": 23.75,
      "extended_cost": 95.00
    }
  ],
  "kits": [
    {
      "kit_id": "uuid",
      "kit_number": "KIT-001",
      "kit_name": "Tube Bundle",
      "vendor": "ABC Fabrication",
      "price": 850.00,
      "part_count": 12
    }
  ]
}
```

**Key Points:**

- `kit_cost` is a separate category alongside labor, material, outsourced, and purchased
- Items with `"in_kit": true` show zero individual cost (covered by kit)
- `kits` array shows all active kits contributing to the total
- Cost estimate is used by:
  - MRP Dashboard cost display
  - AI Assistant cost queries
  - Project costing reports

---

## Use Cases

### 1. Evaluating Vendor Quote

**Scenario:** Vendor offers a pre-welded tube bundle for $850. You need to compare against in-house cost.

**Steps:**

1. Go to MRP Dashboard for the project
2. Click **Manage Kits** button
3. Click **Add Kit**
4. Enter:
   - Kit Number: `KIT-001`
   - Kit Name: `Tube Bundle`
   - Vendor: `ABC Fabrication`
   - Price: `850.00`
5. Save kit
6. Go to Routing page
7. For each part that's included in the vendor bundle:
   - Select the project filter
   - Toggle to "Part of Kit"
   - Select `[KIT-001] Tube Bundle`
   - Save
8. Return to Kit Management slideout
9. Expand `KIT-001` to see:
   - In-house cost: $1,240.50 (labor + material)
   - Kit price: $850.00
   - Savings: $390.50 (31.5%)

**Decision:** Kit is 31.5% cheaper than in-house → Purchase the kit.

---

### 2. Temporarily Disabling a Kit

**Scenario:** Vendor kit is out of stock. You need to build parts in-house temporarily without deleting the kit definition.

**Steps:**

1. Go to MRP Dashboard → **Manage Kits**
2. Click the **green checkmark** icon on the kit card (toggles to gray circle)
3. Kit is now disabled (`use_kit=false`)
4. Parts assigned to the kit automatically fall back to in-house routing costs
5. Project cost estimate recalculates to use routing costs instead of kit price
6. Warning badge appears: "Kit pricing disabled - parts use in-house routing"

**To Re-Enable:** Click the gray circle icon (toggles back to green checkmark).

---

### 3. Deleting a Kit

**Scenario:** Project plan changes, no longer purchasing the vendor kit.

**Steps:**

1. Go to MRP Dashboard → **Manage Kits**
2. Click the **trash icon** on the kit card
3. Confirm deletion: "Delete kit 'Tube Bundle'? Parts in this kit will revert to in-house routing."
4. Kit is deleted from `project_kits`
5. All parts assigned to this kit are automatically updated to `source_type='make'`
6. Parts now use in-house routing costs

---

## Database Queries

### Find all parts in a kit

```sql
SELECT
    i.item_number,
    i.name,
    pis.source_type,
    pk.kit_number,
    pk.kit_name
FROM project_item_source pis
JOIN items i ON pis.item_id = i.id
JOIN project_kits pk ON pis.kit_id = pk.id
WHERE pk.id = 'uuid-of-kit'
  AND pis.source_type = 'kit';
```

---

### Find all kits for a project

```sql
SELECT
    pk.kit_number,
    pk.kit_name,
    pk.vendor,
    pk.price,
    pk.use_kit,
    COUNT(pis.id) AS part_count
FROM project_kits pk
LEFT JOIN project_item_source pis ON pis.kit_id = pk.id AND pis.source_type = 'kit'
WHERE pk.project_id = 'uuid-of-project'
GROUP BY pk.id
ORDER BY pk.kit_number;
```

---

### Find parts sourced from kits vs in-house for a project

```sql
SELECT
    i.item_number,
    i.name,
    COALESCE(pis.source_type, 'make') AS source,
    pk.kit_name
FROM mrp_project_parts mpp
JOIN items i ON mpp.item_id = i.id
LEFT JOIN project_item_source pis ON pis.item_id = i.id AND pis.project_id = 'uuid-of-project'
LEFT JOIN project_kits pk ON pis.kit_id = pk.id
WHERE mpp.project_id = 'uuid-of-project'
ORDER BY COALESCE(pis.source_type, 'make'), i.item_number;
```

---

## Design Decisions

### Why per-project sourcing?

Parts may be sourced differently across projects. For example:
- **Project A:** Buy `wsp20030` as part of a vendor kit
- **Project B:** Make `wsp20030` in-house (vendor kit not available)

Per-project sourcing (`project_item_source` table) allows this flexibility.

---

### Why the `use_kit` toggle?

Allows temporarily disabling kit pricing without deleting the kit definition or reassigning parts. Useful when:
- Vendor kit is temporarily out of stock
- Testing cost sensitivity (kit vs in-house)
- Preserving historical kit data for future reference

---

### Why separate `kit_cost` category?

Keeps kit costs distinct from purchased parts, labor, material, and outsourced costs. This allows:
- Clear cost breakdowns in reports
- Easy comparison: "How much are we spending on kits vs in-house manufacturing?"
- Future reporting: "Which projects used vendor kits vs fully in-house?"

---

## Migration Notes

**Migration Files:**
- `backend/migrations/2026-07-09_project_kits.sql` - Creates `project_kits` and `project_item_source` tables

**Migration Strategy:**
- Tables are new, no data migration needed
- All existing parts default to `source_type='make'` (in-house routing)
- No impact on existing cost calculations until kits are created

**Rollback:** Drop tables `project_kits` and `project_item_source`. Cost estimate function degrades gracefully (no kit costs).

---

## Future Enhancements

### 1. Kit Template Library

Store reusable kit definitions across projects:
- Create a `kit_templates` table
- Allow copying templates to new projects
- Pre-fill part assignments based on template

### 2. Kit Price History

Track vendor price changes over time:
- Add `project_kit_price_history` table
- Log price updates with effective dates
- Compare historical pricing trends

### 3. Kit Lead Time Tracking

Add lead time fields to `project_kits`:
- `lead_time_weeks` - Vendor quoted lead time
- `last_order_date` - When kit was last ordered
- Use for project scheduling (compare kit lead time vs in-house manufacturing time)

### 4. Partial Kit Support

Allow marking parts as "partial kit" (e.g., vendor supplies pre-cut parts, you do final welding):
- Add `source_type='partial_kit'`
- Add `kit_labor_override` to apply partial in-house labor
- More accurate cost modeling for hybrid scenarios

---

## Testing

### Backend Tests

**File:** `backend/tests/test_master_design_book.py`, `backend/tests/test_master_design_book_update.py`

**Note:** Kit pricing tests are not yet written. Future tests should cover:

1. **Kit CRUD operations**
   - Create kit
   - Update kit (price, use_kit toggle)
   - Delete kit (verify parts revert to 'make')
   - List kits with cost comparison

2. **Item source management**
   - Set item source to 'kit'
   - Set item source to 'make'
   - Bulk add parts to kit
   - Bulk remove parts from kit

3. **Cost estimate integration**
   - Verify kit cost is included in project total
   - Verify parts in active kits show zero individual cost
   - Verify disabled kits (`use_kit=false`) don't contribute to kit_cost
   - Verify parts in disabled kits use routing costs

### Frontend Tests

**File:** `frontend/src/services/designBook.test.ts`, `frontend/src/utils/masterDesignBook.test.ts`, `frontend/src/components/DesignBookUpdateModal.test.ts`

**Note:** Kit pricing UI tests are not yet written. Future tests should cover:

1. **Kit Management Slideout**
   - Load kits for project
   - Create new kit
   - Edit kit
   - Delete kit
   - Toggle use_kit
   - Expand kit to view parts

2. **Routing Page Source UI**
   - Load item source for part
   - Save source as 'make'
   - Save source as 'kit' with kit selection
   - Project filter requirement

---

## Related Documentation

- **Database Schema:** `03-DATABASE-SCHEMA.md` - Full table definitions (update with kit tables)
- **MRP System:** `20-COMMON-WORKFLOWS.md` - Add kit management workflow
- **Cost Estimation:** `06-BOM-COST-ROLLUP-GUIDE.md` - Update with kit pricing integration
- **API Reference:** `04-SERVICES-REFERENCE.md` - Add kit endpoints
- **UI Standards:** `35-UI-DESIGN-STANDARDS.md` - Kit management UI patterns

---

**Last Updated:** 2026-07-09
**Version:** v3.9.3
**Author:** Claude Code (documentation agent)
