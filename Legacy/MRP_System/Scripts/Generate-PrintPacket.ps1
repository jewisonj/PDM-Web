# Generate-PrintPacket.ps1
# Creates stamped PDF print packets for MRP projects
# Requires: Python 3 with pypdf, reportlab

param(
    [Parameter(Mandatory=$true)]
    [string]$ProjectCode
)

$dbPath = "D:\PDM_Vault\pdm.sqlite"
$sqliteExe = "sqlite3.exe"
$pdfSourceDir = "D:\PDM_Vault\CADData\PDF"
$outputDir = "D:\MRP_System\PrintPackets\$ProjectCode"
$pythonExe = "python"

# Ensure output directory
if (-not (Test-Path $outputDir)) {
    New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
}

# Get project info
$projectInfo = & $sqliteExe -separator '|' $dbPath "SELECT project_code, description, customer, due_date, top_assembly FROM projects WHERE project_code='$ProjectCode';" 2>$null
if (-not $projectInfo) {
    Write-Error "Project not found: $ProjectCode"
    exit 1
}

$projParts = $projectInfo -split '\|'
$projCode = $projParts[0]
$projDesc = $projParts[1]
$projCustomer = $projParts[2]
$projDueDate = $projParts[3]
$projTopAsm = $projParts[4]

# Get all parts with routing and PDF info
$partsQuery = @"
SELECT pp.item_number, pp.quantity, i.description, i.part_type, 
       COALESCE(rt.total_time, 0) as routing_time,
       f.file_path as pdf_path
FROM project_parts pp
JOIN items i ON pp.item_number = i.item_number
LEFT JOIN (SELECT item_number, SUM(est_time_min) as total_time FROM item_routing GROUP BY item_number) rt ON pp.item_number = rt.item_number
LEFT JOIN files f ON pp.item_number = f.item_number AND f.file_type = 'PDF'
WHERE pp.project_code = '$ProjectCode' AND pp.item_number NOT LIKE 'zzz%'
ORDER BY CASE WHEN i.part_type LIKE '%ASM%' THEN 0 ELSE 1 END, pp.item_number;
"@

$partsResult = & $sqliteExe -separator '|' $dbPath $partsQuery 2>$null

# Get BOM children grouped by type (manufactured, mcmaster, supplier)
$bomQuery = @"
SELECT b.parent_item, b.child_item, b.quantity, i.description,
       COALESCE(i.is_supplier_part, 0) as is_supplier,
       COALESCE(i.supplier_prefix, '') as supplier_prefix,
       COALESCE(i.supplier_pn, '') as supplier_pn
FROM bom b
JOIN items i ON b.child_item = i.item_number
WHERE b.parent_item IN (SELECT item_number FROM project_parts WHERE project_code = '$ProjectCode')
ORDER BY b.parent_item, i.is_supplier_part, b.child_item;
"@

$bomResult = & $sqliteExe -separator '|' $dbPath $bomQuery 2>$null

# Get raw material assignments
$materialsQuery = @"
SELECT rm.item_number, rm.qty_required, mat.part_number, mat.type, mat.profile,
       mat.material, mat.dim1_in, mat.dim2_in, mat.wall_or_thk_in
FROM routing_materials rm
JOIN raw_materials mat ON rm.material_id = mat.material_id
JOIN project_parts pp ON rm.item_number = pp.item_number
WHERE pp.project_code = '$ProjectCode';
"@

$materialsResult = & $sqliteExe -separator '|' $dbPath $materialsQuery 2>$null

# Get routing per part for stamps
function Get-PartRouting {
    param([string]$ItemNumber)
    $routingQuery = "SELECT w.station_code, w.station_name FROM item_routing ir JOIN workstations w ON ir.station_code = w.station_code WHERE ir.item_number = '$ItemNumber' ORDER BY ir.sequence;"
    $result = & $sqliteExe -separator '|' $dbPath $routingQuery 2>$null
    return $result
}

