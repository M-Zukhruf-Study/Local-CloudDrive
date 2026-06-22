FROM python:3.12-slim

WORKDIR /app

# System deps kept minimal — this app has no native build requirements.
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY frontend/ ./frontend/
COPY main.py .

# Data directory is meant to be a mounted volume (see docker-compose.yml)
# so uploads survive container rebuilds.
RUN mkdir -p /app/data/storage /app/data/db /app/data/temp_chunks

EXPOSE 8000

# --timeout-keep-alive raised so very large chunk PUTs over a slow link
# don't get killed mid-transfer by an idle keep-alive timeout.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-keep-alive", "120"]
