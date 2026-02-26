#!/bin/bash
# Deploy spicetrader to Unraid (or any Docker host)
# Usage: ./deploy.sh
#
# Environment variables (set in .env or export before running):
#   DATA_DIR   - host path for the SQLite DB and bot data  (default: ./data)
#   LOGS_DIR   - host path for bot log files               (default: ./logs)
#   UI_HOST    - host interface for the dashboard UI       (default: 127.0.0.1)
#   UI_PORT    - host port for the dashboard UI            (default: 3000)
#   API_HOST   - host interface for the FastAPI backend    (default: 127.0.0.1)
#   API_PORT   - host port for the FastAPI backend         (default: 8000)
#
# Unraid example (.env additions):
#   DATA_DIR=/mnt/user/appdata/spicetrader/data
#   LOGS_DIR=/mnt/user/appdata/spicetrader/logs
#   UI_HOST=0.0.0.0
#   UI_PORT=3033
#   API_HOST=127.0.0.1
#   API_PORT=8000

set -e

# Load .env so compose variables are available to this script too
if [ -f .env ]; then
  export $(grep -v '^#' .env | grep -v '^$' | xargs)
fi

echo "==> Pulling latest changes..."
git pull

echo "==> Stopping existing containers..."
docker compose down --remove-orphans

echo "==> Rebuilding all images (no cache)..."
docker compose build --no-cache

echo "==> Starting all services..."
docker compose up -d

echo ""
echo "==> Deployment complete."
echo "    Dashboard UI : http://$(hostname -I | awk '{print $1}'):${UI_PORT:-3000}"
echo "    API backend  : ${API_HOST:-127.0.0.1}:${API_PORT:-8000} (internal)"
echo ""
echo "==> Container status:"
docker compose ps
