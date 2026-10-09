# ==============================================================================
# Stage 1: Build Telegram Mini App (Frontend)
# ==============================================================================
FROM node:22-alpine AS frontend-builder
WORKDIR /build

COPY webapp/package*.json ./
RUN npm ci || npm install

COPY webapp/ ./
RUN npm run build

# ==============================================================================
# Stage 2: Production Python Backend & Bot Runner
# ==============================================================================
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libjpeg-dev \
    zlib1g-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY app/ ./app/
COPY scripts/ ./scripts/
COPY README.md .

# Copy built frontend assets from builder stage
COPY --from=frontend-builder /build/dist ./webapp/dist

# Create database and uploads directory
RUN mkdir -p /app/data

EXPOSE 8000
VOLUME ["/app/data"]

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["python", "app/main.py"]
