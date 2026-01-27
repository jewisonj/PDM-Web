# ================================
#   PDM HTML Browser Generator
#   Uses sqlite3.exe (no DLLs)
#   Groups suffix items (csa0030_img_1 → csa0030)
#   Adds PDF preview + clickable links
# ================================

# --- CONFIG ---
$dbPath  = "D:\PDM_Vault\pdm.sqlite"
$pdmRoot = "D:\PDM_Vault"
$webRoot = Join-Path $pdmRoot "Web"
$outHtml = Join-Path $webRoot "index.html"

# If sqlite3.exe is not on PATH, set full path here:
$sqliteExe = "sqlite3.exe"

# Ensure output folder
if (!(Test-Path $webRoot)) {
    New-Item -ItemType Directory -Path $webRoot | Out-Null
}

Write-Host "Generating PDM HTML Browser..."

# ------------------------------
# Helper: run sqlite3 and return rows as strings
# ------------------------------
function Invoke-SqliteQuery {
    param([string]$Query)

    $result = & $sqliteExe -separator '|' $dbPath $Query 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "SQLite query failed: $Query"
        return @()
    }
    return $result
}

# ------------------------------
# Helper: normalize item number
# e.g. "csa0030_img_1" -> "csa0030"
#      "CSA0030_stp"  -> "CSA0030"
# ------------------------------
function Normalize-ItemNumber {
    param([string]$Item)

    if ([string]::IsNullOrWhiteSpace($Item)) { return $Item }

    # Match 3 letters + 4 digits at start, adjust if your scheme differs
    $m = [regex]::Match($Item, "^[A-Za-z]{3}\d{4}")
    if ($m.Success) { return $m.Value }
    return $Item
}

# ------------------------------
# Load items
# ------------------------------
$rawItems = Invoke-SqliteQuery "
    SELECT 
        item_number,
        COALESCE(description,''),
        revision,
        iteration,
        lifecycle_state
    FROM items
    ORDER BY item_number;
"

Write-Host "Loaded $($rawItems.Count) item rows."

# We'll group by normalized key so csa0030_img_1 collapses into csa0030
$itemsByKey = @{}

foreach ($row in $rawItems) {
    $parts = $row -split '\|', 5
    if ($parts.Count -lt 5) { continue }

    $origItem = $parts[0]
    $desc     = $parts[1]
    $rev      = $parts[2]
    $iter     = [int]$parts[3]
    $state    = $parts[4]

    $key = Normalize-ItemNumber $origItem

    if (-not $itemsByKey.ContainsKey($key)) {
        $itemsByKey[$key] = [PSCustomObject]@{
            item_number = $key
            description = $desc
            revision    = $rev
            iteration   = $iter
            state       = $state
            files       = @()
        }
    }
    else {
        # Merge: keep highest revision / iteration and non-empty description/state
        $item = $itemsByKey[$key]

        # Simple revision comparison (lexical works fine for single letters)
        $replaceRev = $false
        if ([string]::IsNullOrWhiteSpace($item.revision)) { $replaceRev = $true }
        elseif ($item.revision -lt $rev) { $replaceRev = $true }
        elseif ($item.revision -eq $rev -and $item.iteration -lt $iter) { $replaceRev = $true }

        if ($replaceRev) {
            $item.revision  = $rev
            $item.iteration = $iter
        }

        if ([string]::IsNullOrWhiteSpace($item.description) -and -not [string]::IsNullOrWhiteSpace($desc)) {
            $item.description = $desc
        }

        if ([string]::IsNullOrWhiteSpace($item.state) -and -not [string]::IsNullOrWhiteSpace($state)) {
            $item.state = $state
        }
    }
}

# ------------------------------
# Load file records and attach to normalized items
# ------------------------------
$rawFiles = Invoke-SqliteQuery "
    SELECT 
        item_number,
        file_path,
        file_type,
        revision,
        iteration
    FROM files
    ORDER BY item_number, file_type;
"

Write-Host "Loaded $($rawFiles.Count) file rows."

foreach ($row in $rawFiles) {
    $parts = $row -split '\|', 5
    if ($parts.Count -lt 5) { continue }

    $origItem = $parts[0]
    $filePath = $parts[1]
    $fileType = $parts[2]
    $rev      = $parts[3]
    $iter     = [int]$parts[4]

    # Skip archive files in the normal view
    if ($filePath -match "\\Archive\\") { continue }

    $key = Normalize-ItemNumber $origItem

    if (-not $itemsByKey.ContainsKey($key)) {
        # Create shell item if we have files but no item row
        $itemsByKey[$key] = [PSCustomObject]@{
            item_number = $key
            description = ""
            revision    = $rev
            iteration   = $iter
            state       = "Unknown"
            files       = @()
        }
    }

    $item = $itemsByKey[$key]

    # De-duplicate in memory: don't add same file twice
    $already = $item.files | Where-Object { $_.file_path -eq $filePath }
    if ($already.Count -gt 0) { continue }

    $fileObj = [PSCustomObject]@{
        file_type = $fileType
        file_path = $filePath
        revision  = $rev
        iteration = $iter
    }

    $item.files += $fileObj
}

# Flatten to array and sort
$itemList = $itemsByKey.GetEnumerator() | Sort-Object Name | ForEach-Object { $_.Value }

# Convert to JSON (compact)
$json = $itemList | ConvertTo-Json -Depth 6 -Compress

