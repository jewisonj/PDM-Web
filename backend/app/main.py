"""PDM-Web FastAPI Backend."""

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .config import get_settings
from .routes import (
    items_router,
    files_router,
    bom_router,
    projects_router,
    auth_router,
    tasks_router,
    mrp_router,
    workspace_router,
    nesting_router,
)

settings = get_settings()

app = FastAPI(
    title="PDM-Web API",
    description="Product Data Management System API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware - allow all origins for internal/Tailnet apps
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.cors_allow_all else settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth_router, prefix="/api")
app.include_router(items_router, prefix="/api")
app.include_router(files_router, prefix="/api")
app.include_router(bom_router, prefix="/api")
app.include_router(projects_router, prefix="/api")
app.include_router(tasks_router, prefix="/api")
app.include_router(mrp_router, prefix="/api")
app.include_router(workspace_router, prefix="/api")
app.include_router(nesting_router, prefix="/api")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


# ============================================
# Static File Serving (Production)
# ============================================
# Serve Vue frontend static files in production
# The static folder is created during Docker build

STATIC_DIR = Path(__file__).parent.parent / "static"

if STATIC_DIR.exists() and (STATIC_DIR / "index.html").exists():
    # Serve static assets (js, css, images)
    if (STATIC_DIR / "assets").exists():
        app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/")
    async def serve_index():
        """Serve Vue SPA index."""
        return FileResponse(STATIC_DIR / "index.html")

    # Catch-all route for SPA - must be last
    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        """Serve Vue SPA for all non-API routes."""
        # Don't intercept API routes
        if full_path.startswith("api/"):
            return {"detail": "Not found"}

        # Try to serve the exact file first
        file_path = STATIC_DIR / full_path
        if file_path.is_file():
            return FileResponse(file_path)

        # Otherwise serve index.html for SPA routing
        return FileResponse(STATIC_DIR / "index.html")
else:
    # No static files - serve API info at root (development mode)
    @app.get("/")
    async def root():
        """Root endpoint."""
        return {
            "name": "PDM-Web API",
            "version": "1.0.0",
            "docs": "/docs",
            "static_dir": str(STATIC_DIR),
            "static_exists": STATIC_DIR.exists()
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
    )
