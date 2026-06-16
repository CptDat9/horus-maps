# Single backend image. The `api` service runs uvicorn (after `alembic upgrade head`);
# the `worker` service just overrides the command. Build context is the repo root
# (where this Dockerfile, .env and .venv live) so it can copy ./backend.
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

# System libs for OpenCV (pulled in by ultralytics) — slim lacks libGL/glib.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Deps first (layer caching). requirements.txt lives at the repo root.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Backend code (app/, migrations/, alembic.ini, scripts/, run.py ...).
COPY backend/ .

# YOLO-OBB weights for the detection worker. DETECTION_MODEL_PATH points here.
COPY ml/yolo11s-obb.pt /app/models/yolo11s-obb.pt
# Ultralytics writes runtime config/cache here; keep it inside the image.
ENV DETECTION_MODEL_PATH=/app/models/yolo11s-obb.pt \
    YOLO_CONFIG_DIR=/app/.ultralytics

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
