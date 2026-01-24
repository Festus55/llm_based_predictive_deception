# Batch Processing

Scripts for batch processing SSH command data through Gemini 2.5 Flash on Google Cloud.

## Scripts

- `prepare_batch_gcs_output.py` - Prepare input JSONL and upload to GCS bucket
- `start_batch_work.py` - Submit Vertex AI batch prediction job
- `data_distillation_prompts/` - System prompts and task instructions for trap-intent mapping
