. "D:\PDM_PowerShell\PDM-Library.ps1"

Write-Log "PDM HTML Browser generation started."

# Ensure Web folder exists
$webRoot   = "D:\PDM_Vault\Web"
$outputPath = Join-Path $webRoot "index.html"

if (-not (Test-Path $webRoot)) {
    New-Item -ItemType Directory -Path $webRoot | Out-Null
    Write-Log "Created Web folder at $webRoot"
}

# -----------------------------
# Load data from SQLite via Query-SQL
# -----------------------------

# ITEMS: item_number, name, description, revision, iteration, lifecycle_state
$itemsRaw = Query-SQL "
    SELECT 
        item_number || '|' ||
        COALESCE(name, '') || '|' ||
        COALESCE(description, '') || '|' ||
        revision || '|' ||
        iteration || '|' ||
        lifecycle_state
    FROM items
    ORDER BY item_number;
"

$items = @()
foreach ($row in $itemsRaw) {
    $parts = $row -split '\|'
    if ($parts.Count -ge 6) {
        $items += [PSCustomObject]@{
            item_number     = $parts[0]
            name            = $parts[1]
            description     = $parts[2]
            revision        = $parts[3]
            iteration       = [int]$parts[4]
            lifecycle_state = $parts[5]
        }
    }
}

# FILES: item_number, file_path, file_type
$filesRaw = Query-SQL "
    SELECT
        item_number || '|' ||
        file_path   || '|' ||
        file_type
    FROM files
    ORDER BY item_number, file_type, file_path;
"

$files = @()
foreach ($row in $filesRaw) {
    $parts = $row -split '\|'
    if ($parts.Count -ge 3) {
        $files += [PSCustomObject]@{
            item_number = $parts[0]
            file_path   = $parts[1]
            file_type   = $parts[2]
        }
    }
}

# BOM: parent_item, child_item, quantity
$bomRaw = Query-SQL "
    SELECT
        parent_item || '|' ||
        child_item  || '|' ||
        quantity
    FROM bom
    ORDER BY parent_item, child_item;
"

$bom = @()
foreach ($row in $bomRaw) {
    $parts = $row -split '\|'
    if ($parts.Count -ge 3) {
        $bom += [PSCustomObject]@{
            parent_item = $parts[0]
            child_item  = $parts[1]
            quantity    = [int]$parts[2]
        }
    }
}

# -----------------------------
# Convert to JSON for embedding
# -----------------------------
$itemsJson = $items | ConvertTo-Json -Depth 5
$filesJson = $files | ConvertTo-Json -Depth 5
$bomJson   = $bom   | ConvertTo-Json -Depth 5

