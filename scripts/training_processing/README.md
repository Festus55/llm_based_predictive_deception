# Training Data Processing

Data processing pipeline scripts to prepare training data for fine-tuning.

## Scripts

- `run_data_processing.sh` - Main orchestration script for the data pipeline
- `split.py` - Split data into train/val sets
- `parse_toJSONL.py` - Convert data to JSONL format
- `prompt_completition_format.py` - Format prompt/completion pairs
- `sanitizer_B64.py` / `sanitizer_hex.py` - Remove large base64/hex blobs from data
- `collapse_hx.py` - Collapse repeated hex tokens
- `parse_response_toJSON.py` - Parse batch processing responses to JSON
