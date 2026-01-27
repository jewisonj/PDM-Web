# ==================================================
#   PDM HTML Browser Generator (with 3D STEP & DXF)
#   Vault root fixed at: D:\PDM_Vault
#   Uses sqlite3.exe (no DLLs)
# ==================================================

# --- CONFIG ---
$dbPath   = "D:\PDM_Vault\pdm.sqlite"
$vaultRoot = "D:\PDM_Vault"
$webRoot  = Join-Path $vaultRoot "Web"
$outHtml  = Join-Path $webRoot "index.html"
$sqliteExe = "sqlite3.exe"

if (!(Test-Path $webRoot)) {
    New-Item -ItemType Directory -Path $webRoot | Out-Null
}

Write-Host "Generating PDM HTML Browser..."

# ------------------------------
# Helper: sqlite3 wrapper
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
# Normalize item numbers like:
#   csa0030_img_1 → csa0030
# ------------------------------
function Normalize-ItemNumber {
    param([string]$Item)

    if ([string]::IsNullOrWhiteSpace($Item)) { return $Item }
    $m = [regex]::Match($Item, "^[A-Za-z]{3}\d{4}")
    if ($m.Success) { return $m.Value }
    return $Item
}

# ------------------------------
# Load Items
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

$itemsByKey = @{}

foreach ($row in $rawItems) {
    $p = $row -split '\|', 5
    if ($p.Count -lt 5) { continue }

    $orig  = $p[0]
    $desc  = $p[1]
    $rev   = $p[2]
    $iter  = [int]$p[3]
    $state = $p[4]

    $key = Normalize-ItemNumber $orig

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
        # Optionally merge data here if you need to; for now we keep the first row.
    }
}

# ------------------------------
# Load Files
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

foreach ($row in $rawFiles) {
    $p = $row -split '\|', 5
    if ($p.Count -lt 5) { continue }

    $origItem = $p[0]
    $filePath = $p[1]
    $fileType = $p[2]
    $rev      = $p[3]
    $iter     = [int]$p[4]

    # Skip Archived files from the main view
    if ($filePath -match "\\Archive\\") { continue }

    $key = Normalize-ItemNumber $origItem

    if (-not $itemsByKey.ContainsKey($key)) {
        $itemsByKey[$key] = [PSCustomObject]@{
            item_number = $key
            description = ""
            revision    = $rev
            iteration   = $iter
            state       = "Unknown"
            files       = @()
        }
    }

    $it = $itemsByKey[$key]

    if (($it.files | Where-Object { $_.file_path -eq $filePath }).Count -eq 0) {
        $it.files += [PSCustomObject]@{
            file_type = $fileType
            file_path = $filePath
            revision  = $rev
            iteration = $iter
        }
    }
}

$itemList = $itemsByKey.GetEnumerator() | Sort-Object Name | ForEach-Object { $_.Value }

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

<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&display=swap">

<style>
body {
    background: #020617;
    color: #e5e7eb;
    font-family: Inter, system-ui, sans-serif;
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
}
.right {
    flex: 1;
    padding: 1rem;
    overflow-y: auto;
    box-sizing: border-box;
}
.search-input {
    width: 100%;
    padding: 6px 8px;
    border-radius: 999px;
    border: 1px solid #334155;
    background: #020617;
    color: #e5e7eb;
}
.item {
    padding: 0.45rem;
    margin-top: 0.3rem;
    border: 1px solid #1f2937;
    border-radius: 6px;
    cursor: pointer;
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
.section-title {
    margin-top: 1rem;
    font-size: 0.9rem;
    font-weight: 600;
}
.muted {
    color: #94a3b8;
    font-size: 0.8rem;
}
.file-row {
    margin-bottom: 0.25rem;
    font-size: 0.8rem;
}
button {
    background: #1e293b;
    color: #e5e7eb;
    border: 1px solid #334155;
    padding: 2px 8px;
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.75rem;
}
button:hover {
    border-color: #38bdf8;
    color: #38bdf8;
}
</style>

<!-- STEP 3D & OpenCascade dependencies -->
<script src="https://unpkg.com/three@0.150.0/build/three.min.js"></script>
<script src="https://unpkg.com/three@0.150.0/examples/js/controls/OrbitControls.js"></script>
<script src="https://unpkg.com/occt-import-js/dist/occt-import-js.js"></script>

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
        <div id="stepPreview" style="margin-top:1rem;"></div>
    </div>
</div>

<script>
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

        div.innerHTML =
            "<div><strong>" + escapeHtml(item.item_number) + "</strong></div>" +
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
        html += "<p class='muted'>No files linked to this item.</p>";
    } else {
        files.forEach(f => {
            const fp = (f.file_path || "");
            const lower = fp.toLowerCase();

            // Convert absolute Windows path under D:\PDM_Vault to HTTP path
            let rel = fp.replace(/\\/g, "/");
            rel = rel.replace("D:/PDM_Vault/", "");
            const url = "/" + rel;

            const isPdf  = lower.endsWith(".pdf");
            const isStep = lower.endsWith(".step") || lower.endsWith(".stp");
            const isDxf  = lower.endsWith(".dxf");

            if (isPdf) {
                html += "<div class='file-row'><strong>PDF</strong>: " +
                    "<a href='" + url + "' onclick=\"loadPdfPreview('" + url + "'); return false;\">" +
                    escapeHtml(fp) + "</a></div>";
            }
            else if (isStep) {
                html += "<div class='file-row'><strong>STEP</strong>: " +
                    "<a href='" + url + "' target='_blank'>" + escapeHtml(fp) + "</a>" +
                    " &nbsp; <button onclick=\"loadStepPreview('" + fp.replace(/\\/g, "/") + "')\">View 3D</button>" +
                    "</div>";
            }
            else if (isDxf) {
                html += "<div class='file-row'><strong>DXF</strong>: " +
                    "<a href='" + url + "' target='_blank'>" + escapeHtml(fp) + "</a></div>";
            }
            else {
                html += "<div class='file-row'><strong>" + escapeHtml(f.file_type || "FILE") +
                    "</strong>: <a href='" + url + "' target='_blank'>" +
                    escapeHtml(fp) + "</a></div>";
            }
        });
    }

    document.getElementById("itemDetails").innerHTML = html;
    document.getElementById("pdfPreview").innerHTML = "";
    document.getElementById("stepPreview").innerHTML = "";
}

