# CreoJS Development Agent

## Purpose
This document is a comprehensive reference for building, debugging, and repairing CreoJS applications that run inside PTC Creo Parametric's embedded browser. It covers the architecture, API, patterns from our existing codebase, and integration with our PDM web system.

---

## 1. Architecture Overview

### What is CreoJS?
CreoJS (introduced in Creo 4.0) is PTC's JavaScript toolkit that runs inside Creo Parametric. It uses a **Chrome V8 JavaScript engine** (ECMAScript 2018) running **inside the Creo process**, eliminating the inter-process communication overhead of the older Web.Link approach.

CreoJS supports **all Web.Link APIs** plus additional features.

### Two-Context Model
Every CreoJS application is a **distributed application** with two execution contexts:

```
+-----------------------------------+     +-----------------------------------+
|  BROWSER CONTEXT                  |     |  CREO CONTEXT                     |
|  (Embedded Chromium Browser)      |     |  (V8 Engine inside Creo process)  |
|                                   |     |                                   |
|  - HTML/CSS/DOM manipulation      | <-> |  - pfcSession, pfcModel, etc.     |
|  - Standard JavaScript            | JSON|  - File operations on CAD models   |
|  - fetch(), XMLHttpRequest        |     |  - Creo Toolkit APIs              |
|  - <script> tags (normal)         |     |  - <script type="text/creojs">    |
+-----------------------------------+     +-----------------------------------+
```

**Critical rule:** The two contexts **cannot exchange direct object references**. They communicate by passing **JSON-serializable data** only. All cross-context calls are **asynchronous** and return **Promises**.

### File Locations
- **CreoJS runtime files:** `C:\Program Files\PTC\Creo 10.0.0.0\Common Files\apps\creojs\creojsweb\`
- **Our apps:** `J:\PDM-Web\Local_Creo_Files\creowebjs_apps\`
- **Apps must include** `creojs.js` and optionally `browser.creojs` from the same directory

---

## 2. Application Structure

### Minimal CreoJS App
```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>My CreoJS App</title>
    <!-- REQUIRED: Core CreoJS bridge library -->
    <script src="creojs.js"></script>
    <!-- OPTIONAL: Browser-to-Creo callback bridge -->
    <script type="text/creojs" src="browser.creojs"></script>

    <!-- Creo-context functions (runs in V8 inside Creo) -->
    <script type="text/creojs">
        function myCreoFunction(param1) {
            var session = pfcGetCurrentSession();
            // ... Creo API calls ...
            return {result: "some JSON-serializable data"};
        }
    </script>
</head>
<!-- Initialize AFTER CreoJS scripts are loaded -->
<body onload="CreoJS.$ADD_ON_LOAD(initialize)">
    <div id="output"></div>

    <!-- Browser-context code (runs in Chromium) -->
    <script>
        function initialize() {
            // Called after all CreoJS scripts are loaded
            CreoJS.myCreoFunction("hello")
                .then(function(result) {
                    document.getElementById('output').textContent = result;
                })
                .catch(function(err) {
                    alert('Error: ' + err);
                });
        }
    </script>
</body>
</html>
```

### Required Files in App Directory
| File | Required | Purpose |
|------|----------|---------|
| `creojs.js` | YES | Core CreoJS library - Promise bridge between browser and Creo |
| `browser.creojs` | Recommended | Enables calling browser functions FROM Creo context |
| `creojsbridge.js` | Optional | Alternative JSBridge caller (module-based approach) |
| `*.html` | YES | Your application page(s) |

### Script Types
| Script Tag | Execution Context | Purpose |
|------------|------------------|---------|
| `<script>` | Browser (Chromium) | Standard JS - DOM, fetch, UI logic |
| `<script type="text/creojs">` | Creo (V8 engine) | Creo API calls - models, sessions, files |
| `<script type="text/creojs" src="file.creojs">` | Creo (V8 engine) | External Creo-context script |

**Important:** Use `.creojs` extension for external Creo-context scripts, NOT `.js`. The `.js` extension may not load properly due to OS file type associations.

---

## 3. Initialization Patterns

### Pattern A: Using $ADD_ON_LOAD (Recommended)
```html
<body onload="CreoJS.$ADD_ON_LOAD(initialize)">
<script>
    function initialize() {
        // Safe to call CreoJS functions here
        CreoJS.myFunction().then(handleResult);
    }