# ------------------------------
# Build HTML
# ------------------------------
$html = @"
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>PDM Browser</title>
<style>
body {
    background: #020617;
    color: #e5e7eb;
    font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    margin: 0;
}
.container {
    display: flex;
    height: 100vh;
}
.left {
    width: 30%;
    padding: 0.75rem;
    border-right: 1px solid #1f2937;
    overflow-y: auto;
    box-sizing: border-box;
    background: #020617;
}
.right {
    flex: 1;
    padding: 0.75rem 1rem;
    overflow-y: auto;
    box-sizing: border-box;
    background: #020617;
}
.search-input {
    width: 100%;
    padding: 6px 8px;
    border-radius: 999px;
    border: 1px solid #334155;
    background: #020617;
    color: #e5e7eb;
    font-size: 0.85rem;
    box-sizing: border-box;
}
.search-input::placeholder {
    color: #64748b;
}
.item {
    padding: 0.45rem 0.6rem;
    margin-top: 0.3rem;
    border: 1px solid #1f2937;
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.82rem;
    background: #020617;
}
.item:hover {
    border-color: #38bdf8;
}
.item.active {
    border-color: #38bdf8;
    background: #0b1120;
}
.item-sub {
    font-size: 0.75rem;
    color: #94a3b8;
}
a {
    color: #e5e7eb;
    text-decoration: underline;
}
a:hover {
    color: #38bdf8;
}
.file-row {
    margin-bottom: 0.25rem;
    font-size: 0.8rem;
}
.section-title {
    margin-top: 1rem;
    margin-bottom: 0.25rem;
    font-size: 0.9rem;
    font-weight: 600;
}
.muted {
    color: #94a3b8;
    font-size: 0.8rem;
}
</style>
</head>
<body>

<div class="container">
    <div class="left">
        <input id="search" class="search-input" placeholder="Search...">
        <div id="itemList"></div>
    </div>
    <div class="right">
        <h2 id="itemTitle">Select an item</h2>
        <div id="itemDetails" class="muted">Choose an item from the left to see details and files.</div>
        <div id="pdfPreview" style="margin-top:1rem;"></div>
    </div>
</div>

<script>
// Embedded data from PowerShell
window.PDM_DATA = $json;

function escapeHtml(t) {
    if (t === null || t === undefined) return "";
    return String(t).replace(/[&<>"]/g, function(c) {
        return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c] || c;
    });
}

function renderList(data) {
    const list = document.getElementById("itemList");
    list.innerHTML = "";

    data.forEach(item => {
        const div = document.createElement("div");
        div.className = "item";
        div.dataset.itemNumber = item.item_number;

        const state = item.state || "Unknown";
        const rev = item.revision || "?";
        const it  = item.iteration || "?";

        div.innerHTML = "<div><strong>" + escapeHtml(item.item_number) + "</strong></div>" +
                        "<div class='item-sub'>Rev " + rev + "." + it + " - " + escapeHtml(state) + "</div>";

        div.onclick = () => {
            document.querySelectorAll(".item.active").forEach(e => e.classList.remove("active"));
            div.classList.add("active");
            renderDetails(item);
        };

        list.appendChild(div);
    });
}

function renderDetails(item) {
    document.getElementById("itemTitle").innerText = item.item_number;

    const desc = item.description || "";
    const state = item.state || "Unknown";
    const rev = item.revision || "?";
    const it  = item.iteration || "?";

    let html = "";
    html += "<p><strong>Description:</strong> " + (desc ? escapeHtml(desc) : "<span class='muted'>No description.</span>") + "</p>";
    html += "<p><strong>State:</strong> " + escapeHtml(state) + "</p>";
    html += "<p><strong>Revision:</strong> " + rev + "." + it + "</p>";

    html += "<div class='section-title'>Files</div>";

    const files = item.files || [];
    if (!files.length) {
        html += "<p class='muted'>No files linked in the database for this item.</p>";
    } else {
        files.forEach(f => {
            const lowerPath = (f.file_path || "").toLowerCase();
            const lowerType = (f.file_type || "").toLowerCase();
            const isPdf  = lowerType === "pdf" || lowerPath.endsWith(".pdf");

            const url = "file:///" + (f.file_path || "").replace(/\\/g, "/");

            if (isPdf) {
                html += "<div class='file-row'><strong>PDF</strong>: " +
                    "<a href=\"" + url + "\" onclick=\"loadPdfPreview('" + url + "'); return false;\">" +
                    escapeHtml(f.file_path) + "</a></div>";
            } else {
                html += "<div class='file-row'><strong>" + escapeHtml(f.file_type || "FILE").toUpperCase() +
                    "</strong>: <a href=\"" + url + "\" target=\"_blank\">" +
                    escapeHtml(f.file_path) + "</a></div>";
            }
        });
    }

    document.getElementById("itemDetails").innerHTML = html;
    document.getElementById("pdfPreview").innerHTML = "";
}

function loadPdfPreview(url) {
    const panel = document.getElementById("pdfPreview");
    panel.innerHTML = "<div class='section-title'>PDF Preview</div>" +
        "<iframe src=\"" + url + "\" width=\"100%\" height=\"600px\" style=\"border:1px solid #1f2937; border-radius:6px;\"></iframe>";
}

document.getElementById("search").oninput = function() {
    const q = this.value.toLowerCase();
    const all = window.PDM_DATA || [];
    const filtered = all.filter(i =>
        (i.item_number || "").toLowerCase().includes(q) ||
        (i.description || "").toLowerCase().includes(q) ||
        (i.state || "").toLowerCase().includes(q)
    );
    renderList(filtered);
};

renderList(window.PDM_DATA || []);
</script>

</body>
</html>
"@

Set-Content -Path $outHtml -Value $html -Encoding utf8

Write-Host "Generated: $outHtml"
