# MRP API Server
# REST API for MRP System - runs on port 8086

$port = 8086
$dbPath = "D:\PDM_Vault\pdm.sqlite"
$sqliteExe = "sqlite3.exe"
$printPacketScript = "D:\MRP_System\Scripts\Generate-PrintPacket.ps1"

$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add("http://+:$port/")

try {
    $listener.Start()
    Write-Host "MRP API Server started on port $port"
}
catch {
    Write-Host "ERROR: Failed to start. Run: netsh http add urlacl url=http://+:$port/ user=Everyone"
    exit 1
}

function Query-DB {
    param([string]$sql)
    & $sqliteExe -separator '|' -header $dbPath $sql 2>$null
}

function Exec-DB {
    param([string]$sql)
    & $sqliteExe $dbPath $sql 2>$null
}

function ConvertTo-JsonFromPipe {
    param($rows, $headers)
    if (-not $rows -or $rows.Count -eq 0) { return "[]" }
    $headerArray = $headers -split '\|'
    $objects = @()
    foreach ($row in $rows) {
        if ([string]::IsNullOrWhiteSpace($row)) { continue }
        $values = $row -split '\|'
        $obj = @{}
        for ($i = 0; $i -lt $headerArray.Count; $i++) {
            $key = $headerArray[$i]
            $val = if ($i -lt $values.Count) { $values[$i] } else { "" }
            # Keep code fields as strings (station_code, project_code, type_code)
            if ($key -match 'code') { $obj[$key] = $val }
            elseif ($val -match '^\d+$') { $obj[$key] = [int]$val }
            elseif ($val -match '^\d+\.\d+$') { $obj[$key] = [double]$val }
            else { $obj[$key] = $val }
        }
        $objects += $obj
    }
    return ($objects | ConvertTo-Json -Depth 5)
}

function Send-Response {
    param($context, $body, $contentType = "application/json", $statusCode = 200)
    $context.Response.StatusCode = $statusCode
    $context.Response.ContentType = $contentType
    $context.Response.Headers.Add("Access-Control-Allow-Origin", "*")
    $context.Response.Headers.Add("Access-Control-Allow-Methods", "GET, PUT, POST, DELETE, OPTIONS")
    $context.Response.Headers.Add("Access-Control-Allow-Headers", "Content-Type")
    $buffer = [System.Text.Encoding]::UTF8.GetBytes($body)
    $context.Response.ContentLength64 = $buffer.Length
    $context.Response.OutputStream.Write($buffer, 0, $buffer.Length)
    $context.Response.OutputStream.Close()
}

function Get-RequestBody {
    param($request)
    $reader = New-Object System.IO.StreamReader($request.InputStream)
    $body = $reader.ReadToEnd()
    $reader.Close()
    return $body | ConvertFrom-Json
}

function Explode-BOM {
    param([string]$projectCode, [string]$topAssembly)
    
    Exec-DB "DELETE FROM project_parts WHERE project_code='$projectCode';"
    Exec-DB "INSERT INTO project_parts (project_code, item_number, quantity, parent_assembly) VALUES ('$projectCode', '$topAssembly', 1, NULL);"
    
    $sql = @"
WITH RECURSIVE bom_tree AS (
    SELECT child_item, parent_item, quantity, 1 as level
    FROM bom WHERE parent_item = '$topAssembly'
    UNION ALL
    SELECT b.child_item, b.parent_item, b.quantity * bt.quantity, bt.level + 1
    FROM bom b JOIN bom_tree bt ON b.parent_item = bt.child_item
    WHERE bt.level < 20
)
SELECT child_item, parent_item, SUM(quantity) as total_qty
FROM bom_tree GROUP BY child_item, parent_item;
"@
    
    $result = & $sqliteExe -separator '|' $dbPath $sql 2>$null
    
    foreach ($row in $result) {
        if ([string]::IsNullOrWhiteSpace($row)) { continue }
        $parts = $row -split '\|'
        $childItem = $parts[0].Replace("'", "''")
        $parentItem = $parts[1].Replace("'", "''")
        $qty = $parts[2]
        Exec-DB "INSERT INTO project_parts (project_code, item_number, quantity, parent_assembly) VALUES ('$projectCode', '$childItem', $qty, '$parentItem');"
    }
}

