"""PDM-Web FastAPI Backend."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .routes import (
    items_router,
    files_router,
    bom_router,
    projects_router,
    auth_router,
    tasks_router,
    mrp_router,
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


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "PDM-Web API",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
    )
