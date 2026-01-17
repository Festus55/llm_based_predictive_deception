#@title prepare batch
from google.cloud import storage
import json

# --- CONFIG ---
# inside the current colab dir
INPUT_LOCAL_FILE = 'train.json' 

# GCS placed files
PROJECT_ID = "gruppo2-russo"
BUCKET_NAME = "grupporusso2_dataset_bucket"
GCS_OUTPUT_PATH = "input/train.jsonl" # bucket path

# -----------------------
# PROMPTS (from local colab dir files)
# -----------------------
with open("trap_intent_prompt.md", "r", encoding="utf-8") as f:
    SYSTEM_PROMPT = f.read()

with open("usertask.txt", "r", encoding="utf-8") as f:
    TASK_INSTRUCTIONS = f.read()

FULL_SYSTEM_PROMPT = f"""
## SYSTEM PROMPT 
ONLY
"{SYSTEM_PROMPT}"

## PROCESSING INSTRUCTIONS
ONLY task instructions and json instance
"{TASK_INSTRUCTIONS}"
"""


def stream_to_gcs():
    print(f"Connecting to GCS(Project: {PROJECT_ID})...")
    
    # client GCS init (colab enterprise)
    storage_client = storage.Client(project=PROJECT_ID)
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(GCS_OUTPUT_PATH)

    try:
        print(f"local file read: {INPUT_LOCAL_FILE}")
        with open(INPUT_LOCAL_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"Loaded {len(data)} objs.")
    except Exception as e:
        print(f"Error local file read: {e}")
        return

    print(f"Starting to stream on gs://{BUCKET_NAME}/{GCS_OUTPUT_PATH} ...")

    # STREAM GCS OPENING
    with blob.open("w", encoding="utf-8") as f_out:
        
        valid_lines = 0
        
        for index, item in enumerate(data):
            try:
                item_str = json.dumps(item, ensure_ascii=False)
                full_text_input = f"{SYSTEM_PROMPT}\n\n{item_str}"

                batch_line = {
                    "request": {
                        "contents": [
                            {"role": "user", "parts": [{"text": full_text_input}]}
                        ],
                        "generationConfig": {
                            "temperature": 0.25,
                            "top_p": 0.9,
                            "responseMimeType": "application/jsonl"
                        }
                    }
                }

                jsonl_line = json.dumps(batch_line, ensure_ascii=False)
                f_out.write(jsonl_line + "\n")
                
                valid_lines += 1

                # 10k lines feedback
                if index % 10000 == 0:
                    print(f"{index} lines written on Google Cloud Storage...", end='\r')

            except Exception as e:
                print(f"\nError occurred at line {index}: {e}")

    print(f"\n\nStreaming completed")
    print(f"The file is ready at: gs://{BUCKET_NAME}/{GCS_OUTPUT_PATH}")
    print(f"Total lines: {valid_lines}")

if __name__ == "__main__":
    stream_to_gcs()