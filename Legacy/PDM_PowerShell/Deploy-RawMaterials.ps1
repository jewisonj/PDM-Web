# Deploy-RawMaterials.ps1
# One-step deployment for raw materials system
# Run from DATASERVER with admin privileges

$dbPath = "D:\PDM_Vault\pdm.sqlite"
$sqliteExe = "sqlite3.exe"

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host " Raw Materials System Deployment" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""

# 1. Backup database
Write-Host "[1/4] Backing up database..." -ForegroundColor Yellow
$backupPath = "D:\PDM_Vault\pdm.sqlite.backup_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
Copy-Item $dbPath $backupPath
Write-Host "  Backup created: $backupPath" -ForegroundColor Green

# 2. Create tables
Write-Host ""
Write-Host "[2/4] Creating raw materials tables..." -ForegroundColor Yellow

$schemaSQL = @"
-- Raw materials catalog
CREATE TABLE IF NOT EXISTS raw_materials (
    material_id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    profile TEXT,
    dim1_in REAL,
    dim2_in REAL,
    wall_or_thk_in REAL,
    wall_or_thk_code TEXT,
    material TEXT NOT NULL,
    material_code TEXT NOT NULL,
    stock_length_ft REAL,
    weight_lb_per_ft REAL,
    stock_weight_lb REAL,
    part_number TEXT UNIQUE NOT NULL,
    qty_on_hand INTEGER DEFAULT 0,
    qty_on_order INTEGER DEFAULT 0,
    reorder_point INTEGER DEFAULT 0,
    notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Link materials to items
CREATE TABLE IF NOT EXISTS routing_materials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_number TEXT NOT NULL,
    material_id INTEGER NOT NULL,
    qty_required REAL NOT NULL,
    notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (material_id) REFERENCES raw_materials(material_id),
    FOREIGN KEY (item_number) REFERENCES items(item_number),
    UNIQUE(item_number, material_id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_raw_materials_type ON raw_materials(type);
CREATE INDEX IF NOT EXISTS idx_raw_materials_material ON raw_materials(material_code);
CREATE INDEX IF NOT EXISTS idx_raw_materials_pn ON raw_materials(part_number);
CREATE INDEX IF NOT EXISTS idx_routing_materials_item ON routing_materials(item_number);
CREATE INDEX IF NOT EXISTS idx_routing_materials_material ON routing_materials(material_id);
"@

& $sqliteExe $dbPath $schemaSQL
if ($LASTEXITCODE -eq 0) {
    Write-Host "  Tables created successfully" -ForegroundColor Green
} else {
    Write-Host "  ERROR creating tables!" -ForegroundColor Red
    exit 1
}

# 3. Import materials from CSV
Write-Host ""
Write-Host "[3/4] Importing materials from CSV..." -ForegroundColor Yellow

$csvPath = "D:\MRP_System\Material_List.csv"
if (Test-Path $csvPath) {
    $csv = Import-Csv $csvPath
    $imported = 0
    
    foreach ($row in $csv) {
        $type = $row.Type
        $profile = $row.Profile
        $dim1 = if ($row.Dim1_in) { $row.Dim1_in } else { "NULL" }
        $dim2 = if ($row.Dim2_in) { $row.Dim2_in } else { "NULL" }
        $wall = $row.Wall_or_Thk_in
        $wallCode = $row.Wall_or_Thk_Code
        $material = $row.Material
        $matCode = $row.Material_Code
        $stockLen = if ($row.Stock_Length_ft) { $row.Stock_Length_ft } else { "NULL" }
        $weightFt = if ($row.Weight_lb_per_ft) { $row.Weight_lb_per_ft } else { "NULL" }
        $stockWt = if ($row.Stock_Weight_lb) { $row.Stock_Weight_lb } else { "NULL" }
        $pn = $row.Part_Number
        
        $sql = "INSERT OR REPLACE INTO raw_materials (type, profile, dim1_in, dim2_in, wall_or_thk_in, wall_or_thk_code, material, material_code, stock_length_ft, weight_lb_per_ft, stock_weight_lb, part_number) VALUES ('$type', '$profile', $dim1, $dim2, $wall, '$wallCode', '$material', '$matCode', $stockLen, $weightFt, $stockWt, '$pn');"
        
        & $sqliteExe $dbPath $sql 2>$null
        if ($LASTEXITCODE -eq 0) { $imported++ }
    }
    
    Write-Host "  Imported $imported materials" -ForegroundColor Green
} else {
    Write-Host "  CSV not found at $csvPath - skipping import" -ForegroundColor Yellow
    Write-Host "  Copy Material_List.csv to D:\MRP_System\ and re-run import" -ForegroundColor Yellow
}

# 4. Verify
Write-Host ""
Write-Host "[4/4] Verifying installation..." -ForegroundColor Yellow

$count = & $sqliteExe $dbPath "SELECT COUNT(*) FROM raw_materials;"
Write-Host "  Materials in database: $count" -ForegroundColor Green

$tables = & $sqliteExe $dbPath ".tables"
Write-Host "  Tables: $tables"

Write-Host ""
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host " Deployment Complete!" -ForegroundColor Green
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Stop MRP-API-Server:  nssm stop MRP-API-Server" -ForegroundColor White
Write-Host "2. Copy updated MRP-API-Server.ps1 to D:\MRP_System\Scripts\" -ForegroundColor White
Write-Host "3. Start MRP-API-Server: nssm start MRP-API-Server" -ForegroundColor White
Write-Host "4. Copy routing_editor.html to D:\PDM_WebServer\public\mrp\" -ForegroundColor White
Write-Host "5. Copy raw_materials.html to D:\PDM_WebServer\public\mrp\" -ForegroundColor White
Write-Host "6. Copy Generate-PrintPacket.ps1 to D:\MRP_System\Scripts\" -ForegroundColor White
Write-Host "7. Test in browser: http://DATASERVER:3000/mrp/routing_editor.html" -ForegroundColor White
