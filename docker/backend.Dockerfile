FROM python:3.10-slim

WORKDIR /app

COPY backend/requirements.txt .

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r requirements.txt

COPY ["backend", "/app/backend"]
COPY ["qdrant_docs", "/app/qdrant_docs"]
COPY ["qdrant docs", "/app/qdrant docs"]
COPY ["docker/backend-entrypoint.sh", "/app/backend-entrypoint.sh"]

RUN chmod +x /app/backend-entrypoint.sh

WORKDIR /app/backend

EXPOSE 8000

CMD ["sh", "/app/backend-entrypoint.sh"]
