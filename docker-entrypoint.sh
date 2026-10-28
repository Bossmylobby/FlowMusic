#!/bin/sh
set -e

mkdir -p /app/instance /app/static/music

python -c "from app import init_db; init_db()"

echo "[*] MusicFlow starting on 0.0.0.0:5000"
exec gunicorn app:app \
  --bind 0.0.0.0:5000 \
  --workers 2 \
  --timeout 120 \
  --access-logfile - \
  --error-logfile -