#!/bin/bash
# CloudDrive startup script
# Runs on port 3167, accessible on the local network (laptop + mobile)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="/home/zukhruf/localserver/.venv/bin/uvicorn"
LOG_FILE="$SCRIPT_DIR/clouddrive.log"

cd "$SCRIPT_DIR"

echo "Starting CloudDrive on port 3167..."
echo "Access from laptop : http://localhost:3167"
echo "Access from mobile : http://$(hostname -I | awk '{print $1}'):3167"
echo "Logs: $LOG_FILE"
echo ""

"$VENV_PYTHON" main:app \
    --host 0.0.0.0 \
    --port 3167 \
    --timeout-keep-alive 120 \
    --forwarded-allow-ips "*"
