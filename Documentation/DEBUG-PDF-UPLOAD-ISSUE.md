# PDF Upload 500 Error - Debug Session (2026-07-16)

## Problem
PDF file uploads fail with "Internal Server Error" (500) while CAD files (.prt, .asm, .step) upload successfully.

## Failed Files (in C:\PDM-Upload\Failed\)
- csp03240.pdf
- csa00085.pdf
- csa00350.pdf
- csp03230.pdf

## Investigation Findings

### What Works
1. **PDF stamping function** (`stamp_pdf_upload_date`) - tested directly, works fine
2. **Supabase storage upload** - tested directly, uploads PDFs successfully
3. **Database insert** - tested directly, inserts file records correctly
4. **Pydantic model validation** - FileInfo schema validates correctly
5. **Full upload function called directly** - works via `asyncio.run()`
6. **Fresh server instance** - PDF upload works on port 8099 (fresh uvicorn)

### What Fails
- PDF uploads via HTTP to port 8001 (running server instance)
- STEP/CAD uploads work fine on the same port 8001

### Root Cause (Likely)
The uvicorn server instance on port 8001 is in a bad state. A fresh server instance (tested on port 8099) successfully uploads the same PDF files that fail on port 8001.

Multiple processes were seen listening on port 8001 at one point, suggesting possible zombie processes or reload issues.

## Solution
**Restart the backend server:**
```bash
# Kill existing server
taskkill /PID <pid> /F
# Or Ctrl+C in the terminal running uvicorn

# Restart
cd backend
python -m uvicorn app.main:app --reload --port 8001
```

## Files Created During Debug (can be cleaned up)
- `csp03240.pdf` and `csp03230.pdf` were uploaded to Supabase storage during testing
- File records may exist in database for test uploads

## After Restart - Verification Steps
1. Check backend is running: `curl http://localhost:8001/health`
2. Test PDF upload: `curl -X POST http://localhost:8001/api/files/upload -F "file=@C:/PDM-Upload/Failed/csa00085.pdf" -F "item_number=csa00085"`
3. If still failing, check uvicorn console for actual traceback
4. Re-upload failed PDFs from C:\PDM-Upload\Failed\