</script>
```

### Pattern B: Load Event with Detection
```javascript
window.addEventListener('load', function() {
    if (typeof CreoJS !== 'undefined') {
        // Running inside Creo
        setTimeout(loadCreoData, 500); // Small delay for init
    } else {
        // Running standalone in browser
        loadMockData();
    }
});
```

### Pattern C: Lifecycle Hooks
```javascript
// Run after all CreoJS scripts loaded
CreoJS.$ADD_ON_LOAD(function() { /* init */ });

// Run before page unloads (cleanup)
CreoJS.$ADD_ON_UNLOAD(function() { /* cleanup */ });

// Run if WebSocket connection drops
CreoJS.$ADD_ON_DISCONNECT(function() { /* handle disconnect */ });
```

---

## 4. PFC API Reference (Creo Toolkit Classes)

These are the core Creo API objects available inside `<script type="text/creojs">` blocks. They follow the PFC (Pro/TOOLKIT Foundation Classes) naming convention from J-Link.

### 4.1 Session (`pfcGetCurrentSession()`)

The entry point to all Creo operations.

```javascript
var session = pfcGetCurrentSession();
```

#### Key Session Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `GetCurrentDirectory()` | String | Current working directory path |
| `ChangeDirectory(path)` | void | Change working directory |
| `GetActiveModel()` | Model | Currently active/displayed model |
| `GetCurrentModel()` | Model | Current model in session |
| `RetrieveModel(descriptor)` | Model | Load model into session (no window) |
| `RetrieveModelWithOpts(descriptor, opts)` | Model | Load model with options |
| `OpenFile(filename)` | void | Retrieve + create window + display (convenience) |
| `GetModel(name, type)` | Model | Get model already in session by name and type |
| `GetModelFromDescr(descriptor)` | Model | Get model in session by descriptor |
| `GetModelFromFileName(filename)` | Model | Get model by filename (name.ext format) |
| `CreateModelWindow(model)` | Window | Create/get window for model |
| `GetModelWindow(model)` | Window/null | Get existing window for model |
| `ListFiles(pattern, listOpt, path)` | String[] | List files matching pattern |
| `ListModels()` | Models | List all models in session |
| `ListModelsByType(type)` | Models | List models of specific type |
| `ListWindows()` | Windows | List all open windows |
| `CreatePart(name, ...)` | Part | Create a new part |
| `CreateAssembly(name, ...)` | Assembly | Create a new assembly |

### 4.2 Model Descriptor (`pfcModelDescriptor`)

Creates a reference to a model for retrieval operations.

```javascript
// Create descriptor for a specific model
var descr = pfcModelDescriptor.Create(modelType, filename, "");
// Parameters: (ModelType, filename_with_extension, genericName)

