-- ============================================================================
-- Used Item Numbers Table
-- Tracks part numbers that have been copied from the Part Number Generator
-- but not yet created as items in PDM. Prevents duplicate number generation.
-- ============================================================================

CREATE TABLE IF NOT EXISTS used_item_numbers (
    item_number TEXT PRIMARY KEY,
    used_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE used_item_numbers IS 'Tracks part numbers copied from generator but not yet in PDM';
COMMENT ON COLUMN used_item_numbers.item_number IS 'The reserved part number (e.g., csp00040)';
COMMENT ON COLUMN used_item_numbers.used_at IS 'When the number was copied/reserved';

-- ============================================================================
-- Index for prefix-based queries
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_used_item_numbers_prefix
    ON used_item_numbers(substring(item_number, 1, 3));

-- ============================================================================
-- Auto-cleanup trigger: remove from used_item_numbers when item is created
-- ============================================================================
CREATE OR REPLACE FUNCTION cleanup_used_item_number_on_create()
RETURNS TRIGGER AS $$
BEGIN
    DELETE FROM used_item_numbers WHERE item_number = NEW.item_number;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_cleanup_used_item_number ON items;
CREATE TRIGGER trigger_cleanup_used_item_number
    AFTER INSERT ON items
    FOR EACH ROW
    EXECUTE FUNCTION cleanup_used_item_number_on_create();

-- ============================================================================
-- RLS Policies (allow all for authenticated users)
-- ============================================================================
ALTER TABLE used_item_numbers ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Allow all for authenticated users" ON used_item_numbers;
CREATE POLICY "Allow all for authenticated users" ON used_item_numbers
    FOR ALL USING (auth.role() = 'authenticated');
