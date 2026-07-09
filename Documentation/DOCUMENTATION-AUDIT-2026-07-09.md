# PDM-Web Documentation Audit Report

**Audit Date:** 2026-07-09
**Auditor:** Documentation Agent
**Current Version:** v3.9.2
**Total Documentation Files:** 34

---

## Executive Summary

The documentation is **largely accurate and well-maintained**. The most critical files (Table of Contents, Version History, Port Configuration) are up to date with version v3.9.2. However, **14 documentation files contain incorrect port references** (8000 instead of 8001), which could cause confusion during setup and troubleshooting.

### Critical Findings

1. **PORT NUMBER ERRORS (High Priority):** 14 docs reference `localhost:8000` instead of `localhost:8001` for backend
2. **README.md OUTDATED (High Priority):** Root README still describes legacy SQLite/PowerShell system instead of web stack
3. **CLAUDE.md PORT ERROR (High Priority):** Main AI instructions reference wrong backend port in startup command
4. **MRP VIEWS PARTIALLY DOCUMENTED (Medium Priority):** 12 MRP views exist but only partially documented
5. **API ENDPOINTS MATCH (Good):** Backend routes align with API documentation

### Overall Health Score: 7/10

- **Strengths:** Version history current, ToC accurate, schema docs good, MRP features well-documented
- **Weaknesses:** Port numbers inconsistent, README outdated, some workflows reference wrong ports

---

## Detailed Findings

### 1. Root-Level Files

#### PORTS.md ✅ ACCURATE
- Correctly documents frontend port 5174
- Correctly documents backend port 8001
- Includes proper proxy configuration
- **Status:** No changes needed

#### CLAUDE.md ❌ NEEDS UPDATE
**Issues Found:**
1. Line 124: `cd backend && uvicorn app.main:app --reload` (missing `--port 8001`)
2. Should reference PORTS.md more prominently

**Recommended Fix:**
```bash
# Wrong
cd backend && uvicorn app.main:app --reload

# Correct
cd backend && uvicorn app.main:app --reload --port 8001
```

#### README.md ❌ SEVERELY OUTDATED
**Issues Found:**
1. Line 7-10: Describes legacy "SQLite-based with PowerShell automation" instead of Supabase
2. Line 13-40: Mentions Node.js web interface instead of Vue 3
3. Line 32-37: Requirements list SQLite, PowerShell 5.1 as primary tech
4. Line 45: Version listed as "v2.0 (2025-01-01)" instead of "v3.9.2 (2026-07-09)"

**Recommended Action:** Complete rewrite to match CLAUDE.md overview

### 2. Port Reference Errors (14 Files)

The following files contain references to `localhost:8000` instead of `localhost:8001`:

| File | Lines with Error | Impact |
|------|-----------------|---------|
| `04-SERVICES-REFERENCE.md` | 120, 178, 201, 208, 224 | High - API examples will fail |
| `17-QUICK-START-CHECKLIST.md` | 87, 94, 179, 230, 264, 267, 344 | High - Setup instructions wrong |
| `20-COMMON-WORKFLOWS.md` | 42, 82, 92 | Medium - Example commands fail |
| `23-SYSTEM-CONFIGURATION.md` | Many examples | Medium - Config examples wrong |
| `13-LOCAL-PDM-SERVICES-GUIDE.md` | Multiple | Low - Bridge config |
| `14-SKILL-DEFINITION.md` | Examples | Low - Reference only |
| `15-DEVELOPMENT-NOTES-WORKSPACE-COMPARISON.md` | Scattered | Low - Historical notes |
| `19-TROUBLESHOOTING-DECISION-TREE.md` | Port check examples | Medium - Debug commands |
| `24-VERSION-HISTORY.md` | Historical examples | Low - Release notes |
| `25-INTEGRATION-EXAMPLES.md` | Code samples | Low - Custom integration |
| `29-NESTING-AUTOMATION.md` | API calls | Low - Worker docs |
| `06-BOM-COST-ROLLUP-GUIDE.md` | Examples | Low - Cost docs |
| `05-POWERSHELL-SCRIPTS-INDEX.md` | Config | Low - Upload bridge |

**Recommended Fix:** Global find-replace `localhost:8000` → `localhost:8001` in all docs

**Exception:** `24-VERSION-HISTORY.md` contains some intentional historical references to 8000 in old release notes. These should be preserved with a note that port changed to 8001 in v3.x.

### 3. Version Number Accuracy ✅ GOOD

Only 2 files reference v3.9.2:
- `00-TABLE-OF-CONTENTS.md` ✅ (line 6)
- `24-VERSION-HISTORY.md` ✅ (line 9)

Other docs are intentionally version-agnostic (no version numbers mentioned).

### 4. Frontend Views Documentation

