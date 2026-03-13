# Stage 1: Build React UI
FROM node:20-slim AS ui-builder
WORKDIR /app/ui
COPY ui/package.json ./
RUN npm install
COPY ui/ ./
RUN npm run build

# Stage 2: Python server
FROM python:3.11-slim
WORKDIR /app

# Install package
COPY pyproject.toml ./
COPY hub/ ./hub/
COPY alembic.ini ./

RUN pip install --no-cache-dir -e .

# Copy built UI into hub static directory
COPY --from=ui-builder /app/ui/dist /app/hub/static/ui

# Create data directory for SQLite
RUN mkdir -p /app/data

# Run migrations then start server
CMD ["sh", "-c", "alembic upgrade head && uvicorn hub.main:app --host 0.0.0.0 --port ${AW_PORT:-8000}"]