while ($listener.IsListening) {
    $context = $listener.GetContext()
    $request = $context.Request
    $method = $request.HttpMethod
    $path = $request.Url.LocalPath
    
    Write-Host "$method $path"
    
    if ($method -eq "OPTIONS") { Send-Response $context "" "text/plain" 204; continue }
    
    try {
        # GET /api/items
        if ($path -eq "/api/items" -and $method -eq "GET") {
            $sql = "SELECT i.item_number, i.description, i.revision, i.iteration, i.lifecycle_state, i.part_type, i.material, i.thickness, i.cut_time, i.mass, CASE WHEN COUNT(ir.routing_id) > 0 THEN 1 ELSE 0 END as has_routing, COUNT(ir.routing_id) as station_count FROM items i LEFT JOIN item_routing ir ON i.item_number = ir.item_number WHERE i.item_number NOT LIKE 'zzz%' GROUP BY i.item_number ORDER BY i.item_number;"
            $result = Query-DB $sql
            if ($result -and $result.Count -gt 1) { Send-Response $context (ConvertTo-JsonFromPipe ($result | Select-Object -Skip 1) $result[0]) }
            else { Send-Response $context "[]" }
        }
        
        # GET /api/workstations
        elseif ($path -eq "/api/workstations" -and $method -eq "GET") {
            $result = Query-DB "SELECT station_code, station_name, sort_order FROM workstations ORDER BY sort_order;"
            if ($result -and $result.Count -gt 1) { Send-Response $context (ConvertTo-JsonFromPipe ($result | Select-Object -Skip 1) $result[0]) }
            else { Send-Response $context "[]" }
        }
        
        # POST /api/workstations - Create new station
        elseif ($path -eq "/api/workstations" -and $method -eq "POST") {
            $data = Get-RequestBody $request
            $code = $data.station_code.ToString().PadLeft(3, '0')
            $name = $data.station_name.Replace("'", "''")
            $sortOrder = if ($data.sort_order) { $data.sort_order } else { [int]$code }
            Exec-DB "INSERT INTO workstations (station_code, station_name, sort_order) VALUES ('$code', '$name', $sortOrder);"
            Send-Response $context '{"success": true}'
        }
        
        # GET /api/part-types
        elseif ($path -eq "/api/part-types" -and $method -eq "GET") {
            $result = Query-DB "SELECT type_code, type_name, sort_order FROM part_types ORDER BY sort_order;"
            if ($result -and $result.Count -gt 1) { Send-Response $context (ConvertTo-JsonFromPipe ($result | Select-Object -Skip 1) $result[0]) }
            else { Send-Response $context "[]" }
        }
        
        # GET /api/files
        elseif ($path -eq "/api/files" -and $method -eq "GET") {
            $result = Query-DB "SELECT item_number, file_path, file_type FROM files ORDER BY item_number;"
            if ($result -and $result.Count -gt 1) { Send-Response $context (ConvertTo-JsonFromPipe ($result | Select-Object -Skip 1) $result[0]) }
            else { Send-Response $context "[]" }
        }
        
        # GET /api/routing/{item}
        elseif ($path -match "^/api/routing/([^/]+)$" -and $method -eq "GET") {
            $item = $matches[1]
            $result = Query-DB "SELECT ir.station_code, w.station_name, ir.sequence, ir.est_time_min, ir.notes FROM item_routing ir JOIN workstations w ON ir.station_code = w.station_code WHERE ir.item_number = '$item' ORDER BY ir.sequence;"
            if ($result -and $result.Count -gt 1) { Send-Response $context (ConvertTo-JsonFromPipe ($result | Select-Object -Skip 1) $result[0]) }
            else { Send-Response $context "[]" }
        }
        
        # PUT /api/routing/{item}
        elseif ($path -match "^/api/routing/([^/]+)$" -and $method -eq "PUT") {
            $item = $matches[1]
            $routing = Get-RequestBody $request
            Exec-DB "DELETE FROM item_routing WHERE item_number = '$item';"
            foreach ($r in $routing) {
                $estTime = if ($r.est_time_min) { $r.est_time_min } else { 0 }
                $notes = if ($r.notes) { $r.notes.Replace("'", "''") } else { "" }
                Exec-DB "INSERT INTO item_routing (item_number, station_code, sequence, est_time_min, notes) VALUES ('$item', '$($r.station_code)', $($r.sequence), $estTime, '$notes');"
            }
            Send-Response $context '{"success": true}'
        }
        
        # PUT /api/items/{item}/type
        elseif ($path -match "^/api/items/([^/]+)/type$" -and $method -eq "PUT") {
            $item = $matches[1]
            $data = Get-RequestBody $request
            Exec-DB "UPDATE items SET part_type = '$($data.part_type)', modified_at = CURRENT_TIMESTAMP WHERE item_number = '$item';"
            Send-Response $context '{"success": true}'
        }
        
        # GET /api/pdf
        elseif ($path -eq "/api/pdf" -and $method -eq "GET") {
            $pdfPath = $request.QueryString["path"]
            if ($pdfPath -and (Test-Path $pdfPath)) {
                $bytes = [System.IO.File]::ReadAllBytes($pdfPath)
                $context.Response.ContentType = "application/pdf"
                $context.Response.Headers.Add("Access-Control-Allow-Origin", "*")
                $context.Response.ContentLength64 = $bytes.Length
                $context.Response.OutputStream.Write($bytes, 0, $bytes.Length)
                $context.Response.OutputStream.Close()
            } else { Send-Response $context '{"error": "PDF not found"}' "application/json" 404 }
        }
        
        # ========== RAW MATERIALS ENDPOINTS ==========
        
        # GET /api/raw-materials - All raw materials
        elseif ($path -eq "/api/raw-materials" -and $method -eq "GET") {
            $sql = "SELECT material_id, type, profile, dim1_in, dim2_in, wall_or_thk_in, wall_or_thk_code, material, material_code, stock_length_ft, weight_lb_per_ft, stock_weight_lb, part_number, qty_on_hand, qty_on_order, reorder_point FROM raw_materials ORDER BY type, dim1_in, dim2_in, wall_or_thk_in;"
            $result = Query-DB $sql
            if ($result -and $result.Count -gt 1) { Send-Response $context (ConvertTo-JsonFromPipe ($result | Select-Object -Skip 1) $result[0]) }
            else { Send-Response $context "[]" }
        }
        
        # PUT /api/raw-materials/{id} - Update inventory
        elseif ($path -match "^/api/raw-materials/(\d+)$" -and $method -eq "PUT") {
            $materialId = $matches[1]
            $data = Get-RequestBody $request
            $updates = @()
            if ($null -ne $data.qty_on_hand) { $updates += "qty_on_hand = $($data.qty_on_hand)" }
            if ($null -ne $data.qty_on_order) { $updates += "qty_on_order = $($data.qty_on_order)" }
            if ($null -ne $data.reorder_point) { $updates += "reorder_point = $($data.reorder_point)" }
            
            if ($updates.Count -gt 0) {
                Exec-DB "UPDATE raw_materials SET $($updates -join ', ') WHERE material_id = $materialId;"
                Send-Response $context '{"success": true}'
            } else {
                Send-Response $context '{"success": false, "error": "No fields to update"}' "application/json" 400
            }
        }
        
        # DELETE /api/routing-materials/{id} - Remove material assignment (must be before GET)
        elseif ($path -match "^/api/routing-materials/(\d+)$" -and $method -eq "DELETE") {
            $assignmentId = $matches[1]
            Exec-DB "DELETE FROM routing_materials WHERE id = $assignmentId;"
            Send-Response $context '{"success": true}'
        }
        
        # GET /api/routing-materials/{item} - Get material assignments for item
        elseif ($path -match "^/api/routing-materials/([^/]+)$" -and $method -eq "GET") {
            $item = $matches[1]
            $sql = "SELECT rm.id, rm.item_number, rm.qty_required, rm.notes, mat.material_id, mat.part_number, mat.type, mat.profile, mat.dim1_in, mat.dim2_in, mat.wall_or_thk_in, mat.wall_or_thk_code, mat.material, mat.material_code, mat.stock_length_ft, mat.weight_lb_per_ft FROM routing_materials rm JOIN raw_materials mat ON rm.material_id = mat.material_id WHERE rm.item_number = '$item';"
            $result = Query-DB $sql
            if ($result -and $result.Count -gt 1) { Send-Response $context (ConvertTo-JsonFromPipe ($result | Select-Object -Skip 1) $result[0]) }
            else { Send-Response $context "[]" }
        }
        
        # POST /api/routing-materials - Assign material to item
        elseif ($path -eq "/api/routing-materials" -and $method -eq "POST") {
            $data = Get-RequestBody $request
            $item = $data.item_number.Replace("'", "''")
            $matId = $data.material_id
            $qty = if ($data.qty_required) { $data.qty_required } else { 0 }
            $notes = if ($data.notes) { $data.notes.Replace("'", "''") } else { "" }
            
            # Delete existing then insert (cleaner than INSERT OR REPLACE with autoincrement)
            Exec-DB "DELETE FROM routing_materials WHERE item_number = '$item' AND material_id = $matId;"
            Exec-DB "INSERT INTO routing_materials (item_number, material_id, qty_required, notes) VALUES ('$item', $matId, $qty, '$notes');"
            Send-Response $context '{"success": true}'
        }
        
        # ========== PROJECT ENDPOINTS ==========
        
        # GET /api/projects
        elseif ($path -eq "/api/projects" -and $method -eq "GET") {
            $sql = "SELECT p.project_code, p.description, p.customer, p.top_assembly, p.due_date, p.status, p.created_at, p.notes, COALESCE(cnt.part_count, 0) as part_count, COALESCE(unrouted.unrouted_count, 0) as unrouted_count FROM projects p LEFT JOIN (SELECT project_code, COUNT(*) as part_count FROM project_parts WHERE item_number NOT LIKE 'zzz%' GROUP BY project_code) cnt ON p.project_code = cnt.project_code LEFT JOIN (SELECT pp.project_code, COUNT(*) as unrouted_count FROM project_parts pp LEFT JOIN item_routing ir ON pp.item_number = ir.item_number WHERE ir.routing_id IS NULL AND pp.item_number NOT LIKE 'zzz%' GROUP BY pp.project_code) unrouted ON p.project_code = unrouted.project_code ORDER BY p.due_date;"
            $result = Query-DB $sql
            if ($result -and $result.Count -gt 1) { Send-Response $context (ConvertTo-JsonFromPipe ($result | Select-Object -Skip 1) $result[0]) }
            else { Send-Response $context "[]" }
        }
        
        # GET /api/projects/{code}
        elseif ($path -match "^/api/projects/([^/]+)$" -and $method -eq "GET") {
            $code = $matches[1]
            $sql = "SELECT p.*, COALESCE(cnt.part_count, 0) as part_count, COALESCE(unrouted.unrouted_count, 0) as unrouted_count, COALESCE(timing.total_minutes, 0) as total_minutes FROM projects p LEFT JOIN (SELECT project_code, COUNT(*) as part_count FROM project_parts WHERE project_code='$code' AND item_number NOT LIKE 'zzz%') cnt ON 1=1 LEFT JOIN (SELECT COUNT(*) as unrouted_count FROM project_parts pp LEFT JOIN item_routing ir ON pp.item_number = ir.item_number WHERE pp.project_code='$code' AND ir.routing_id IS NULL AND pp.item_number NOT LIKE 'zzz%') unrouted ON 1=1 LEFT JOIN (SELECT SUM(pp.quantity * COALESCE(rt.total_time, 0)) as total_minutes FROM project_parts pp LEFT JOIN (SELECT item_number, SUM(est_time_min) as total_time FROM item_routing GROUP BY item_number) rt ON pp.item_number = rt.item_number WHERE pp.project_code='$code' AND pp.item_number NOT LIKE 'zzz%') timing ON 1=1 WHERE p.project_code = '$code';"
            $result = Query-DB $sql
            if ($result -and $result.Count -gt 1) { Send-Response $context (ConvertTo-JsonFromPipe ($result | Select-Object -Skip 1) $result[0]) }
            else { Send-Response $context '{"error": "Not found"}' "application/json" 404 }
        }
        
        # POST /api/projects
        elseif ($path -eq "/api/projects" -and $method -eq "POST") {
            $data = Get-RequestBody $request
            $code = $data.project_code.Replace("'", "''")
            $desc = if ($data.description) { $data.description.Replace("'", "''") } else { "" }
            $customer = if ($data.customer) { $data.customer.Replace("'", "''") } else { "" }
            $dueDate = if ($data.due_date) { $data.due_date } else { "" }
            $notes = if ($data.notes) { $data.notes.Replace("'", "''") } else { "" }
            Exec-DB "INSERT INTO projects (project_code, description, customer, due_date, status, notes) VALUES ('$code', '$desc', '$customer', '$dueDate', 'Setup', '$notes');"
            Send-Response $context '{"success": true}'
        }
        
        # PUT /api/projects/{code}
        elseif ($path -match "^/api/projects/([^/]+)$" -and $method -eq "PUT") {
            $code = $matches[1]
            $data = Get-RequestBody $request
            $updates = @()
            if ($data.description) { $updates += "description='$($data.description.Replace("'", "''"))'" }
            if ($data.customer) { $updates += "customer='$($data.customer.Replace("'", "''"))'" }
            if ($data.due_date) { $updates += "due_date='$($data.due_date)'" }
            if ($data.status) { $updates += "status='$($data.status)'" }
            if ($data.notes) { $updates += "notes='$($data.notes.Replace("'", "''"))'" }
            if ($data.top_assembly) { $updates += "top_assembly='$($data.top_assembly)'" }
            if ($updates.Count -gt 0) { Exec-DB "UPDATE projects SET $($updates -join ', ') WHERE project_code='$code';" }
            Send-Response $context '{"success": true}'
        }
        
        # DELETE /api/projects/{code}
        elseif ($path -match "^/api/projects/([^/]+)$" -and $method -eq "DELETE") {
            $code = $matches[1]
            Exec-DB "DELETE FROM project_parts WHERE project_code='$code';"
            Exec-DB "DELETE FROM time_logs WHERE project_code='$code';"
            Exec-DB "DELETE FROM part_completion WHERE project_code='$code';"
            Exec-DB "DELETE FROM projects WHERE project_code='$code';"
            Send-Response $context '{"success": true}'
        }
        
        # POST /api/projects/{code}/assemblies
        elseif ($path -match "^/api/projects/([^/]+)/assemblies$" -and $method -eq "POST") {
            $code = $matches[1]
            $data = Get-RequestBody $request
            $topAsm = $data.top_assembly.ToLower()
            Exec-DB "UPDATE projects SET top_assembly='$topAsm' WHERE project_code='$code';"
            Explode-BOM -projectCode $code -topAssembly $topAsm
            Send-Response $context '{"success": true}'
        }
        
        # GET /api/projects/{code}/parts
        elseif ($path -match "^/api/projects/([^/]+)/parts$" -and $method -eq "GET") {
            $code = $matches[1]
            $sql = "SELECT pp.item_number, pp.quantity, pp.parent_assembly, pp.status, i.description, i.part_type, i.material, CASE WHEN COUNT(ir.routing_id) > 0 THEN 1 ELSE 0 END as has_routing, COALESCE(SUM(ir.est_time_min), 0) as routing_time, f.file_path as pdf_path FROM project_parts pp JOIN items i ON pp.item_number = i.item_number LEFT JOIN item_routing ir ON pp.item_number = ir.item_number LEFT JOIN files f ON pp.item_number = f.item_number AND f.file_type = 'PDF' WHERE pp.project_code = '$code' AND pp.item_number NOT LIKE 'zzz%' GROUP BY pp.item_number ORDER BY i.part_type, pp.item_number;"
            $result = Query-DB $sql
            if ($result -and $result.Count -gt 1) { Send-Response $context (ConvertTo-JsonFromPipe ($result | Select-Object -Skip 1) $result[0]) }
            else { Send-Response $context "[]" }
        }
        
        # GET /api/projects/{code}/print-packet - Check if exists or serve PDF
        elseif ($path -match "^/api/projects/([^/]+)/print-packet$" -and $method -eq "GET") {
            $code = $matches[1]
            $pdfPath = "D:\MRP_System\PrintPackets\$code\${code}_packet.pdf"
            $serve = $request.QueryString["serve"]
            
            if (Test-Path $pdfPath) {
                if ($serve -eq "true") {
                    # Serve the actual PDF
                    $bytes = [System.IO.File]::ReadAllBytes($pdfPath)
                    $context.Response.ContentType = "application/pdf"
                    $context.Response.Headers.Add("Access-Control-Allow-Origin", "*")
                    $context.Response.Headers.Add("Content-Disposition", "inline; filename=`"${code}_packet.pdf`"")
                    $context.Response.ContentLength64 = $bytes.Length
                    $context.Response.OutputStream.Write($bytes, 0, $bytes.Length)
                    $context.Response.OutputStream.Close()
                } else {
                    # Just return exists status
                    $lastMod = (Get-Item $pdfPath).LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss")
                    Send-Response $context "{`"exists`": true, `"path`": `"$pdfPath`", `"modified`": `"$lastMod`"}"
                }
            } else {
                Send-Response $context '{"exists": false}'
            }
        }
        
        # POST /api/projects/{code}/print-packet
        elseif ($path -match "^/api/projects/([^/]+)/print-packet$" -and $method -eq "POST") {
            $code = $matches[1]
            $result = & powershell.exe -ExecutionPolicy Bypass -File $printPacketScript -ProjectCode $code 2>&1
            $outputPath = "D:\MRP_System\PrintPackets\$code\${code}_packet.pdf"
            if (Test-Path $outputPath) { Send-Response $context "{`"success`": true, `"path`": `"$outputPath`"}" }
            else { Send-Response $context "{`"success`": false, `"error`": `"$result`"}" "application/json" 500 }
        }
        
        # POST /api/time-logs - Log time for a part at a station
        elseif ($path -eq "/api/time-logs" -and $method -eq "POST") {
            $data = Get-RequestBody $request
            $projCode = $data.project_code.Replace("'", "''")
            $itemNum = $data.item_number.Replace("'", "''")
            $stationCode = $data.station_code.Replace("'", "''")
            $worker = if ($data.worker) { $data.worker.Replace("'", "''") } else { "Unknown" }
            $timeMin = if ($data.time_min) { $data.time_min } else { 0 }
            $notes = if ($data.notes) { $data.notes.Replace("'", "''") } else { "" }
            
            Exec-DB "INSERT INTO time_logs (project_code, item_number, station_code, worker, time_min, notes) VALUES ('$projCode', '$itemNum', '$stationCode', '$worker', $timeMin, '$notes');"
            Send-Response $context '{"success": true}'
        }
        
        # GET /api/time-logs?project={code} - Get time logs for project
        elseif ($path -eq "/api/time-logs" -and $method -eq "GET") {
            $projCode = $request.QueryString["project"]
            $sql = "SELECT * FROM time_logs"
            if ($projCode) { $sql += " WHERE project_code = '$projCode'" }
            $sql += " ORDER BY logged_at DESC;"
            $result = Query-DB $sql
            if ($result -and $result.Count -gt 1) { Send-Response $context (ConvertTo-JsonFromPipe ($result | Select-Object -Skip 1) $result[0]) }
            else { Send-Response $context "[]" }
        }
        
        # POST /api/part-completion - Mark part complete at station
        elseif ($path -eq "/api/part-completion" -and $method -eq "POST") {
            $data = Get-RequestBody $request
            $projCode = $data.project_code.Replace("'", "''")
            $itemNum = $data.item_number.Replace("'", "''")
            $stationCode = $data.station_code.Replace("'", "''")
            $qtyComplete = if ($data.qty_complete) { $data.qty_complete } else { 0 }
            $completedBy = if ($data.completed_by) { $data.completed_by.Replace("'", "''") } else { "Unknown" }
            
            Exec-DB "INSERT INTO part_completion (project_code, item_number, station_code, qty_complete, completed_by) VALUES ('$projCode', '$itemNum', '$stationCode', $qtyComplete, '$completedBy');"
            Send-Response $context '{"success": true}'
        }
        
        # GET /api/part-completion?project={code} - Get completion status
        elseif ($path -eq "/api/part-completion" -and $method -eq "GET") {
            $projCode = $request.QueryString["project"]
            $sql = "SELECT project_code, item_number, station_code, SUM(qty_complete) as qty_complete FROM part_completion"
            if ($projCode) { $sql += " WHERE project_code = '$projCode'" }
            $sql += " GROUP BY project_code, item_number, station_code;"
            $result = Query-DB $sql
            if ($result -and $result.Count -gt 1) { Send-Response $context (ConvertTo-JsonFromPipe ($result | Select-Object -Skip 1) $result[0]) }
            else { Send-Response $context "[]" }
        }
        
        else { Send-Response $context '{"error": "Not found"}' "application/json" 404 }
    }
    catch {
        Write-Host "ERROR: $_"
        Send-Response $context "{`"error`": `"$_`"}" "application/json" 500
    }
}
