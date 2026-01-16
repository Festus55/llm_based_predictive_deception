#!/bin/bash

# get dir where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[*] Starting Honeypot Services..."

# canarytokens-docker
CANARY_DIR="${SCRIPT_DIR}/canarytokens-docker"

if [ -d "$CANARY_DIR" ]; then
    echo "[*] Checking Canarytokens Docker..."
    cd "$CANARY_DIR"

    # Check if containers are already running
    if sudo docker compose ps --quiet 2>/dev/null | grep -q .; then
        echo "[+] Canarytokens Docker is already running"
    else
        echo "[*] Starting Canarytokens Docker..."
        sudo docker compose up -d
        echo "[+] Canarytokens Docker started"
    fi
    cd "$SCRIPT_DIR"
else
    echo "[! ] Warning: canarytokens-docker directory not found at $CANARY_DIR"
fi

# start the cowrie log ingester in bg
LOG_INGESTER="${SCRIPT_DIR}/mongoDB/save-log-cowrie.py"
if [ -f "$LOG_INGESTER" ]; then
    echo "[*] Starting Cowrie Log Ingester..."

    pkill -f "python.*save-log-cowrie.py" 2>/dev/null || true
    nohup python3 "$LOG_INGESTER" &
    INGESTER_PID=$!
    echo "[+] Cowrie Log Ingester started (PID: $INGESTER_PID)"
else
    echo "[!] Warning: save-log-cowrie.py not found at $LOG_INGESTER"
fi

# start the webhook listener in fg
echo "[*] Starting Webhook Listener on port 9000..."
exec gunicorn -w 4 -b 0.0.0.0:9000 --access-logfile - --error-logfile - listener9000:app
