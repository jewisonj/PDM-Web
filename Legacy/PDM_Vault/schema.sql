-- ============================================
-- PDM System Database Schema
-- ============================================
-- This schema defines the complete structure for the PDM SQLite database
-- Last Updated: 2025-12-30

-- ============================================
-- ITEMS TABLE
-- ============================================
-- Stores part metadata, lifecycle state, revision/iteration tracking,
-- BOM-extracted properties, and supplier part information
CREATE TABLE items (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_number TEXT UNIQUE NOT NULL,
    name TEXT,
    revision TEXT DEFAULT 'A',
    iteration INTEGER DEFAULT 1,
    lifecycle_state TEXT DEFAULT 'Design',
    description TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    modified_at TEXT DEFAULT CURRENT_TIMESTAMP,

    -- BOM-extracted properties
    material TEXT,                  -- e.g., 'STEEL_HSLA', 'ALUMINUM_6061'
    mass REAL,                      -- grams
    thickness REAL,                 -- millimeters
    cut_length REAL,                -- millimeters (flat pattern perimeter)
    project TEXT,                   -- project/assembly association

    -- Supplier part properties
    is_supplier_part BOOLEAN DEFAULT 0,
    supplier_prefix TEXT,           -- e.g., 'mmc', 'spn'
    supplier_pn TEXT,               -- supplier part number
    supplier_name TEXT,             -- e.g., 'McMaster-Carr', 'Souriau'
    unit_price REAL,                -- price per unit
    units TEXT,                     -- e.g., 'each', 'box of 100'
    product_url TEXT,               -- catalog/datasheet URL
    stock_quantity INTEGER DEFAULT 0,
    reorder_point INTEGER,
    specifications TEXT,            -- additional specs/notes

    -- Manufacturing properties
    cut_time REAL,                  -- estimated laser cut time (seconds)
    price_est REAL                  -- estimated manufacturing cost
);

-- ============================================
-- FILES TABLE
-- ============================================
-- Tracks individual files with paths, types, and version info
CREATE TABLE files (
    file_id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_number TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_type TEXT NOT NULL,        -- 'CAD', 'STEP', 'DXF', 'SVG', 'PDF', 'OTHER'
    revision TEXT,
    iteration INTEGER,
    added_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (item_number) REFERENCES items(item_number)
);

-- ============================================
-- BOM TABLE
-- ============================================
-- Bill of Materials - single-level parent/child relationships
CREATE TABLE bom (
    bom_id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_item TEXT NOT NULL,      -- Assembly item number
    child_item TEXT NOT NULL,       -- Component item number
    quantity INTEGER NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    source_file TEXT,               -- Audit trail: source BOM file
    FOREIGN KEY (parent_item) REFERENCES items(item_number),
    FOREIGN KEY (child_item) REFERENCES items(item_number)
);

-- ============================================
-- LIFECYCLE_HISTORY TABLE
-- ============================================
-- Audit trail for lifecycle state changes
CREATE TABLE lifecycle_history (
    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_number TEXT NOT NULL,
    old_state TEXT,
    new_state TEXT,
    old_revision TEXT,
    new_revision TEXT,
    old_iteration INTEGER,
    new_iteration INTEGER,
    changed_by TEXT,
    changed_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (item_number) REFERENCES items(item_number)
);

-- ============================================
-- CHECKOUTS TABLE
-- ============================================
-- Tracks which items are currently checked out
CREATE TABLE checkouts (
    item_number TEXT NOT NULL,
    username TEXT NOT NULL,
    checked_out_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (item_number) REFERENCES items(item_number)
);

-- ============================================
-- WORK_QUEUE TABLE
-- ============================================
-- Task queue for automated processing by Worker-Processor
CREATE TABLE work_queue (
    task_id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_number TEXT NOT NULL,
    file_path TEXT NOT NULL,
    task_type TEXT NOT NULL,        -- 'GENERATE_DXF', 'GENERATE_SVG', 'PARAM_SYNC', 'SYNC'
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    started_at TEXT,
    completed_at TEXT,
    status TEXT DEFAULT 'Pending'   -- 'Pending', 'Processing', 'Completed', 'Failed'
);

-- ============================================
-- INDEXES
-- ============================================
-- Items table indexes
CREATE INDEX idx_items_number ON items(item_number);
CREATE INDEX idx_items_supplier ON items(is_supplier_part, supplier_prefix);
CREATE INDEX idx_items_supplier_pn ON items(supplier_pn);

-- Files table indexes
CREATE INDEX idx_files_item ON files(item_number);

-- BOM table indexes
CREATE INDEX idx_bom_parent ON bom(parent_item);
CREATE INDEX idx_bom_child ON bom(child_item);

-- Work queue indexes
CREATE INDEX idx_work_queue_status ON work_queue(status);
CREATE INDEX idx_work_queue_item ON work_queue(item_number);
CREATE INDEX idx_work_queue_type ON work_queue(task_type);

-- ============================================
-- VIEWS
-- ============================================
-- Categorizes parts by type (Supplier, Assembly, Part)
CREATE VIEW v_parts_by_type AS
SELECT
    item_number,
    CASE
        WHEN is_supplier_part = 1 THEN 'Supplier'
        WHEN item_number LIKE '%a%' THEN 'Assembly'
        WHEN item_number LIKE '%p%' THEN 'Part'
        ELSE 'Unknown'
    END as part_type,
    supplier_prefix,
    supplier_name,
    description,
    material,
    lifecycle_state
FROM items;
