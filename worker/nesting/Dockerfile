FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for Shapely (libgeos)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgeos-dev \
    && rm -rf /var/lib/apt/lists/*

COPY worker/nesting/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY worker/nesting/ .

CMD ["python", "nest_worker.py"]
