FROM python:3.12-slim

WORKDIR /app

# System deps (kept minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
  && rm -rf /var/lib/apt/lists/*

# Install Python deps first (better cache)
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy source
COPY src /app/src
COPY scripts /app/scripts
COPY config.yml /app/config.yml
COPY sources_allowlist.yml /app/sources_allowlist.yml
COPY SPEC.md /app/SPEC.md

# Make package importable
ENV PYTHONPATH=/app/src

# Default command (override per-service in compose)
CMD ["python", "scripts/run_backtest.py"]