// Alternative: create from full filename
var descr = pfcModelDescriptor.CreateFromFileName(filename);
```

### 4.3 Model Types (`pfcModelType`)

| Constant | Description | File Extension |
|----------|-------------|----------------|
| `pfcModelType.MDL_PART` | Part file | `.prt` |
| `pfcModelType.MDL_ASSEMBLY` | Assembly file | `.asm` |
| `pfcModelType.MDL_DRAWING` | Drawing file | `.drw` |
| `pfcModelType.MDL_MFG` | Manufacturing | `.mfg` |
| `pfcModelType.MDL_LAYOUT` | Layout | `.lay` |

### 4.4 File List Options (`pfcFileListOpt`)

| Constant | Description |
|----------|-------------|
| `pfcFileListOpt.FILE_LIST_LATEST` | List only latest version of each file |
| `pfcFileListOpt.FILE_LIST_INSTANCES` | List instances |
| `pfcFileListOpt.FILE_LIST_NO_DEPENDENCY` | Exclude dependencies |

### 4.5 Model Object Methods

Once you have a Model object (from `RetrieveModel`, `GetActiveModel`, etc.):

#### Properties
| Property/Method | Returns | Description |
|----------------|---------|-------------|
| `FileName` | String | Filename with extension (e.g., "part1.prt") |
| `FullName` | String | Full model name |
| `Type` | ModelType | Model type enum |
| `GetOrigin()` | String | File location on disk |
| `GetIsModified()` | boolean | Modified since last save? |
| `GetDescr()` | ModelDescriptor | Get model's descriptor |
| `GetCommonName()` | String | PDM-style display name |

#### File Operations
| Method | Returns | Description |
|--------|---------|-------------|
| `Save()` | void | Save model to disk |
| `Backup(descriptor)` | void | Backup to different location |
| `Rename(newName)` | void | Rename the model |
| `Copy(newName)` | void | Copy the model file |
| `Delete()` | void | Remove from memory AND disk |
| `Erase()` | void | Remove from session only (not disk) |
| `EraseWithDependencies()` | void | Erase model and its dependencies |
| `Display()` | void | Display model in its window |

#### Parameters
| Method | Returns | Description |
|--------|---------|-------------|
| `GetParam(name)` | Parameter | Get parameter by name |
| `ListParams()` | Parameters | List all parameters |
| `CreateParam(name, value)` | Parameter | Create new parameter |

#### Relations
| Method | Returns | Description |
|--------|---------|-------------|
| `GetRelations()` | String[] | Get model relations |
| `SetRelations(relations)` | void | Set model relations |
| `DeleteRelations()` | void | Delete all relations |

#### Dependencies
| Method | Returns | Description |
|--------|---------|-------------|
| `ListDependencies()` | Dependencies | First-level model dependencies |
| `ListDeclaredModels()` | ModelDescriptors | First-level declared objects |

#### Items & Features
| Method | Returns | Description |
|--------|---------|-------------|
| `GetItemByName(type, name)` | ModelItem | Get item by name |
| `ListItems(type)` | ModelItems | List items by type |

#### Views
| Method | Returns | Description |
|--------|---------|-------------|
| `ListViews()` | Views | List all views |
| `GetCurrentView()` | View | Get current view |

#### Action Listeners
| Method | Returns | Description |
|--------|---------|-------------|
| `AddActionListener(listener)` | void | Add event listener |
| `RemoveActionListener(listener)` | void | Remove event listener |

#### Import/Export
| Method | Returns | Description |
|--------|---------|-------------|
| `Export(filename, exportData)` | void | Export model |
| `ExportIntf3D(filename, type, profile)` | void | 3D interface export |
| `Import(filePath, importData)` | void | Import file into model |

### 4.6 Type Checking (CreoJS-specific)

```javascript
// Check if object is instance of a class (including parent classes)
model.isInstanceOf("pfcAssembly")  // returns boolean

// Get the class name
model.getClassName()  // returns string like "pfcPart"
```

### 4.7 Session Storage (CreoJS-specific)

Persist data across page navigations within the same Creo session:

```javascript
saveToSession("myKey", myValue);
var value = getFromSession("myKey");
removeFromSession("myKey");
```

### 4.8 File I/O (CreoJS-specific)

Requires `web_link_file_read: YES` in `config.pro`:

```javascript
var content = readFileAsString("C:\\path\\to\\file.txt");
writeFileAsString("C:\\path\\to\\file.txt", "content");
```

### 4.9 HTTP Operations (CreoJS-specific)

```javascript
// Upload/Download
uploadFile(url, filePath, responseHandler);
downloadFile(url, filePath, responseHandler);
uploadJSON(url, jsonObject, responseHandler);
downloadJSON(url, responseHandler);
uploadString(url, stringValue, responseHandler);
downloadString(url, responseHandler);
```

### 4.10 Built-in Web Server (CreoJS-specific)

Start a web server inside the Creo process:

```javascript
startWebServer(port);        // -1 for auto port
isWebServerStarted();        // boolean
getWebServerPort();          // number
stopWebServer();

// HTTP handlers
addServerHandler(path, function(req, resp) {
    resp.writeHead(200, "OK", {"Content-Type": "application/json"});
    resp.write(JSON.stringify({status: "ok"}));
    resp.end();
}, RequestMethod.GET);

// WebSocket handlers
addWebSocketServerHandler(path, {
    dataHandler: function(conn, msg) { /* handle message */ },
    openHandler: function(conn) { /* connection opened */ },
    closeHandler: function(conn) { /* connection closed */ },
    errorHandler: function(conn, msg) { /* error */ }
});
```

### 4.11 Module System (CreoJS-specific)

```javascript
// Load modules (NodeJS-like require)
var myModule = require("mymodule");     // searches current dir, then script path
forgetRequired("mymodule");             // clear cache for one module
forgetAllRequired();                    // clear all cached modules

