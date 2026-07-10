-- Migration: Project Kits for Bundle/Kit Pricing
-- Date: 2026-07-09
-- Description: Adds tables for tracking vendor kits and per-project item sourcing

-- ============================================================================
-- project_kits: Vendor bundles/kits purchased for a project
-- ============================================================================
CREATE TABLE IF NOT EXISTS project_kits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES mrp_projects(id) ON DELETE CASCADE,
    kit_number VARCHAR(50) NOT NULL,           -- e.g., "KIT-001"
    kit_name VARCHAR(255) NOT NULL,            -- e.g., "Tube Bundle"
    vendor VARCHAR(255),                       -- Vendor/supplier name
    price DECIMAL(12, 2) NOT NULL DEFAULT 0,   -- Total kit price from vendor
    use_kit BOOLEAN NOT NULL DEFAULT true,     -- Toggle: use kit pricing vs in-house
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Unique kit number per project
    CONSTRAINT unique_kit_number_per_project UNIQUE (project_id, kit_number)
);

-- Index for project lookups
CREATE INDEX IF NOT EXISTS idx_project_kits_project_id ON project_kits(project_id);

-- ============================================================================
-- project_item_source: Per-project sourcing method for each part
-- ============================================================================
CREATE TABLE IF NOT EXISTS project_item_source (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES mrp_projects(id) ON DELETE CASCADE,
    item_id UUID NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    source_type VARCHAR(20) NOT NULL DEFAULT 'make',  -- 'make' | 'kit'
    kit_id UUID REFERENCES project_kits(id) ON DELETE SET NULL,  -- Only set when source_type='kit'
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Each item can only have one source per project
    CONSTRAINT unique_item_source_per_project UNIQUE (project_id, item_id),

    -- Validate source_type values
    CONSTRAINT valid_source_type CHECK (source_type IN ('make', 'kit')),

    -- If source_type is 'kit', kit_id should be set
    CONSTRAINT kit_id_required_for_kit_source CHECK (
        (source_type = 'kit' AND kit_id IS NOT NULL) OR
        (source_type = 'make' AND kit_id IS NULL)
    )
);

-- Indexes for lookups
CREATE INDEX IF NOT EXISTS idx_project_item_source_project_id ON project_item_source(project_id);
CREATE INDEX IF NOT EXISTS idx_project_item_source_item_id ON project_item_source(item_id);
CREATE INDEX IF NOT EXISTS idx_project_item_source_kit_id ON project_item_source(kit_id);

-- ============================================================================
-- Trigger: Update updated_at on project_kits
-- ============================================================================
CREATE OR REPLACE FUNCTION update_project_kits_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_project_kits_updated_at ON project_kits;
CREATE TRIGGER trigger_project_kits_updated_at
    BEFORE UPDATE ON project_kits
    FOR EACH ROW
    EXECUTE FUNCTION update_project_kits_updated_at();

-- ============================================================================
-- RLS Policies (if RLS is enabled)
-- ============================================================================
-- Enable RLS
ALTER TABLE project_kits ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_item_source ENABLE ROW LEVEL SECURITY;

-- Allow all operations for authenticated users (simple policy for small team)
CREATE POLICY "Allow all for authenticated users" ON project_kits
    FOR ALL USING (auth.role() = 'authenticated');

CREATE POLICY "Allow all for authenticated users" ON project_item_source
    FOR ALL USING (auth.role() = 'authenticated');

-- ============================================================================
-- Comments for documentation
-- ============================================================================
COMMENT ON TABLE project_kits IS 'Vendor bundles/kits purchased for MRP projects. Tracks bundle pricing vs in-house manufacturing.';
COMMENT ON COLUMN project_kits.use_kit IS 'When true, kit price is used in cost calculations. When false, parts fall back to in-house routing costs.';
COMMENT ON COLUMN project_kits.price IS 'Total vendor price for the entire kit/bundle.';

COMMENT ON TABLE project_item_source IS 'Per-project sourcing method for each part. Determines whether a part is made in-house or sourced from a vendor kit.';
COMMENT ON COLUMN project_item_source.source_type IS 'make = use in-house routing, kit = part of a vendor bundle';
