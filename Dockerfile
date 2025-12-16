FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY config.yml ./

# Set Python path
ENV PYTHONPATH=/app/src

# Create data and models directories
RUN mkdir -p /app/data /app/models

CMD ["python", "scripts/deploy_pipeline.py", "--loop", "--sleep-seconds", "3600"]