// Script path info
getScriptPath();     // array of search folders
getScriptFolder();   // full path to script directory
getScripts();        // array of script names
```

### 4.12 AppData Operations (CreoJS-specific)

```javascript
saveToAppData("settings.json", JSON.stringify(data));
var data = JSON.parse(getFromAppData("settings.json"));
deleteFromAppData("settings.json");
existsAppData("settings.json");   // boolean

// Folder paths
getAppDataFolder();
getLocalAppDataFolder();
getCreojsAppDataFolder();
```

### 4.13 Utility

```javascript
print(message);           // Send message to browser console
help("pfcSession");       // Open help window for a type
help("pfcModel.Save");    // Open help for specific method
```

---

## 5. Our Existing CreoJS Applications

### 5.1 workspace.html (Main Workspace Tool)
**Location:** `J:\PDM-Web\Local_Creo_Files\creowebjs_apps\workspace.html`
**Purpose:** Workspace comparison tool for syncing CAD files with PDM vault

**Creo-context functions:**
- `getWorkspaceFiles()` - Lists .prt, .asm, .drw files in working directory
- `openFileInCreo(filename)` - Opens a model in Creo without closing other windows

**Browser-context features:**
- File table with sort, search, filter (PRT/ASM/DRW)
- Bulk select and open
- Check-in to vault via Local PDM Services (localhost:8083)
- Download from vault
- Vault comparison via DATASERVER:8082
- Debug console toggle
- Standalone mock data mode

**Currently connects to legacy services:**
- `http://DATASERVER:8082/api/compare-filelist` - Vault comparison (PowerShell)
- `http://localhost:8083/api/checkin` - Local file copy service (PowerShell)
- `http://localhost:8083/api/download` - Vault download service (PowerShell)
- `http://dataserver:3000/pdm-browser.html` - PDM browser link

**Web PDM Migration notes:**
These endpoints need to be updated to point to the new web-based PDM system (FastAPI backend + Supabase). The workspace.html will need to call the new API endpoints instead.

### 5.2 creo_bulk_renumber.html
**Purpose:** Bulk rename parts/assemblies/drawings while maintaining assembly references

**Creo-context functions:**
- `getWorkingDirectory()` - Returns current directory
- `listAllModels()` - Lists all .prt, .asm, .drw in working directory
- `performBulkRename(renameData)` - Multi-step rename process:
  1. Opens ALL assemblies in session (maintains references)
  2. For each rename: opens model, opens matching drawing, renames both
  3. Saves all assemblies (locks in new references)
  4. Closes all models

### 5.3 active_model_name.html
**Purpose:** Displays the filename of the currently active model
**Pattern:** Minimal example of CreoJS initialization and function call

### 5.4 open_matching_drawing.html
**Purpose:** Opens the matching .drw file for the active part/assembly
**Pattern:** Uses older direct Web.Link style (no CreoJS bridge, direct `pfcGetCurrentSession()`)

---

## 6. Critical Development Patterns & Gotchas

### 6.1 Window Management (THE BIG ONE)

**NEVER** set `session.CurrentModel` when opening multiple files. It closes other windows!

```javascript
// BAD - Closes other windows!
session.CurrentModel = model;
model.Display();
window.Activate();

// GOOD - Keeps all windows open
var model = session.RetrieveModel(descr);
var win = session.GetModelWindow(model);
if (win == null) {
    win = session.CreateModelWindow(model);
}
// Do NOT set CurrentModel or activate!
```

### 6.2 Async Call Pattern

All CreoJS calls from browser context are async:

```javascript
// CORRECT - Using Promise .then()
CreoJS.myFunction(param1, param2)
    .then(function(result) {
        // Process result
    })
    .catch(function(err) {
        // Handle error
    });

// CORRECT - Using async/await (if browser supports it)
async function doWork() {
    try {
        const result = await CreoJS.myFunction(param1, param2);
        // Process result
    } catch (err) {
        // Handle error
    }
}
```

### 6.3 Return Values Must Be JSON-Serializable

```javascript
// Creo-context function
function getModelInfo() {
    var session = pfcGetCurrentSession();
    var model = session.GetActiveModel();

    // GOOD - Return plain objects/arrays/strings/numbers
    return {
        filename: model.FileName,
        type: model.Type.toString(),
        modified: model.GetIsModified()
    };

    // BAD - Cannot return Creo objects directly
    // return model;  // Will fail!
}
```

### 6.4 Error Handling Pattern