**Actual Views (19 total):**
```
HomeView.vue
LoginView.vue
NotFoundView.vue
PartNumbersView.vue
PdmBrowserView.vue
WorkQueueView.vue
MrpAssistantView.vue
MrpBuildBookView.vue
MrpBuildTrackerView.vue
MrpCostReportView.vue
MrpCostSettingsView.vue
MrpDashboardView.vue
MrpPartLookupView.vue
MrpPrintLookupView.vue
MrpProjectTrackingView.vue
MrpRawMaterialsView.vue
MrpRoutingView.vue
MrpShopView.vue
```

**Documentation Coverage:**

| View | Documented In | Status |
|------|--------------|--------|
| PDM Views (5) | `10-PDM-WEBSERVER-OVERVIEW.md` | ✅ Good |
| MrpAssistantView | `33-AI-ASSISTANT.md` | ✅ Excellent |
| MrpBuildBookView | `32-BUILD-BOOK.md` | ✅ Excellent |
| MrpBuildTrackerView | `31-BUILD-TRACKER-SHEET.md` | ✅ Excellent |
| MrpProjectTrackingView | `20-COMMON-WORKFLOWS.md` Section 15 | ✅ Good |
| MrpPartLookupView | `20-COMMON-WORKFLOWS.md` Section 13 | ⚠️ Basic |
| MrpRoutingView | `20-COMMON-WORKFLOWS.md` Section 14 | ⚠️ Basic |
| MrpCostReportView | `06-BOM-COST-ROLLUP-GUIDE.md` | ⚠️ Partial |
| MrpCostSettingsView | Not documented | ❌ Missing |
| MrpRawMaterialsView | `waterjet-cutting-speeds.md` | ⚠️ Partial |
| MrpPrintLookupView | Not documented | ❌ Missing |
| MrpShopView | `20-COMMON-WORKFLOWS.md` Section 16 | ⚠️ Basic |
| MrpDashboardView | `20-COMMON-WORKFLOWS.md` | ⚠️ Mentioned only |

**Recommendation:** Create `35-MRP-VIEWS-REFERENCE.md` to document all MRP views in one place with screenshots, workflows, and troubleshooting.

### 5. API Endpoints Verification ✅ MOSTLY ACCURATE

**Backend Routes Exist:**
- `auth.py` ✅ Documented in 04-SERVICES-REFERENCE.md
- `items.py` ✅ Documented
- `files.py` ✅ Documented
- `bom.py` ✅ Documented
- `projects.py` ✅ Documented
- `tasks.py` ✅ Documented
- `workspace.py` ✅ Documented
- `nesting.py` ✅ Documented in 29-NESTING-AUTOMATION.md
- `assistant.py` ✅ Documented in 33-AI-ASSISTANT.md
- `mrp.py` ✅ Documented in 31-BUILD-TRACKER-SHEET.md, 32-BUILD-BOOK.md

**Issue Found:** `04-SERVICES-REFERENCE.md` doesn't list MRP endpoints. Should cross-reference to docs 31/32/33.

### 6. Configuration Files ✅ ACCURATE

**Backend (.env.example):**
- Port correctly set to 8001 ✅
- ANTHROPIC_API_KEY documented ✅
- All variables match config.py ✅

**Frontend (vite.config.ts):**
- Port correctly set to 5174 ✅
- Proxy targets 127.0.0.1:8001 ✅
- SSE timeout config present ✅

**Configuration Documentation:**
- `23-SYSTEM-CONFIGURATION.md` has port 8000 errors but structure is good
- Should add ANTHROPIC_API_KEY to the environment variables table

### 7. Database Schema Documentation ✅ GOOD

`03-DATABASE-SCHEMA.md` accurately reflects:
- 16 tables in Supabase PostgreSQL
- UUID primary keys
- RLS policies mentioned
- Recent additions (assistant_conversations, assistant_approvals) documented in 33-AI-ASSISTANT.md

**Minor Issue:** Doc 03 doesn't mention the latest AI Assistant tables. Should add note to see Doc 33 for assistant_* tables.

### 8. Documentation File Organization ✅ EXCELLENT

Table of Contents (00-TABLE-OF-CONTENTS.md) is:
- Current and accurate ✅
- Well-organized by section ✅
- Includes all 34 docs ✅
- Good navigation by use case ✅
- Development commands correct (except port issue) ⚠️

### 9. Missing Documentation

**Should Be Documented:**
1. **MRP Cost Settings View** - No docs for the pricing/rates configuration UI
2. **Print Lookup View** - Shop terminal print search not documented
3. **Raw Materials Management** - Only cutting speeds doc exists, not the CRUD UI
4. **Deployment Guide Updates** - `09-PDM-WEBSERVER-DEPLOYMENT.md` may be outdated for v3.9

**Nice to Have:**
1. **Video Walkthrough Links** - No video tutorials referenced
2. **Keyboard Shortcuts Reference** - Are there any? Not documented
3. **Browser Compatibility Matrix** - No docs on supported browsers
4. **Performance Benchmarks** - No load time or data volume limits documented

