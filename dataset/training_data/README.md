# Training Data

Final training datasets in JSONL format ready for LoRA fine-tuning. Contains train/val splits formatted for Gemma 3 chat template.

## Converting between JSON and JSONL

To convert from JSON to JSONL:
```bash
jq -c '.[]' input.json > output.jsonl
```

To convert from JSONL to JSON:
```bash
jq -s '.' input.jsonl > output.json
```