```javascript
// Creo-context: Always wrap in try/catch
function safeOperation(filename) {
    try {
        var session = pfcGetCurrentSession();
        var descr = pfcModelDescriptor.Create(
            pfcModelType.MDL_PART, filename, ""
        );
        var model = session.RetrieveModel(descr);
        return {success: true, data: model.FileName};
    } catch (e) {
        return {success: false, error: e.toString()};
    }
}

// Browser-context: Handle both Promise rejection and error objects
CreoJS.safeOperation("part.prt")
    .then(function(result) {
        if (result.success) {
            // Use result.data
        } else {
            debugLog('Failed: ' + result.error, 'error');
        }
    })
    .catch(function(err) {
        debugLog('Exception: ' + err.message, 'error');
    });
```

### 6.5 File Type Detection

```javascript
function getModelType(filename) {
    var ext = filename.toLowerCase().split('.').pop();
    switch (ext) {
        case 'prt': return pfcModelType.MDL_PART;
        case 'asm': return pfcModelType.MDL_ASSEMBLY;
        case 'drw': return pfcModelType.MDL_DRAWING;
        default: return null;
    }
}
```

### 6.6 Bulk Operations Require Delays

When performing bulk operations (opening many files, renaming), add small delays:

```javascript
for (const file of files) {
    const result = await CreoJS.openFileInCreo(file.filename);
    // Small delay between operations - Creo needs breathing room
    await new Promise(resolve => setTimeout(resolve, 100));
}
```

### 6.7 Standalone Detection (Dual-Mode Apps)

Apps can work both inside Creo and in a regular browser for testing:

```javascript
if (typeof CreoJS !== 'undefined') {
    // Running inside Creo - use real APIs
    CreoJS.getWorkspaceFiles().then(processFiles);
} else {
    // Running standalone - use mock data
    loadMockData();
}
```

### 6.8 Path Handling

Creo returns Windows paths with backslashes. When using them in URLs:

```javascript
// Convert Creo paths for URL use
var urlPath = creoPath.replace(/\\/g, '/');
var fileUrl = 'file:///' + urlPath;
```

---

## 7. UI Design Standards

Based on our existing apps, CreoJS apps should follow these conventions:

