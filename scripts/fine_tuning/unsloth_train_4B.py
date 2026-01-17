from unsloth import FastModel
import torch
import os
from unsloth.chat_templates import get_chat_template, train_on_responses_only
from datasets import load_dataset
from trl import SFTTrainer, SFTConfig
import builtins
if not hasattr(builtins, "VARIANT_KWARG_KEYS"):
    builtins.VARIANT_KWARG_KEYS = ["adapter_name"]

model, tokenizer = FastModel.from_pretrained(
    model_name = "unsloth/gemma-3-4b-pt-unsloth-bnb-4bit",  
    max_seq_length = 1024,
    load_in_4bit = True,
    load_in_8bit = False,
    full_finetuning = False,
    token = os.environ["HF_TOKEN"],
)

model = FastModel.get_peft_model(
    model,
    finetune_vision_layers     = False,
    finetune_language_layers   = True,
    finetune_attention_modules = True,
    finetune_mlp_modules       = True,

    r = 16,
    lora_alpha = 32,
    lora_dropout = 0.05,
    bias = "none",
    random_state = 3407,
)

tokenizer = get_chat_template(
    tokenizer,
    chat_template = "gemma-3",
)

data = load_dataset(
    "json",
    data_files={
        "train": "train_final.jsonl",
        "validation": "val_final.jsonl",
    },
)

#tr_dataset = data["train"]
#ev_dataset  = data["validation"]
#train_dataset = tr_dataset.select(range(2000))# possible shrinking of both eval and training datasets to run tests
#eval_dataset  = ev_dataset.select(range(500))
train_dataset = data["train"]
eval_dataset  = data["validation"]

trainer = SFTTrainer(
    model = model,
    tokenizer = tokenizer,
    train_dataset = train_dataset,
    eval_dataset  = eval_dataset,
    args = SFTConfig(
        output_dir="outputs_4b",         
        save_strategy="steps",
        save_steps=1500,
        save_total_limit=3,
        dataset_text_field = "text",
        per_device_train_batch_size = 2,
        gradient_accumulation_steps = 4,
        warmup_steps = 5,
        num_train_epochs = 1,
        max_steps = -1,
        learning_rate = 2e-4,
        logging_steps = 1,
        optim = "adamw_8bit",
        weight_decay = 0.001,
        lr_scheduler_type = "linear",
        seed = 3407,
        report_to = "none",
        eval_strategy="steps",
        eval_steps=1000,
    ),
)

trainer = train_on_responses_only(
    trainer,
    instruction_part = "<start_of_turn>user\n",
    response_part = "<start_of_turn>model\n",
)

gpu_stats = torch.cuda.get_device_properties(0)
start_gpu_memory = round(torch.cuda.max_memory_reserved() / 1024 / 1024 / 1024, 3)
max_memory = round(gpu_stats.total_memory / 1024 / 1024 / 1024, 3)
print(f"GPU = {gpu_stats.name}. Max memory = {max_memory} GB.")
print(f"{start_gpu_memory} GB of memory reserved.")

trainer_stats = trainer.train()

used_memory = round(torch.cuda.max_memory_reserved() / 1024 / 1024 / 1024, 3)
used_memory_for_lora = round(used_memory - start_gpu_memory, 3)
used_percentage = round(used_memory / max_memory * 100, 3)
lora_percentage = round(used_memory_for_lora / max_memory * 100, 3)
print(f"{trainer_stats.metrics['train_runtime']} seconds used for training.")
print(f"{round(trainer_stats.metrics['train_runtime']/60, 2)} minutes used for training.")
print(f"Peak reserved memory = {used_memory} GB.")
print(f"Peak reserved memory for training = {used_memory_for_lora} GB.")
print(f"Peak reserved memory % of max memory = {used_percentage} %.")
print(f"Peak reserved memory for training % of max memory = {lora_percentage} %.")

model.save_pretrained("gemma-3-4b")
tokenizer.save_pretrained("gemma-3-4b")