# -----------------------------
# HTML Template
# -----------------------------
$htmlTemplate = @'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>PDM Browser</title>
    <style>
        * {
            box-sizing: border-box;
        }

        body {
            margin: 0;
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            background: #020617;
            color: #e5e7eb;
        }

        .app {
            display: grid;
            grid-template-columns: 260px 1fr;
            height: 100vh;
            overflow: hidden;
        }

        .sidebar {
            background: #020617;
            border-right: 1px solid #1e293b;
            padding: 12px;
            display: flex;
            flex-direction: column;
        }

        .sidebar h1 {
            font-size: 18px;
            margin: 0 0 10px;
            color: #e5e7eb;
        }

        .search-box {
            margin-bottom: 8px;
        }

        .search-box input {
            width: 100%;
            padding: 6px 8px;
            border-radius: 6px;
            border: 1px solid #1f2937;
            background: #020617;
            color: #e5e7eb;
        }

        .search-box input:focus {
            outline: none;
            border-color: #38bdf8;
            box-shadow: 0 0 0 1px #38bdf8;
        }

        .list {
            flex: 1;
            overflow-y: auto;
            margin-top: 6px;
        }

        .item-row {
            padding: 6px 8px;
            border-radius: 6px;
            cursor: pointer;
            margin-bottom: 2px;
        }

        .item-row:hover {
            background: #0f172a;
        }

        .item-row.active {
            background: #1d4ed8;
        }

        .item-row-main {
            font-size: 13px;
            font-weight: 500;
        }

        .item-row-sub {
            font-size: 11px;
            color: #9ca3af;
        }

        .content {
            display: flex;
            flex-direction: column;
            height: 100vh;
        }

        .item-main {
            padding: 10px 14px;
            border-bottom: 1px solid #1e293b;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .item-main h2 {
            margin: 0;
            font-size: 18px;
        }

        .item-meta-line {
            font-size: 12px;
            color: #9ca3af;
        }

        .content-body {
            display: grid;
            grid-template-columns: minmax(0, 1.1fr) minmax(0, 1.4fr);
            gap: 10px;
            padding: 10px 14px;
            flex: 1;
            overflow: hidden;
        }

        .panel {
            border-radius: 10px;
            border: 1px solid #1e293b;
            background: #020617;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        .panel-title {
            padding: 8px 10px;
            font-size: 13px;
            border-bottom: 1px solid #1e293b;
            background: #020617;
        }

        .panel-body {
            padding: 8px 10px;
            flex: 1;
            overflow: auto;
        }

        .files-list div {
            font-size: 12px;
            margin-bottom: 4px;
        }

        .file-link {
            color: #e5e7eb;
            text-decoration: none;
        }

        .file-link:hover {
            text-decoration: underline;
        }

        .badge {
            display: inline-block;
            font-size: 10px;
            border-radius: 999px;
            padding: 2px 6px;
            margin-right: 4px;
        }

        .badge-cad  { background: #1f2937; color: #e5e7eb; }
        .badge-pdf  { background: #991b1b; color: #fee2e2; }
        .badge-step { background: #065f46; color: #a7f3d0; }
        .badge-dxf  { background: #a16207; color: #fef3c7; }
        .badge-other{ background: #4b5563; color: #e5e7eb; }

        .preview-frame {
            padding: 0;
        }

        iframe.pdf-frame {
            border: none;
            width: 100%;
            height: 100%;
        }

        .muted {
            color: #9ca3af;
            font-size: 12px;
        }

        .bom-tree {
            font-size: 12px;
        }

        .bom-node {
            margin-left: 12px;
        }

        .bom-row {
            display: flex;
            align-items: center;
            gap: 4px;
            cursor: default;
        }

        .bom-toggle {
            width: 12px;
            text-align: center;
            cursor: pointer;
            font-size: 11px;
            color: #9ca3af;
        }

        .bom-toggle.empty {
            visibility: hidden;
        }

        .bom-item-tag {
            font-family: "JetBrains Mono", Consolas, monospace;
            font-size: 11px;
        }

        .bom-qty {
            color: #9ca3af;
            font-size: 11px;
        }

        .bom-child {
            margin-left: 16px;
            border-left: 1px dashed #1f2937;
            padding-left: 8px;
            margin-top: 2px;
        }

        .bom-item-link {
            color: #e5e7eb;
            text-decoration: none;
        }

        .bom-item-link:hover {
            text-decoration: underline;
        }

        .state-pill {
            font-size: 10px;
            padding: 2px 6px;
            border-radius: 999px;
            border: 1px solid #1e293b;
            margin-left: 4px;
            color: #9ca3af;
        }

        .state-pill.Design   { border-color: #1d4ed8; color: #bfdbfe; }
        .state-pill.Released { border-color: #16a34a; color: #bbf7d0; }
        .state-pill.Unknown  { border-color: #4b5563; color: #e5e7eb; }

        .footer-row {
            padding: 2px 14px 8px;
            font-size: 11px;
            color: #6b7280;
        }
    </style>
</head>
<body>
<div class="app">
    <div class="sidebar">
        <h1>PDM Browser</h1>
        <div class="search-box">
            <input id="searchBox" placeholder="Search item, description..." />
        </div>
        <div id="itemList" class="list"></div>
    </div>

    <div class="content">
        <div class="item-main">
            <div>
                <h2 id="itemTitle">Select an item…</h2>
                <div id="itemMeta" class="item-meta-line"></div>
            </div>
        </div>

        <div class="content-body">
            <div class="panel">
                <div class="panel-title">Files</div>
                <div id="fileList" class="panel-body files-list"></div>
            </div>
            <div class="panel">
                <div class="panel-title">Preview</div>
                <div id="previewContainer" class="panel-body preview-frame">
                    <p class="muted">Select a PDF or STEP file to preview. Other files will open in a new tab.</p>
                </div>
            </div>
        </div>

        <div class="content-body" style="grid-template-columns: 1fr; height: 40vh;">
            <div class="panel">
                <div class="panel-title">Bill of Materials (Recursive)</div>
                <div id="bomTree" class="panel-body bom-tree">
                    <p class="muted">Select an item with a BOM (assembly) to view child components.</p>
                </div>
            </div>
        </div>

        <div class="footer-row">
            Served from D:\PDM_Vault — start server with: <code>python -m http.server 8080</code> in <code>D:\PDM_Vault</code>, then visit <code>http://localhost:8080/Web/index.html</code>.
        </div>
    </div>
</div>

<script>
// -------------------------
// Data from SQLite
// -------------------------
const ITEMS = __ITEMS_JSON__;
const FILES = __FILES_JSON__;
const BOM   = __BOM_JSON__;

// Build maps for quick lookup
const ITEM_BY_ID = {};
ITEMS.forEach(it => {
    ITEM_BY_ID[it.item_number] = it;
});

// Group files by item_number
const FILES_BY_ITEM = {};
FILES.forEach(f => {
    if (!FILES_BY_ITEM[f.item_number]) FILES_BY_ITEM[f.item_number] = [];
    FILES_BY_ITEM[f.item_number].push(f);
});

// Group BOM rows by parent
const BOM_BY_PARENT = {};
BOM.forEach(row => {
    if (!BOM_BY_PARENT[row.parent_item]) BOM_BY_PARENT[row.parent_item] = [];
    BOM_BY_PARENT[row.parent_item].push(row);
});

// -------------------------
// Utilities
// -------------------------
function escapeHtml(s) {
    return String(s ?? "").replace(/[&<>"]/g, c => (
        { "&":"&amp;","<":"&lt;",">":"&gt;" }[c]
    ));
}

function fileTypeBadgeClass(ft) {
    switch (ft) {
        case "CAD":   return "badge badge-cad";
        case "PDF":   return "badge badge-pdf";
        case "STEP":  return "badge badge-step";
        case "DXF":   return "badge badge-dxf";
        default:      return "badge badge-other";
    }
}

function relPathFromVault(fullPath) {
    // Expect like: D:\PDM_Vault\...
    if (!fullPath) return "#";
    const norm = fullPath.replace(/\\\\/g, "\\");
    const m = norm.match(/^[A-Za-z]:\\PDM_Vault\\(.*)$/i);
    let rel = m ? m[1] : fullPath;
    rel = rel.replace(/\\/g, "/");
    if (!rel.startsWith("/")) rel = "/" + rel;
    return rel;
}

// -------------------------
// Item list + selection
// -------------------------
let currentItem = null;

function renderItemList(filterText = "") {
    const listEl = document.getElementById("itemList");
    const ft = filterText.toLowerCase();
    let html = "";

    const sorted = [...ITEMS].sort((a, b) => a.item_number.localeCompare(b.item_number));

    sorted.forEach(it => {
        const haystack = (it.item_number + " " + (it.description || "") + " " + (it.name || "")).toLowerCase();
        if (ft && !haystack.includes(ft)) return;

        const activeClass = (currentItem && currentItem.item_number === it.item_number) ? "item-row active" : "item-row";

        html += `
<div class="${activeClass}" onclick="selectItem('${it.item_number}')">
  <div class="item-row-main">${escapeHtml(it.item_number)}</div>
  <div class="item-row-sub">
    ${escapeHtml(it.description || it.name || "") || "<span class='muted'>No description</span>"}
  </div>
</div>`;
    });

    listEl.innerHTML = html || "<p class='muted'>No items match this search.</p>";
}

function selectItem(itemNumber) {
    currentItem = ITEM_BY_ID[itemNumber];
    if (!currentItem) return;

    // Header
    document.getElementById("itemTitle").textContent = currentItem.item_number;

    const metaEl = document.getElementById("itemMeta");
    const state = currentItem.lifecycle_state || "Unknown";

    metaEl.innerHTML = `
        Rev ${escapeHtml(currentItem.revision)}.${escapeHtml(currentItem.iteration)} 
        &mdash; <span class="muted">State:</span> 
        <span class="state-pill ${escapeHtml(state)}">${escapeHtml(state)}</span>
        ${currentItem.description ? " &mdash; " + escapeHtml(currentItem.description) : ""}
    `;

    // Files list + clear preview
    renderFilesForItem(itemNumber);
    document.getElementById("previewContainer").innerHTML =
        "<p class='muted'>Select a PDF or STEP file to preview. Other files will open in a new tab.</p>";

    // BOM tree
    renderBomTree(itemNumber);

    // Re-render list to highlight active
    const searchVal = document.getElementById("searchBox").value;
    renderItemList(searchVal);
}

// -------------------------
// Files + preview
// -------------------------
function renderFilesForItem(itemNumber) {
    const flist = FILES_BY_ITEM[itemNumber] || [];
    const el = document.getElementById("fileList");
    if (!flist.length) {
        el.innerHTML = "<p class='muted'>No files recorded for this item.</p>";
        return;
    }

    let html = "";
    flist.forEach(f => {
        const badgeClass = fileTypeBadgeClass(f.file_type);
        const url = relPathFromVault(f.file_path);

        // Click handlers for PDF/STEP preview
        let onclick = "";
        if (f.file_type === "PDF") {
            onclick = `onclick="previewPdf('${encodeURIComponent(url)}'); return false;"`;
        } else if (f.file_type === "STEP") {
            onclick = `onclick="previewStep('${encodeURIComponent(url)}'); return false;"`;
        }

        html += `
<div>
  <span class="${badgeClass}">${escapeHtml(f.file_type)}</span>
  <a class="file-link" href="${url}" target="_blank" ${onclick}>
    ${escapeHtml(f.file_path)}
  </a>
</div>`;
    });

    el.innerHTML = html;
}

function previewPdf(encodedUrl) {
    const url = decodeURIComponent(encodedUrl);
    const container = document.getElementById("previewContainer");
    container.innerHTML = `
<iframe class="pdf-frame" src="${url}"></iframe>
`;
}

function previewStep(encodedUrl) {
    const url = decodeURIComponent(encodedUrl);
    const container = document.getElementById("previewContainer");
    container.innerHTML = `
<p class="muted" style="padding:8px;">
  STEP file selected: <code>${escapeHtml(url)}</code><br>
  Use your CAD tool to open it from the server path, or download via the Files list.
</p>
`;
}

// -------------------------
// Recursive BOM tree
// -------------------------
function renderBomTree(itemNumber) {
    const container = document.getElementById("bomTree");
    const rows = BOM_BY_PARENT[itemNumber];

    if (!rows || !rows.length) {
        container.innerHTML = "<p class='muted'>No BOM data for this item. It may be a part, not an assembly.</p>";
        return;
    }

    // Deduplicate/aggregate already handled in SQL, but we'll be safe
    const uniqueRows = {};
    rows.forEach(r => {
        const key = r.child_item;
        if (!uniqueRows[key]) uniqueRows[key] = { child_item: r.child_item, quantity: r.quantity };
    });

    let html = `<div class="bom-root">
        <div class="bom-row">
            <span class="bom-item-tag">${escapeHtml(itemNumber)}</span>
        </div>
    </div>`;

    html += `<div class="bom-child">`;
    const visited = new Set();
    visited.add(itemNumber);

    Object.values(uniqueRows).forEach(r => {
        html += buildBomSubtree(itemNumber, r.child_item, r.quantity, visited);
    });

    html += `</div>`;

    container.innerHTML = html;
}

function buildBomSubtree(parent, childItem, qty, visited) {
    const childNorm = String(childItem);
    const hasChildren = !!BOM_BY_PARENT[childNorm] && BOM_BY_PARENT[childNorm].length > 0;
    const itemInfo = ITEM_BY_ID[childNorm] || null;
    const state = itemInfo ? (itemInfo.lifecycle_state || "Unknown") : "Unknown";
    const desc  = itemInfo ? (itemInfo.description || itemInfo.name || "") : "";

    const safeChild = escapeHtml(childNorm);
    const safeDesc  = escapeHtml(desc);
    const safeQty   = escapeHtml(qty);

    const toggleClass = hasChildren ? "bom-toggle" : "bom-toggle empty";
    const stateClass  = "state-pill " + escapeHtml(state);

    let html = `<div class="bom-node">
  <div class="bom-row">
    <span class="${toggleClass}" onclick="toggleBomChildren(this)">+</span>
    <span class="bom-item-tag">
      <a href="javascript:void(0)" class="bom-item-link" onclick="selectItem('${safeChild}')">${safeChild}</a>
    </span>
    <span class="bom-qty">×${safeQty}</span>
    <span class="${stateClass}">${escapeHtml(state)}</span>
    ${desc ? `<span class="muted">— ${safeDesc}</span>` : ""}
  </div>
`;

    if (hasChildren && !visited.has(childNorm)) {
        visited.add(childNorm);
        html += `<div class="bom-child" style="display:none;">`;

        // aggregate children again for subtree
        const rows = BOM_BY_PARENT[childNorm];
        const uniq = {};
        rows.forEach(r => {
            const key = r.child_item;
            if (!uniq[key]) uniq[key] = { child_item: r.child_item, quantity: r.quantity };
        });

        Object.values(uniq).forEach(r => {
            html += buildBomSubtree(childNorm, r.child_item, r.quantity, visited);
        });

        html += `</div>`;
        visited.delete(childNorm);
    }

    html += `</div>`;
    return html;
}

function toggleBomChildren(toggleEl) {
    const container = toggleEl.parentElement.nextElementSibling;
    if (!container) return;
    const visible = container.style.display !== "none";
    container.style.display = visible ? "none" : "block";
    toggleEl.textContent = visible ? "+" : "–";
}

// -------------------------
// Search wiring
// -------------------------
document.getElementById("searchBox").addEventListener("input", (e) => {
    const v = e.target.value || "";
    renderItemList(v);
});

// Initial render
renderItemList();
</script>
</body>
</html>
'@

# -----------------------------
# Inject JSON into template
# -----------------------------
# Make sure JSON is plain strings
$itemsJsonString = $itemsJson
$filesJsonString = $filesJson
$bomJsonString   = $bomJson

$html = $htmlTemplate.
    Replace("__ITEMS_JSON__", $itemsJsonString).
    Replace("__FILES_JSON__", $filesJsonString).
    Replace("__BOM_JSON__",   $bomJsonString)

# Write as UTF-8 to avoid weird characters
[System.IO.File]::WriteAllText($outputPath, $html, [System.Text.Encoding]::UTF8)

Write-Log "PDM HTML Browser generated at $outputPath"
Write-Host "PDM HTML Browser generated at $outputPath"