function loadPdfPreview(url) {
    const panel = document.getElementById("pdfPreview");
    panel.innerHTML =
        "<div class='section-title'>PDF Preview</div>" +
        "<iframe src='" + url + "' width='100%' height='600px' style='border:1px solid #334155; border-radius:6px;'></iframe>";
}

function loadStepPreview(path) {
    const panel = document.getElementById("stepPreview");

    let html = "";
    html += "<div class='section-title'>3D Model Preview</div>";
    html += "<div id='stepCanvas' style='width:100%; height:600px; border:1px solid #334155; border-radius:6px;'></div>";
    html += "<p class='muted'>Rendering… Please wait.</p>";

    panel.innerHTML = html;

    // Convert absolute file path to HTTP path under vault root
    let rel = path.replace(/\\/g, "/");
    rel = rel.replace("D:/PDM_Vault/", "");
    const url = "/" + rel;

    fetch(url)
        .then(r => r.arrayBuffer())
        .then(b => renderStepFromBuffer(b))
        .catch(err => {
            console.error("STEP viewer fetch error:", err);
            let fb = "";
            fb += "<p class='muted'>3D viewer error while loading STEP: " + escapeHtml(String(err)) + "</p>";
            panel.innerHTML = fb;
        });
}

async function renderStepFromBuffer(buffer) {
    const panel = document.getElementById("stepCanvas");
    panel.innerHTML = "";

    let occt;
    try {
        occt = await occtimportjs();
    } catch (e) {
        console.error("Failed to load occt-import-js:", e);
        panel.innerHTML = "<p style='color:red'>Failed to load OpenCascade (occt-import-js).</p>";
        return;
    }

    const data = new Uint8Array(buffer);

    let result;
    try {
        result = occt.readStepFile(data);
    } catch (e) {
        console.error("readStepFile error:", e);
        panel.innerHTML = "<p style='color:red'>Error reading STEP file.</p>";
        return;
    }

    if (!result || !result.meshes || result.meshes.length === 0) {
        console.error("No meshes in STEP result:", result);
        panel.innerHTML = "<p style='color:red'>No mesh data found in STEP file.</p>";
        return;
    }

    const meshData = result.meshes[0];

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(panel.clientWidth, panel.clientHeight);
    panel.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0b1120);

    const camera = new THREE.PerspectiveCamera(
        45,
        panel.clientWidth / panel.clientHeight,
        0.1,
        2000
    );
    camera.position.set(4, 3, 4);

    if (THREE.OrbitControls) {
        const controls = new THREE.OrbitControls(camera, renderer.domElement);
        controls.target.set(0, 0, 0);
        controls.update();
    } else {
        console.warn("THREE.OrbitControls is not available.");
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute(
        "position",
        new THREE.BufferAttribute(meshData.attributes.position.array, 3)
    );
    geometry.setIndex(meshData.index);
    geometry.computeVertexNormals();

    const material = new THREE.MeshStandardMaterial({
        color: 0xcccccc,
        metalness: 0.1,
        roughness: 0.6
    });

    const mesh = new THREE.Mesh(geometry, material);
    scene.add(mesh);

    const light1 = new THREE.DirectionalLight(0xffffff, 1);
    light1.position.set(5, 10, 7);
    scene.add(light1);

    const light2 = new THREE.AmbientLight(0x404040);
    scene.add(light2);

    function animate() {
        requestAnimationFrame(animate);
        renderer.render(scene, camera);
    }
    animate();
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
