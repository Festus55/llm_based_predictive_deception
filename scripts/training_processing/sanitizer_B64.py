#!/usr/bin/env python3
import argparse
import json
import re
from typing import Any, Dict, List, Tuple

"""usage
python3 sanitizer_B64.py \
  --in {train|val}_prompt_completion.jsonl \
  --out {train|val}_prompt_completion_sanitized.jsonl \
  --mode prompt_completion \
  --min_len 80
  """

# Conservative "base64-ish" detector:
# - only base64 charset
# - length multiple of 4 OR ends with = / ==
# - we apply a minimum length threshold to avoid false positives
B64_RE = re.compile(r'(?:[A-Za-z0-9+/]{4}){10,}(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?')

def replace_b64_in_string(s: str, min_len: int = 80) -> Tuple[str, int]:
    """Replace base64-ish substrings in s with tags. Returns (new_s, replacements_count)."""
    n = 0

    def _sub(m: re.Match) -> str:
        nonlocal n
        blob = m.group(0)
        if len(blob) < min_len:
            return blob
        n += 1
        return f"<B64_{n} len={len(blob)}>"
    return B64_RE.sub(_sub, s), n

def sanitize_output_list(output: Any, min_len: int = 80) -> Tuple[Any, int]:
    """Sanitize ONLY within output list of dicts: predicted_cmd, trap_path, trap_template."""
    if not isinstance(output, list):
        return output, 0

    total = 0
    new_out = []
    for item in output:
        if not isinstance(item, dict):
            new_out.append(item)
            continue

        new_item = dict(item)
        # Only touch string fields of each output object.
        for k in ("predicted_cmd", "trap_path", "trap_template"):
            v = new_item.get(k)
            if isinstance(v, str):
                new_v, c = replace_b64_in_string(v, min_len=min_len)
                new_item[k] = new_v
                total += c
        new_out.append(new_item)

    return new_out, total

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True, help="Input JSONL")
    ap.add_argument("--out", dest="out", required=True, help="Output JSONL")
    ap.add_argument("--min_len", type=int, default=80, help="Minimum base64 run length to replace")
    ap.add_argument("--mode", choices=["prompt_completion", "window_json"], required=True,
                    help="prompt_completion: expects {prompt, completion}; window_json: expects {input, output}")
    args = ap.parse_args()

    replaced_total = 0
    lines = 0

    with open(args.inp, "r", encoding="utf-8") as fin, open(args.out, "w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            lines += 1
            obj = json.loads(line)

            if args.mode == "prompt_completion":
                # completion is a JSON string representing the output array
                comp = obj.get("completion")
                if isinstance(comp, str):
                    try:
                        comp_json = json.loads(comp)
                    except Exception:
                        # If completion isn't valid JSON, leave it unchanged
                        fout.write(json.dumps(obj, ensure_ascii=False) + "\n")
                        continue

                    new_comp_json, c = sanitize_output_list(comp_json, min_len=args.min_len)
                    obj["completion"] = json.dumps(new_comp_json, ensure_ascii=False)
                    replaced_total += c

            elif args.mode == "window_json":
                # output is already a list of dicts
                new_out, c = sanitize_output_list(obj.get("output"), min_len=args.min_len)
                obj["output"] = new_out
                replaced_total += c

            fout.write(json.dumps(obj, ensure_ascii=False) + "\n")

    print(json.dumps({
        "lines_processed": lines,
        "base64_replacements": replaced_total,
        "min_len": args.min_len,
    }))

if __name__ == "__main__":
    main()
