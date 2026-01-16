import json

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) == 3:
        INP = sys.argv[1]
        OUT = sys.argv[2]
    else:
        print("Usage: python prompt_completition_format.py <input.jsonl> <output.jsonl>")
        sys.exit(1)

    MARKER = "\n<ASSISTANT>\n"

    with open( INP, "r", encoding="utf-8") as f_in, open(OUT, "w", encoding="utf-8") as f_out:
        for line_num, line in enumerate(f_in, 1):
            if not line.strip():
                continue
            obj = json.loads(line)
            text = obj["text"]

            if MARKER not in text:
                raise ValueError(f"Missing marker on line {line_num}")

            prompt, completion = text.split(MARKER, 1)
            prompt = prompt + MARKER
            completion = completion.strip()

            # Optional: validate completion is JSON
            json.loads(completion)

            f_out.write(json.dumps({"prompt": prompt, "completion": completion}, ensure_ascii=False) + "\n")
