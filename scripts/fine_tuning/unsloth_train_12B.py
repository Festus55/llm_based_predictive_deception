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
    model_name = "unsloth/gemma-3-12b-pt-unsloth-bnb-4bit",
    max_seq_length = 1024, # Choose any for long context!
    load_in_4bit = True,  # 4 bit quantization to reduce memory
    load_in_8bit = False, # [NEW!] A bit more accurate, uses 2x memory
    full_finetuning = False, # [NEW!] We have full finetuning now!
    token = os.environ["HF_TOKEN"], # hugging face token as an environment os var
)

model = FastModel.get_peft_model(
    model,
    finetune_vision_layers     = False, # Turn off for just text!
    finetune_language_layers   = True,  # Should leave on!
    finetune_attention_modules = True,  # Attention good for GRPO
    finetune_mlp_modules       = True,  # SHould leave on always!

    r = 16,           # Larger = higher accuracy, but might overfit
    lora_alpha = 32,  # Recommended alpha == r at least
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
        "train": "train.jsonl",
        "validation": "val.jsonl",
    },
)

tr_dataset = data["train"]
ev_dataset  = data["validation"]
train_dataset = tr_dataset
eval_dataset  = ev_dataset # possible shrinking of both eval and training datasets to run tests

trainer = SFTTrainer(
    model = model,
    tokenizer = tokenizer,
    train_dataset = train_dataset,
    eval_dataset  = eval_dataset,
    args = SFTConfig(
        output_dir="outputs",
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
    # max stepts to None -> Full set (shrinkened before if needed for a test) 
    # train_steps = train_length/8, eval_steps=train_steps/num_evals (es. I want 5 eval on 250 train steps, eval_steps=50)
)

trainer = train_on_responses_only(
    trainer,
    instruction_part = "<start_of_turn>user\n",
    response_part = "<start_of_turn>model\n",
)

#tokenizer.decode(trainer.train_dataset[100]["input_ids"]) #debug
#tokenizer.decode([tokenizer.pad_token_id if x == -100 else x for x in trainer.train_dataset[100]["labels"]]).replace(tokenizer.pad_token, " ") #debug

# Show current memory stats
gpu_stats = torch.cuda.get_device_properties(0)
start_gpu_memory = round(torch.cuda.max_memory_reserved() / 1024 / 1024 / 1024, 3)
max_memory = round(gpu_stats.total_memory / 1024 / 1024 / 1024, 3)
print(f"GPU = {gpu_stats.name}. Max memory = {max_memory} GB.")
print(f"{start_gpu_memory} GB of memory reserved.")

trainer_stats = trainer.train()

# Show final memory and time stats
used_memory = round(torch.cuda.max_memory_reserved() / 1024 / 1024 / 1024, 3)
used_memory_for_lora = round(used_memory - start_gpu_memory, 3)
used_percentage = round(used_memory / max_memory * 100, 3)
lora_percentage = round(used_memory_for_lora / max_memory * 100, 3)
print(f"{trainer_stats.metrics['train_runtime']} seconds used for training.")
print(
    f"{round(trainer_stats.metrics['train_runtime']/60, 2)} minutes used for training."
)
print(f"Peak reserved memory = {used_memory} GB.")
print(f"Peak reserved memory for training = {used_memory_for_lora} GB.")
print(f"Peak reserved memory % of max memory = {used_percentage} %.")
print(f"Peak reserved memory for training % of max memory = {lora_percentage} %.")


model.save_pretrained("gemma-3-12b")  # Local saving
tokenizer.save_pretrained("gemma-3-12b")
