#!/usr/bin/env bash
set -euo pipefail
mkdir -p "${DATA_DIR:-/var/data}" "${HF_HOME:-/var/data/huggingface}"
LLAMA_HOST="${LLAMA_HOST:-127.0.0.1}"
LLAMA_PORT="${LLAMA_PORT:-8080}"
LOCAL_MODEL="${LOCAL_MODEL:-Qwen/Qwen2.5-0.5B-Instruct-GGUF:Q4_K_M}"
MODEL_ALIAS="${MODEL_NAME:-neura-local}"
MODEL_CONTEXT="${MODEL_CONTEXT:-4096}"
MODEL_THREADS="${MODEL_THREADS:-2}"
echo "Avvio del motore locale NÈURA: ${LOCAL_MODEL}"
/opt/llama/bin/llama-server -hf "${LOCAL_MODEL}" --alias "${MODEL_ALIAS}" --host "${LLAMA_HOST}" --port "${LLAMA_PORT}" -c "${MODEL_CONTEXT}" -t "${MODEL_THREADS}" -np 1 --no-webui > "${DATA_DIR:-/var/data}/llama-server.log" 2>&1 &
LLAMA_PID=$!
cleanup(){ kill "$LLAMA_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
echo "Avvio dell'applicazione web NÈURA"
exec uvicorn app:app --host 0.0.0.0 --port "${PORT:-10000}"
