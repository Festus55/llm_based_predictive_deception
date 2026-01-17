#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./startup_API_server.sh gemma-3-12b /home/honeypot_leo/models/gemma-3-12b
MODEL_SLUG="${1:?Usage: $0 <MODEL_SLUG> \{gemma-3-12b-pt | gemma-3-4b-pt | gemma-3-4b-it\} <LORA_PATH> \{ /home/honeypot_leo/models/gemma-3-12b |  /home/honeypot_leo/models/gemma-3-4b-pt | /home/honeypot_leo/models/gemma-3-4b-it\ [<IP> default = "192.168.122.1"]}"
LORA_PATH="${2:?Usage: $0 <MODEL_SLUG> \{gemma-3-12b-pt | gemma-3-4b-pt | gemma-3-4b-it\} <LORA_PATH> \{ /home/honeypot_leo/models/gemma-3-12b |  /home/honeypot_leo/models/gemma-3-4b-pt | /home/honeypot_leo/models/gemma-3-4b-it\ [<IP> default = "192.168.122.1"]}"


HOST="192.168.122.1"

if [[ "$#" -eq 3 ]] ; then  HOST="$3" ; fi

PORT="8000"
BASE_MODEL="unsloth/${MODEL_SLUG}-unsloth-bnb-4bit"
API="http://${HOST}:${PORT}"

source ~/venvs/vllm/bin/activate

export VLLM_ALLOW_RUNTIME_LORA_UPDATING=True   # enables /v1/load_lora_adapter 
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

echo "[+] Starting vLLM server: ${BASE_MODEL}"
python -m vllm.entrypoints.openai.api_server \
  --model "${BASE_MODEL}" \
  --served-model-name base \
  --enable-lora \
  --max-lora-rank 16 \
  --chat-template ./gemma3_chat_template.jinja \
  --chat-template-content-format string \
  --max-model-len 8192 \
  --max-num-seqs 4 \
  --gpu-memory-utilization 0.90 \
  --host "${HOST}" \
  --port "${PORT}" \
  > vllm_server.log 2>&1 &

SERVER_PID=$!
echo "[+] Server PID: ${SERVER_PID}"
echo "[+] Logs: ./vllm_server.log"

# Wait until server is up (poll /v1/models for HTTP 200)
echo -n "[+] Waiting for server"
until curl -s -o /dev/null -w "%{http_code}" "${API}/v1/models" | grep -q "^200$"; do
  echo -n "."
  sleep 1
done
echo
echo "[+] Server is up."

echo "[+] Loading LoRA adapter: name=honeypot path=${LORA_PATH}"
curl -sS -X POST "${API}/v1/load_lora_adapter" \
  -H "Content-Type: application/json" \
  --data-binary "{\"lora_name\":\"honeypot\",\"lora_path\":\"${LORA_PATH}\"}"
echo
echo "[+] Done. Use model=\"honeypot\" in /v1/chat/completions."

echo "[+] To stop:"
echo "    kill ${SERVER_PID}"
echo " OR "
echo "    pkill -f "vllm.entrypoints.openai.api_server" || true"
echo "    pkill -f "vllm.entrypoints.openai.apiserver" || true"
echo "    pkill -f "vllm" || true"
