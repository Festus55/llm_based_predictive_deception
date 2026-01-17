#@title batch job scheduling
import os
import sys
from google.cloud import storage
from google.cloud import aiplatform
from google.api_core import exceptions

# --- CONFIG ---
PROJECT_ID = "gruppo2-russo"           
REGION = "europe-west4"                  
BUCKET_NAME = "grupporusso2_dataset_bucket"  
GCS_FILENAME = "input/knowledge_distillation_input.jsonl" #gcs prepared file location

# chosen batch processing model 
MODEL_ID = "gemini-2.5-flash" 

def submit_batch_job(input_uri, bucket_name):
    print(f"Batch job preparation with model: {MODEL_ID}...")
    
    try:
        aiplatform.init(project=PROJECT_ID, location=REGION)

        output_uri = f"gs://{bucket_name}/output/"

        job = aiplatform.BatchPredictionJob.create(
            job_display_name=f"batch-process-150k-{MODEL_ID}",
            model_name=f"publishers/google/models/{MODEL_ID}",
            input_dataset=input_uri,
            output_uri_prefix=output_uri,
            instances_format="jsonl",
            predictions_format="jsonl",
        )

        print(f"\nSUCCESFULLY SUBMITTED JOB")
        print(f"Job ID: {job.name}")
        print(f"Status: {job.state.name}")
        print(f"Dashboard URL: https://console.cloud.google.com/vertex-ai/jobs/batch-predictions?project={PROJECT_ID}")
        print(f"Results will be available at: {output_uri}")
        
        return job

    except exceptions.InvalidArgument as e:
        print(f"CONFIG ERROR: Wrong parameters: {e}")
    except exceptions.PermissionDenied:
        print(f"PERMISSION ERROR: Verify Vertex AI is enabled.")
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    gcs_input_uri = f"gs://{BUCKET_NAME}/{GCS_FILENAME}"
    submit_batch_job(gcs_input_uri, BUCKET_NAME)