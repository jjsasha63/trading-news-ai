FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y build-essential curl && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e . && \
    pip install alpaca-py requests-cache redis

COPY scripts ./scripts
COPY config.yml sources_allowlist.yml run.py Makefile ./

RUN mkdir -p data models logs

EXPOSE 8000
CMD ["python3", "run.py", "scripts/trading/paper_trader.py"]