# Calculate start date
$totalMinutes = & $sqliteExe $dbPath "SELECT COALESCE(SUM(pp.quantity * COALESCE(rt.total_time, 0)), 0) FROM project_parts pp LEFT JOIN (SELECT item_number, SUM(est_time_min) as total_time FROM item_routing GROUP BY item_number) rt ON pp.item_number = rt.item_number WHERE pp.project_code = '$ProjectCode';" 2>$null
$workDays = [math]::Ceiling([double]$totalMinutes / 480)

$startDate = ""
if ($projDueDate) {
    try {
        $due = [DateTime]::Parse($projDueDate)
        $start = $due.AddDays(-$workDays)
        $startDate = $start.ToString("MM/dd/yyyy")
        $projDueDate = $due.ToString("MM/dd/yyyy")
    } catch { }
}

# Build BOM lookup by parent
$bomByParent = @{}
foreach ($row in $bomResult) {
    if ([string]::IsNullOrWhiteSpace($row)) { continue }
    $cols = $row -split '\|'
    $parent = $cols[0]
    if (-not $bomByParent.ContainsKey($parent)) {
        $bomByParent[$parent] = @{ manufactured = @(); mcmaster = @(); supplier = @() }
    }
    
    $bomItem = @{
        child_item = $cols[1]
        quantity = $cols[2]
        description = $cols[3]
        is_supplier = $cols[4]
        supplier_prefix = $cols[5]
        supplier_pn = $cols[6]
    }
    
    if ($bomItem.is_supplier -eq '1') {
        if ($bomItem.supplier_prefix -eq 'mmc') {
            $bomByParent[$parent].mcmaster += $bomItem
        } else {
            $bomByParent[$parent].supplier += $bomItem
        }
    } else {
        $bomByParent[$parent].manufactured += $bomItem
    }
}

# Build materials lookup by item
$materialsByItem = @{}
foreach ($row in $materialsResult) {
    if ([string]::IsNullOrWhiteSpace($row)) { continue }
    $cols = $row -split '\|'
    $item = $cols[0]
    if (-not $materialsByItem.ContainsKey($item)) {
        $materialsByItem[$item] = [System.Collections.ArrayList]@()
    }
    [void]$materialsByItem[$item].Add(@{
        qty_required = $cols[1]
        part_number = $cols[2]
        type = $cols[3]
        profile = $cols[4]
        material = $cols[5]
        dim1 = $cols[6]
        dim2 = $cols[7]
        thickness = $cols[8]
    })
}

# Build parts data for Python
$partsData = @()
foreach ($row in $partsResult) {
    if ([string]::IsNullOrWhiteSpace($row)) { continue }
    $cols = $row -split '\|'
    $itemNum = $cols[0]
    $qty = $cols[1]
    $desc = $cols[2]
    $partType = $cols[3]
    $pdfPath = $cols[5]
    
    # Get routing for stamp
    $routing = Get-PartRouting -ItemNumber $itemNum
    $routingLines = [System.Collections.ArrayList]@()
    foreach ($r in $routing) {
        if ($r) {
            $rParts = $r -split '\|'
            [void]$routingLines.Add("$($rParts[0]) - $($rParts[1])")
        }
    }
    
    # Get BOM for this item
    $bom = if ($bomByParent.ContainsKey($itemNum)) { $bomByParent[$itemNum] } else { @{ manufactured = @(); mcmaster = @(); supplier = @() } }
    
    # Get raw materials - ensure array
    $rawMats = if ($materialsByItem.ContainsKey($itemNum)) { @($materialsByItem[$itemNum]) } else { @() }
    
    $partsData += @{
        item_number = $itemNum
        quantity = $qty
        description = $desc
        part_type = $partType
        pdf_path = $pdfPath
        routing = $routingLines
        bom_manufactured = $bom.manufactured
        bom_mcmaster = $bom.mcmaster
        bom_supplier = $bom.supplier
        raw_materials = $rawMats
    }
}

# Create Python script for PDF generation
$pythonScript = @"
import os
import sys
from io import BytesIO