- **Font:** Segoe UI, 11-13px for body text
- **Style:** Clean, compact, professional (like Windchill/PLM systems)
- **Spacing:** Tight (4-8px padding)
- **Colors:** Gray/white palette, blue accents (#4a90e2)
- **Status colors:** Green (#28a745) = OK, Red (#dc3545) = Modified, Yellow (#ffc107) = Warning, Gray (#6c757d) = Not in vault
- **Table design:** Grid layout, sticky headers, resizable columns
- **Fonts for filenames:** Monospace (Consolas, Monaco)
- **Debug console:** Dark theme, fixed bottom, toggle button

---

## 8. Integration with PDM Web System

### Current Architecture (Legacy)
```
workspace.html (in Creo)
    ├── CreoJS API → Creo session (file listing, opening)
    ├── HTTP → DATASERVER:8082 (PowerShell compare service)
    ├── HTTP → localhost:8083 (PowerShell local file service)
    └── HTTP → dataserver:3000 (Legacy Node.js PDM browser)
```

### Target Architecture (Web Migration)
```
workspace.html (in Creo)
    ├── CreoJS API → Creo session (file listing, opening)
    ├── HTTP → [backend-url]/api/files/compare (FastAPI)
    ├── HTTP → localhost:8083 (Local file service - still needed)
    └── HTTP → [frontend-url] (Vue.js PDM browser)
```

The local PowerShell service on localhost:8083 will likely still be needed for local file operations (copy files to/from the local workspace), since the web backend cannot access the local filesystem. However, vault comparison should move to the FastAPI backend.

### API Endpoints to Update in workspace.html
1. **Vault comparison:** `DATASERVER:8082/api/compare-filelist` → FastAPI backend endpoint
2. **PDM Browser link:** `dataserver:3000/pdm-browser.html` → Vue frontend URL
3. **Check-in:** May need to route through FastAPI for Supabase storage upload
4. **Download:** May need signed URLs from Supabase storage

---

## 9. Common Tasks & Recipes

### List All Open Models
```javascript
// Creo-context
function listOpenModels() {
    var session = pfcGetCurrentSession();
    var models = session.ListModels();
    var result = [];
    if (models != null) {
        for (var i = 0; i < models.Count; i++) {
            var m = models.Item(i);
            result.push({
                filename: m.FileName,
                type: m.Type.toString(),
                modified: m.GetIsModified()
            });
        }
    }
    return result;
}
```

### Get Active Model Parameters
```javascript
// Creo-context
function getModelParameters() {
    var session = pfcGetCurrentSession();
    var model = session.GetActiveModel();
    if (!model) return {error: "No active model"};

    var params = model.ListParams();
    var result = [];
    if (params != null) {
        for (var i = 0; i < params.Count; i++) {
            var p = params.Item(i);
            result.push({
                name: p.GetName(),
                value: p.GetValue()
            });
        }
    }
    return {filename: model.FileName, parameters: result};
}
```

### Save All Modified Models
```javascript
// Creo-context
function saveAllModified() {
    var session = pfcGetCurrentSession();
    var models = session.ListModels();
    var saved = [];
    var errors = [];

    if (models != null) {
        for (var i = 0; i < models.Count; i++) {
            var m = models.Item(i);
            if (m.GetIsModified()) {
                try {
                    m.Save();
                    saved.push(m.FileName);
                } catch (e) {
                    errors.push({file: m.FileName, error: e.toString()});
                }
            }
        }
    }
    return {saved: saved, errors: errors};
}
```

### Get BOM (Bill of Materials) from Assembly
```javascript
// Creo-context
function getAssemblyBOM(filename) {
    var session = pfcGetCurrentSession();
    var descr = pfcModelDescriptor.Create(pfcModelType.MDL_ASSEMBLY, filename, "");
    var model = session.RetrieveModel(descr);

    if (!model) return {error: "Could not retrieve model"};

    var deps = model.ListDependencies();
    var bom = [];

    if (deps != null) {
        for (var i = 0; i < deps.Count; i++) {
            var dep = deps.Item(i);
            bom.push({
                filename: dep.FileName,
                type: dep.Type.toString()
            });
        }
    }
    return {assembly: filename, components: bom};
}
```

### Open File and Matching Drawing
```javascript
// Creo-context
function openWithDrawing(filename) {
    var session = pfcGetCurrentSession();
    var results = [];

    // Determine model type
    var ext = filename.toLowerCase().split('.').pop();
    var modelType;
    if (ext === 'prt') modelType = pfcModelType.MDL_PART;
    else if (ext === 'asm') modelType = pfcModelType.MDL_ASSEMBLY;
    else return {error: "Not a part or assembly"};

    try {
        // Open the model
        var descr = pfcModelDescriptor.Create(modelType, filename, "");
        var model = session.RetrieveModel(descr);
        var win = session.GetModelWindow(model);
        if (win == null) win = session.CreateModelWindow(model);
        results.push({action: "opened", file: filename});

        // Try to open matching drawing
        var baseName = filename.replace(/\.[^.]+$/, "");
        var drwName = baseName + ".drw";
        try {
            var drwDescr = pfcModelDescriptor.Create(pfcModelType.MDL_DRAWING, drwName, "");
            var drw = session.RetrieveModel(drwDescr);
            var drwWin = session.GetModelWindow(drw);
            if (drwWin == null) drwWin = session.CreateModelWindow(drw);
            results.push({action: "opened_drawing", file: drwName});
        } catch (e) {
            results.push({action: "no_drawing", file: drwName});
        }
    } catch (e) {
        results.push({action: "error", file: filename, error: e.toString()});
    }

    return results;
}
```

---

## 10. Debugging

### Debug Console Pattern
All our apps include a toggleable debug console:

```html
<button class="debug-toggle" onclick="toggleDebug()">Debug Console</button>
<div class="debug-console" id="debugConsole"></div>

<script>
function debugLog(message, level) {
    level = level || 'info';
    var console = document.getElementById('debugConsole');
    var line = document.createElement('div');
    line.className = 'debug-line ' + level;
    var timestamp = new Date().toLocaleTimeString('en-US', {hour12: false});
    line.innerHTML = '<span class="timestamp">[' + timestamp + ']</span>' + message;
    console.appendChild(line);
    console.scrollTop = console.scrollHeight;
}
</script>
```

### CreoJS Built-in Debugging
```javascript
// In Creo-context scripts:
print("Debug message");  // Sends to browser

// In browser-context:
help("pfcSession");           // Opens help for type
help("pfcModel.Save");        // Opens help for method
```

### Common Issues

| Problem | Cause | Fix |
|---------|-------|-----|
| "Not connected to Creo" | Page opened in normal browser | Use mock data fallback |
| Functions undefined | CreoJS not initialized yet | Use `$ADD_ON_LOAD` |
| Windows closing on open | Setting `session.CurrentModel` | Use `CreateModelWindow` only |
| .js files not loading | OS file association issue | Use `.creojs` extension |
| Data not passing | Returning Creo objects | Return plain JSON objects |
| Operations slow | No delays between bulk ops | Add 100ms delays |
| Path errors | Backslash in URLs | Replace `\\` with `/` |

---

## 11. Configuration

### config.pro Settings for CreoJS
```
web_link_file_read YES          # Enable local file read/write
web_link_file_write YES         # Enable local file write
web_enable_javascript YES       # Enable JavaScript in browser
browser_favorite <name> <url>   # Add browser bookmark
```

### creo_js_app.conf (Optional)
Configures script search paths and app settings. Located in the CreoJS loadpoint or referenced in `config.pro`.

---

## 12. PTC Documentation References

- [CreoJS Scripts](https://support.ptc.com/help/creo_toolkit/creojs_plus/usascii/creo_toolkit/user_guide/Creo_JS_Scripts.html)
- [Overview of CreoJS](https://support.ptc.com/help/creo_toolkit/creojs_plus/usascii/creo_toolkit/user_guide/Overview_of_Creo_JS.html)
- [Working with CreoJS](https://support.ptc.com/help/creo_toolkit/creojs_plus/usascii/creo_toolkit/user_guide/Working_with_Creo_JS.html)
- [CreoJS Application](https://support.ptc.com/help/creo_toolkit/creojs_plus/usascii/creo_toolkit/user_guide/Creo_JS_Application.html)
- [Calling CreoJS from Browser Code](https://support.ptc.com/help/creo_toolkit/creojs_plus/usascii/creo_toolkit/user_guide/Calling_Creo_JS_Code_from_Browser_Code.html)
- [Additional API Features](https://support.ptc.com/help/creo_toolkit/creojs_plus/usascii/creo_toolkit/user_guide/Additional_API_Features_Introduced_in_Creo_JS.html)
- [pfcModel Interface (Java OTK)](https://support.ptc.com/help/creo_toolkit/otk_java_plus/usascii/creo_toolkit/api/dita/c-pfcModel-Model.html)
- [pfcBaseSession Interface](https://support.ptc.com/help/creo_toolkit/otk_java_plus/usascii/creo_toolkit/api/dita/c-pfcSession-BaseSession.html)
- [pfcSession Class (C++ OTK)](https://support.ptc.com/help/creo_toolkit/otk_cpp_pma/r11.0/usascii/creo_toolkit/api/dita/t-pfcSession-Session.html)

---

## 13. Limitations & Things I Don't Know

> **Transparency note:** The following areas have limited documentation available. Do NOT hallucinate APIs or behavior for these. Ask the user or test empirically.

1. **Assembly component manipulation** - Adding/removing components from assemblies via CreoJS. The API likely mirrors J-Link's `pfcComponentFeat` but exact CreoJS behavior is unverified.

2. **Feature creation** - Creating new features (extrudes, cuts, rounds, etc.) programmatically. This is available in J-Link/C Toolkit but the exact CreoJS API surface is not fully documented in what I've reviewed.

3. **Drawing view manipulation** - Creating/modifying drawing views, adding dimensions, annotations. Likely available but not confirmed in CreoJS context.

4. **Notification/event system** - The full set of events that can be listened to via `AddActionListener`. J-Link supports many event types but CreoJS coverage is uncertain.

5. **Manufacturing objects** - MFG model manipulation via CreoJS is not documented in sources reviewed.

6. **Family table operations** - Instance/generic manipulation patterns in CreoJS are not confirmed.

7. **Mapkey execution** - Running Creo mapkeys from CreoJS is not documented in reviewed sources.

8. **Exact iteration methods** - Some collection objects in Creo may use `.Count`/`.Item(i)` while others use `.length`/array indexing or `.getarraysize()`/`.get(i)`. The exact API depends on the Creo version and whether the object is a CIP sequence or a JS array (see `setCIPSequenceHandler`).

When in doubt, use `help("className")` inside the CreoJS execution toolbar to look up available methods, or test in the CreoJS debugger.
