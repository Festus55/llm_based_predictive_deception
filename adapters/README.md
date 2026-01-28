# Adapters

This folder contains fine-tuned LoRA adapters for the Gemma 3 models used in the predictive honeypot system.

## Contents

- `gemma-3-12b-2k/` - LoRA adapter for Gemma 3 12B obtained from a subset of 2000 lines to test if the process was effective 
- `gemma-3-4b/` - LoRA adapter for Gemma 3 4B instruction-tuned model
- `gemma-3-4b-pt/` - LoRA adapter for Gemma 3 4B pretrained model
- `gemma-3-12b/` - LoRA adapter for Gemma 3 12B pretrained model
- `startup_API_server.sh` - Script to start the vLLM inference server with LoRA adapters
- `gemma3_chat_template.jinja` - Chat template for Gemma 3 model inference