try:
    from pypdf import PdfReader, PdfWriter
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import inch
except ImportError:
    print("ERROR: Install required packages: pip install pypdf reportlab")
    sys.exit(1)

# Project info
PROJECT_CODE = "$projCode"
PROJECT_DESC = "$projDesc"
CUSTOMER = "$projCustomer"
DUE_DATE = "$projDueDate"
START_DATE = "$startDate"
OUTPUT_DIR = r"$outputDir"
PDF_SOURCE = r"$pdfSourceDir"

# Parts data (injected from PowerShell)
PARTS = $($partsData | ConvertTo-Json -Depth 5 -Compress)

def create_stamp(part_info, page_width, page_height):
    """Create stamp overlay for a page"""
    packet = BytesIO()
    c = canvas.Canvas(packet, pagesize=(page_width, page_height))
    
    # Stamp position - right edge, middle
    stamp_width = 180
    stamp_height = 200
    x = page_width - stamp_width - 20
    y = (page_height - stamp_height) / 2
    
    # Draw stamp box
    c.setStrokeColorRGB(0, 0, 0)
    c.setFillColorRGB(1, 1, 1)
    c.rect(x, y, stamp_width, stamp_height, fill=1, stroke=1)
    
    # Text settings
    c.setFillColorRGB(0, 0, 0)
    line_height = 14
    current_y = y + stamp_height - 20
    
    def draw_line(text, bold=False):
        nonlocal current_y
        if bold:
            c.setFont("Helvetica-Bold", 9)
        else:
            c.setFont("Helvetica", 9)
        c.drawString(x + 8, current_y, text)
        current_y -= line_height
    
    # Draw stamp content
    draw_line(f"Project - {PROJECT_CODE}", bold=True)
    draw_line(f"Part Number - {part_info['item_number']}")
    draw_line(f"Start Date - {START_DATE}")
    draw_line(f"Due Date - {DUE_DATE}")
    draw_line(f"QTY - ({part_info['quantity']})")
    current_y -= 8
    draw_line("WORKSTATIONS", bold=True)
    
    for route in part_info.get('routing', []):
        draw_line(f"  {route}  ( )")
    
    c.save()
    packet.seek(0)
    return PdfReader(packet)

