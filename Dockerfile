FROM node:22-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/ ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS backend
WORKDIR /app/backend
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./

FROM python:3.12-slim
WORKDIR /app

COPY --from=frontend-builder /app/frontend/dist /app/static
COPY --from=backend /app/backend /app/backend
COPY --from=backend /usr/local/lib/python3.12 /usr/local/lib/python3.12
COPY --from=backend /usr/local/bin/python /usr/local/bin/python
COPY --from=backend /usr/local/bin/uvicorn /usr/local/bin/uvicorn
COPY alembic.ini ./

ENV PYTHONPATH=/app/backend
ENV STATIC_PATH=/app/static
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

CMD alembic upgrade head && \
    uvicorn app.main:app --host 0.0.0.0 --port 8080 --app-dir backend
