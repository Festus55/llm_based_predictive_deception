#!/bin/bash

set -euo pipefail

# ============================================================================
# Dataset processing timeline to prepare it for Gemma 3 LoRA
# ============================================================================

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATASET_DIR="${PROJECT_ROOT}/../../dataset"
ENRICHED_DIR="${DATASET_DIR}/enriched_data"
TRAINING_DIR="${DATASET_DIR}/training_data"
WORK_DIR="${DATASET_DIR}/work_tmp"

# Input file
INPUT_FILE="${ENRICHED_DIR}/training_set.json"

# Ensure directories exist
mkdir -p "$WORK_DIR"
mkdir -p "$TRAINING_DIR"

echo "Launching Honeypot Dataset Processing Pipeline"
echo "========================================"
echo "PROJECT_ROOT: $PROJECT_ROOT"
echo "WORK_DIR: $WORK_DIR"
echo "INPUT_FILE: $INPUT_FILE"
echo ""

# ============================================================================
# STEP 1: Split dataset (training_set.json → clean_train.json, clean_val.json)
# ============================================================================
echo "1/8: Splitting dataset..."

if [ ! -f "$INPUT_FILE" ]; then
  echo "Input file not found: $INPUT_FILE"
  exit 1
fi

SPLIT_TRAIN="${WORK_DIR}/split_train.json"
SPLIT_VAL="${WORK_DIR}/split_val.json"

# Se split.py esiste, lo runi. Altrimenti assumi che i file siano già stati splittati
if [ -f "${PROJECT_ROOT}/split.py" ]; then
  python3 "${PROJECT_ROOT}/split.py" \
  --in "$INPUT_FILE" \
  --out-train "$SPLIT_TRAIN" \
  --out-val "$SPLIT_VAL" \
  --val-frac 0.1 \
  --seed 42
  echo "Split completed: split_train.json, split_val.json"
else
  echo "split.py not found. Assuming split_train.json and split_val.json exist."
fi

# ============================================================================
# STEP 2: Convert JSON to JSONL format
# ============================================================================
echo ""
echo "2/8: Converting to JSONL format..."

TRAIN_JSONL="${WORK_DIR}/train.jsonl"
VAL_JSONL="${WORK_DIR}/val.jsonl"

python3 "${PROJECT_ROOT}/parse_toJSONL.py" \
  --in "$SPLIT_TRAIN" \
  --out "$TRAIN_JSONL" \
  --format text \
  --fix-output-3

python3 "${PROJECT_ROOT}/parse_toJSONL.py" \
  --in "$SPLIT_VAL" \
  --out "$VAL_JSONL" \
  --format text \
  --fix-output-3

echo "JSONL files generated: train.jsonl, val.jsonl"

# ============================================================================
# STEP 3: Format to prompt/completion
# ============================================================================
echo ""
echo "3/8: Formatting prompt/completion..."

TRAIN_PC="${WORK_DIR}/train_prompt_completion.jsonl"
VAL_PC="${WORK_DIR}/val_prompt_completion.jsonl"

# Render prompt_completition_format.py parametrico
python3 "${PROJECT_ROOT}/prompt_completition_format.py" "$VAL_JSONL" "$VAL_PC"
python3 "${PROJECT_ROOT}/prompt_completition_format.py" "$TRAIN_JSONL" "$TRAIN_PC"

echo "Prompt/completion files generated: train_prompt_completion.jsonl, val_prompt_completion.jsonl"

# ============================================================================
# STEP 4: Sanitize base64 payloads
# ============================================================================
echo ""
echo "4/8: Sanitizing base64 payloads..."

TRAIN_B64="${WORK_DIR}/train_prompt_completion_sanitized.jsonl"
VAL_B64="${WORK_DIR}/val_prompt_completion_sanitized.jsonl"

python3 "${PROJECT_ROOT}/sanitizer_B64.py" \
  --in "$TRAIN_PC" \
  --out "$TRAIN_B64" \
  --mode prompt_completion \
  --min_len 80

python3 "${PROJECT_ROOT}/sanitizer_B64.py" \
  --in "$VAL_PC" \
  --out "$VAL_B64" \
  --mode prompt_completion \
  --min_len 80

echo "Base64 sanitization completed"

# ============================================================================
# STEP 5: Sanitize hex sequences
# ============================================================================
echo ""
echo "5/8: Sanitizing hex sequences..."

TRAIN_HEX="${WORK_DIR}/train_prompt_completion_sanitized_hex.jsonl"
VAL_HEX="${WORK_DIR}/val_prompt_completion_sanitized_hex.jsonl"

python3 "${PROJECT_ROOT}/sanitizer_hex.py" \
  --in "$TRAIN_B64" \
  --out "$TRAIN_HEX" \
  --mode prompt_completion \
  --min_bytes 80

python3 "${PROJECT_ROOT}/sanitizer_hex.py" \
  --in "$VAL_B64" \
  --out "$VAL_HEX" \
  --mode prompt_completion \
  --min_bytes 80

echo "Hex sanitization completed"

# ============================================================================
# STEP 6: Collapse consecutive hex tokens
# ============================================================================
echo ""
echo "6/8: Collapsing hex token runs..."

TRAIN_COLLAPSED="${WORK_DIR}/train_prompt_completion_sanitized_hex_collapsed.jsonl"
VAL_COLLAPSED="${WORK_DIR}/val_prompt_completion_sanitized_hex_collapsed.jsonl"

python3 "${PROJECT_ROOT}/collapse_hx.py" \
  --in "$TRAIN_HEX" \
  --out "$TRAIN_COLLAPSED" \
  --mode prompt_completion

python3 "${PROJECT_ROOT}/collapse_hx.py" \
  --in "$VAL_HEX" \
  --out "$VAL_COLLAPSED" \
  --mode prompt_completion

echo "Hex collapse completed"

# ============================================================================
# STEP 7: Transform to final chat format (prompt/completion → text format)
# ============================================================================
echo ""
echo "7/8: Transforming to final chat format..."

TRAIN_FINAL="${TRAINING_DIR}/train.json"
VAL_FINAL="${TRAINING_DIR}/val.json"

python3 "${PROJECT_ROOT}/parse_fromPC_toText.py" "$TRAIN_COLLAPSED" "$TRAIN_FINAL"
python3 "${PROJECT_ROOT}/parse_fromPC_toText.py" "$VAL_COLLAPSED" "$VAL_FINAL"

echo "Final transformation completed"

# ============================================================================
# STEP 8: Cleanup intermediate files
# ============================================================================
echo ""
echo "8/8: Cleaning up intermediate files..."

rm -f \
  "$SPLIT_TRAIN" \
  "$SPLIT_VAL" \
  "$TRAIN_JSONL" \
  "$VAL_JSONL" \
  "$TRAIN_PC" \
  "$VAL_PC" \
  "$TRAIN_B64" \
  "$VAL_B64" \
  "$TRAIN_HEX" \
  "$VAL_HEX" \
  "$TRAIN_COLLAPSED" \
  "$VAL_COLLAPSED"

echo "Cleanup completed"

# ============================================================================
# FINAL SUMMARY
# ============================================================================
echo ""
echo "++++++++++ PIPELINE COMPLETED ++++++++++"
echo "========================================"
echo "Final output files:"
echo "  ${TRAINING_DIR}/train_final.jsonl"
echo "  ${TRAINING_DIR}/val_final.jsonl"
echo ""
echo "File sizes:"
wc -l "${TRAINING_DIR}"/*.jsonl
echo ""