def create_cover_sheet():
    """Create cover sheet PDF with separated BOM sections"""
    packet = BytesIO()
    c = canvas.Canvas(packet, pagesize=letter)
    width, height = letter
    
    # Title
    c.setFont("Helvetica-Bold", 24)
    c.drawCentredString(width/2, height - 80, f"Project: {PROJECT_CODE}")
    
    # Project info
    c.setFont("Helvetica", 14)
    y = height - 130
    
    if CUSTOMER:
        c.drawString(72, y, f"Customer: {CUSTOMER}")
        y -= 25
    if PROJECT_DESC:
        c.drawString(72, y, f"Description: {PROJECT_DESC}")
        y -= 25
    c.drawString(72, y, f"Due Date: {DUE_DATE}")
    y -= 25
    c.drawString(72, y, f"Start Date: {START_DATE}")
    y -= 40
    
    # MANUFACTURED PARTS section
    c.setFont("Helvetica-Bold", 14)
    c.drawString(72, y, "Manufactured Parts")
    y -= 20
    
    c.setFont("Helvetica-Bold", 10)
    c.drawString(72, y, "Part Number")
    c.drawString(200, y, "Description")
    c.drawString(420, y, "Qty")
    y -= 5
    c.line(72, y, width - 72, y)
    y -= 15
    
    c.setFont("Helvetica", 9)
    mfg_parts = [p for p in PARTS if not p.get('item_number', '').startswith('mmc') and not p.get('item_number', '').startswith('spn')]
    for part in mfg_parts:
        if y < 100:
            c.showPage()
            y = height - 72
            c.setFont("Helvetica", 9)
        
        c.drawString(72, y, part['item_number'])
        desc = (part.get('description') or '')[:35]
        c.drawString(200, y, desc)
        c.drawString(420, y, str(part['quantity']))
        y -= 3
        c.setStrokeColorRGB(0.8, 0.8, 0.8)  # Light gray line
        c.line(72, y, width - 72, y)
        c.setStrokeColorRGB(0, 0, 0)  # Reset to black
        y -= 9
    
    y -= 20
    
    # MCMASTER PARTS section (with hyperlinks)
    mcmaster_parts = [p for p in PARTS if p.get('item_number', '').startswith('mmc')]
    if mcmaster_parts:
        if y < 150:
            c.showPage()
            y = height - 72
        
        c.setFont("Helvetica-Bold", 14)
        c.drawString(72, y, "McMaster-Carr Parts")
        y -= 20
        
        c.setFont("Helvetica-Bold", 10)
        c.drawString(72, y, "McMaster P/N")
        c.drawString(200, y, "Description")
        c.drawString(420, y, "Qty")
        y -= 5
        c.line(72, y, width - 72, y)
        y -= 15
        
        c.setFont("Helvetica", 9)
        for part in mcmaster_parts:
            if y < 72:
                c.showPage()
                y = height - 72
                c.setFont("Helvetica", 9)
            
            # Strip MMC prefix for display and link
            mmc_pn = part['item_number'][3:] if part['item_number'].lower().startswith('mmc') else part['item_number']
            
            # Create hyperlink
            url = f"https://www.mcmaster.com/{mmc_pn}/"
            c.setFillColorRGB(0, 0, 0.8)  # Blue for links
            c.drawString(72, y, mmc_pn)
            # Add clickable link annotation
            c.linkURL(url, (72, y - 2, 180, y + 10), relative=0)
            
            c.setFillColorRGB(0, 0, 0)  # Back to black
            desc = (part.get('description') or '')[:35]
            c.drawString(200, y, desc)
            c.drawString(420, y, str(part['quantity']))
            y -= 3
            c.setStrokeColorRGB(0.8, 0.8, 0.8)
            c.line(72, y, width - 72, y)
            c.setStrokeColorRGB(0, 0, 0)
            y -= 9
        
        y -= 20
    
    # SUPPLIER PARTS section
    supplier_parts = [p for p in PARTS if p.get('item_number', '').startswith('spn')]
    if supplier_parts:
        if y < 150:
            c.showPage()
            y = height - 72
        
        c.setFont("Helvetica-Bold", 14)
        c.drawString(72, y, "Supplier Parts")
        y -= 20
        
        c.setFont("Helvetica-Bold", 10)
        c.drawString(72, y, "Supplier P/N")
        c.drawString(200, y, "Description")
        c.drawString(420, y, "Qty")
        y -= 5
        c.line(72, y, width - 72, y)
        y -= 15
        
        c.setFont("Helvetica", 9)
        for part in supplier_parts:
            if y < 72:
                c.showPage()
                y = height - 72
                c.setFont("Helvetica", 9)
            
            c.drawString(72, y, part['item_number'])
            desc = (part.get('description') or '')[:35]
            c.drawString(200, y, desc)
            c.drawString(420, y, str(part['quantity']))
            y -= 3
            c.setStrokeColorRGB(0.8, 0.8, 0.8)
            c.line(72, y, width - 72, y)
            c.setStrokeColorRGB(0, 0, 0)
            y -= 9
        
        y -= 20
    
    # RAW MATERIALS section - aggregate by material part number
    material_totals = {}  # keyed by part_number
    for part in PARTS:
        raw_mats = part.get('raw_materials', [])
        part_qty = int(part.get('quantity', 1) or 1)
        # Handle case where it might be a single dict or malformed
        if isinstance(raw_mats, dict):
            raw_mats = [raw_mats]
        elif not isinstance(raw_mats, list):
            raw_mats = []
        for mat in raw_mats:
            if not isinstance(mat, dict):
                continue
            pn = mat.get('part_number', '')
            if not pn:
                continue
            mat_qty = float(mat.get('qty_required', 0) or 0)
            total_qty = mat_qty * part_qty
            
            if pn in material_totals:
                material_totals[pn]['total_qty'] += total_qty
            else:
                material_totals[pn] = {
                    'part_number': pn,
                    'material': mat.get('material', ''),
                    'dim1': mat.get('dim1', ''),
                    'dim2': mat.get('dim2', ''),
                    'thickness': mat.get('thickness', ''),
                    'type': mat.get('type', ''),
                    'total_qty': total_qty
                }
    
    if material_totals:
        if y < 150:
            c.showPage()
            y = height - 72
        
        c.setFont("Helvetica-Bold", 14)
        c.drawString(72, y, "Raw Material Requirements")
        y -= 20
        
        c.setFont("Helvetica-Bold", 10)
        c.drawString(72, y, "Material P/N")
        c.drawString(200, y, "Material / Size")
        c.drawString(350, y, "Total")
        c.drawString(420, y, "Feet")
        c.drawString(470, y, "Sticks (20ft)")
        y -= 5
        c.line(72, y, width - 72, y)
        y -= 15
        
        c.setFont("Helvetica", 9)
        for pn, mat in material_totals.items():
            if y < 72:
                c.showPage()
                y = height - 72
                c.setFont("Helvetica", 9)
            
            c.drawString(72, y, mat['part_number'])
            dims = f"{mat['material']} {mat['dim1']}x{mat['dim2']}x{mat['thickness']}"
            c.drawString(200, y, dims[:25])
            
            if mat['type'] == 'SM':
                # Sheet metal - just show sheets
                c.drawString(350, y, f"{mat['total_qty']:.1f} sheets")
            else:
                # Tube - show inches, feet, and sticks
                total_in = mat['total_qty']
                total_ft = total_in / 12
                sticks = int((total_ft + 19.99) // 20)  # Round up to 20ft sticks
                c.drawString(350, y, f"{total_in:.1f} in")
                c.drawString(420, y, f"{total_ft:.1f} ft")
                c.drawString(470, y, f"{sticks}")
            y -= 3
            c.setStrokeColorRGB(0.8, 0.8, 0.8)
            c.line(72, y, width - 72, y)
            c.setStrokeColorRGB(0, 0, 0)
            y -= 9
    
    c.save()
    packet.seek(0)
    return PdfReader(packet)

def main():
    writer = PdfWriter()
    
    # Add cover sheet
    cover = create_cover_sheet()
    for page in cover.pages:
        writer.add_page(page)
    
    # Process each part's PDF
    for part in PARTS:
        pdf_path = part.get('pdf_path')
        if not pdf_path or not os.path.exists(pdf_path):
            continue
        
        try:
            reader = PdfReader(pdf_path)
            for page in reader.pages:
                # Get page dimensions
                page_width = float(page.mediabox.width)
                page_height = float(page.mediabox.height)
                
                # Create stamp overlay
                stamp_pdf = create_stamp(part, page_width, page_height)
                
                # Merge stamp onto page
                page.merge_page(stamp_pdf.pages[0])
                writer.add_page(page)
        except Exception as e:
            print(f"Warning: Could not process {pdf_path}: {e}")
    
    # Write output
    output_path = os.path.join(OUTPUT_DIR, f"{PROJECT_CODE}_packet.pdf")
    with open(output_path, 'wb') as f:
        writer.write(f)
    
    print(f"Generated: {output_path}")

if __name__ == '__main__':
    main()
"@

# Write and execute Python script
$tempScript = Join-Path $env:TEMP "generate_packet_$ProjectCode.py"
$pythonScript | Out-File -FilePath $tempScript -Encoding UTF8

try {
    $result = & $pythonExe $tempScript 2>&1
    Write-Host $result
    
    $outputPath = Join-Path $outputDir "${ProjectCode}_packet.pdf"
    if (Test-Path $outputPath) {
        Write-Host "SUCCESS: Print packet generated at $outputPath"
    } else {
        Write-Error "Failed to generate print packet"
        exit 1
    }
}
finally {
    Remove-Item $tempScript -Force -ErrorAction SilentlyContinue
}