### 10. Python Version Verification

**Actual:** Python 3.14.2
**Documented in 17-QUICK-START-CHECKLIST.md:** "Python 3.10+"

✅ Accurate (3.14.2 satisfies 3.10+ requirement)

---

## Priority Actions

### CRITICAL (Do Immediately)

1. **Fix README.md** - Rewrite to reflect current web stack
2. **Fix CLAUDE.md startup command** - Add `--port 8001`
3. **Global port fix** - Replace `localhost:8000` with `localhost:8001` in high-impact docs:
   - `04-SERVICES-REFERENCE.md`
   - `17-QUICK-START-CHECKLIST.md`
   - `20-COMMON-WORKFLOWS.md`
   - `23-SYSTEM-CONFIGURATION.md`

### HIGH PRIORITY (This Week)

4. **Update 04-SERVICES-REFERENCE.md**
   - Fix all port 8000 → 8001 references
   - Add cross-references to MRP endpoints in docs 31/32/33
   - Add ANTHROPIC_API_KEY to environment variables table

5. **Update 23-SYSTEM-CONFIGURATION.md**
   - Fix port 8000 → 8001 in examples
   - Add ANTHROPIC_API_KEY configuration

### MEDIUM PRIORITY (This Month)

6. **Create 35-MRP-VIEWS-REFERENCE.md** - Comprehensive MRP UI documentation
7. **Update 03-DATABASE-SCHEMA.md** - Add note about assistant_* tables (see Doc 33)
8. **Review 09-PDM-WEBSERVER-DEPLOYMENT.md** - Verify production deployment steps current

### LOW PRIORITY (When Time Permits)

9. **Fix remaining port references** in low-impact docs (05, 06, 13, 14, 15, 19, 25, 29)
10. **Add browser compatibility matrix** to 26-SECURITY-HARDENING.md or new doc
11. **Document keyboard shortcuts** if any exist

---

## Files That Are Accurate (No Changes Needed)

**Excellent Documentation (Keep As-Is):**
- `00-TABLE-OF-CONTENTS.md` ✅
- `PORTS.md` ✅
- `24-VERSION-HISTORY.md` ✅ (except historical port 8000 refs are intentional)
- `31-BUILD-TRACKER-SHEET.md` ✅
- `32-BUILD-BOOK.md` ✅
- `33-AI-ASSISTANT.md` ✅
- `34-AI-ASSISTANT-ROADMAP.md` ✅
- `01-PDM-SYSTEM-MAP.md` ✅
- `02-PDM-COMPLETE-OVERVIEW.md` ✅
- `03-DATABASE-SCHEMA.md` ✅ (minor addition needed)
- `10-PDM-WEBSERVER-OVERVIEW.md` ✅
- `12-FREECAD-AUTOMATION.md` ✅
- `29-NESTING-AUTOMATION.md` ✅ (except port refs)
- `waterjet-cutting-speeds.md` ✅

---

## Recommended Documentation Priorities

### For New Developers
1. Fix README.md (first impression)
2. Fix 17-QUICK-START-CHECKLIST.md ports
3. Ensure 02-PDM-COMPLETE-OVERVIEW.md is current

### For Daily Operations
1. Fix 20-COMMON-WORKFLOWS.md ports
2. Create 35-MRP-VIEWS-REFERENCE.md
3. Document MRP Cost Settings and Print Lookup

### For Troubleshooting
1. Fix 19-TROUBLESHOOTING-DECISION-TREE.md ports
2. Update 04-SERVICES-REFERENCE.md with all current endpoints
3. Add common error messages and solutions

---

## Global Find-Replace Commands

**Safe to run globally across all .md files:**

```bash
# Fix backend port (dev)
find Documentation/ -name "*.md" -exec sed -i 's/localhost:8000/localhost:8001/g' {} \;

# Except: Keep historical references in 24-VERSION-HISTORY.md
# Manual review recommended for that file
```

**Files requiring manual review (not safe for global replace):**
- `24-VERSION-HISTORY.md` - Contains intentional historical port 8000 references in old release notes

---

## Conclusion

The PDM-Web documentation is **in good shape overall** with excellent coverage of recent features (Build Book, Build Tracker, AI Assistant). The main issue is **port number inconsistency** from the migration to port 8001, which affects 14 files.

**Immediate action:** Fix README.md, CLAUDE.md, and the three high-impact docs (04, 17, 20, 23) to prevent new developers from hitting port errors during setup.

**Next steps:** Create MRP Views Reference doc and fill in the missing documentation for Cost Settings and Print Lookup views.

**Maintenance:** The documentation agent should perform this audit quarterly or after major releases.

---

**Audit Complete**
**Next Audit Due:** 2026-10-09 (3 months) or after v4.0 release
