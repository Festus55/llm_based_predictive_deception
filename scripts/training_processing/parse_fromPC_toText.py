import json
import re
import sys
import os
 
def parse_and_transform(input_file, output_file):
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Errore: Il file '{input_file}' non è stato trovato.")
        return
    except json.JSONDecodeError as e:
        print(f"Errore: Il file '{input_file}' non è un JSON valido.\n{e}")
        return
 
    transformed_data = []

    pattern = re.compile(r"<SYSTEM>\s*(.*?)\s*<USER>\s*(.*?)\s*<ASSISTANT>", re.DOTALL | re.IGNORECASE)
 
    print(f"Analisi di {len(data)} elementi...")
 
    success_count = 0
    for entry in data:
        raw_prompt = entry.get("prompt", "")
        completion = entry.get("completion", "")
 
        match = pattern.search(raw_prompt)
 
        if match:
            system_prompt = match.group(1).strip()
            user_input = match.group(2).strip()
            formatted_text = (
                f"<start_of_turn>user\n"
                f"{system_prompt}\n\n"
                f"{user_input}<end_of_turn>\n"
                f"<start_of_turn>model\n"
                f"{completion}<end_of_turn>"
            )
 
            transformed_data.append({"text": formatted_text})
            success_count += 1
        else:
            print(f"[Warning] Pattern non trovato nel prompt (len: {len(raw_prompt)}). Saltato.")
 
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(transformed_data, f, indent=4, ensure_ascii=False)
        print(f"---")
        print(f"Completato. Convertiti {success_count}/{len(data)} elementi.")
        print(f"Output salvato in: {output_file}")
    except IOError as e:
        print(f"Errore durante il salvataggio del file: {e}")
 
if __name__ == "__main__":
    if len(sys.argv) == 3:
        INPUT_FILENAME = sys.argv[1]
        OUTPUT_FILENAME = sys.argv[2]
    else:
        print(f"Usage: python {sys.argv[0]} <input.json> <output.json>")
        sys.exit(1)
 
    parse_and_transform(INPUT_FILENAME, OUTPUT_FILENAME)