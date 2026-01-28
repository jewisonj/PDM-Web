# PDM-Web Production Dockerfile
# Single container: FastAPI backend + Vue frontend static files

# ============================================
# Stage 1: Build Frontend
# ============================================
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

# Build arguments for Vite (required at build time)
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_ANON_KEY

# Copy package files first for better caching
COPY frontend/package*.json ./

# Install dependencies (npm ci is faster and deterministic with lock file)
RUN npm ci

# Copy frontend source
COPY frontend/ ./

# Build production bundle (skip TypeScript checking, just build with Vite)
ENV VITE_SUPABASE_URL=$VITE_SUPABASE_URL
ENV VITE_SUPABASE_ANON_KEY=$VITE_SUPABASE_ANON_KEY
RUN npx vite build

# ============================================
# Stage 2: Production Backend + Static Files
# ============================================
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend application
COPY backend/app ./app

# Copy built frontend from previous stage
COPY --from=frontend-builder /app/frontend/dist ./static

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run the application
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
