#!/usr/bin/env python3
import argparse
import json
from typing import Any, Dict, List

"""usage:
python3 parse_toJSONL.py \
  --in split_{train|val}.json \
  --out {train|val}.jsonl \
  --format text \
  --fix-output-3
"""

DEFAULT_SYSTEM = (
    "Role: Predictive Honeypot. Analyze SSH. Predict 3 unique high-value "
    "Canarytoken trap commands. Sort by probability."
)

DEFAULT_USER_TEMPLATE = (
    "SSH observed command:\n{input}\n\n"
    "Return exactly 3 items as a JSON array of objects. "
    "Each object must have keys: predicted_cmd, trap_path, trap_template. "
    "Sort most likely first. "
    "Output only valid JSON (no markdown, no backticks, no extra text)."
)

DEFAULT_NOOP = {"predicted_cmd": "cd", "trap_path": "", "trap_template": "NO_OP"}
REQUIRED_KEYS = ("predicted_cmd", "trap_path", "trap_template")


def load_records(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        text = f.read().strip()
    if not text:
        return []
    # JSON array first; fallback to JSONL
    try:
        obj = json.loads(text)
        if isinstance(obj, list):
            return obj
        if isinstance(obj, dict):
            return [obj]
        raise ValueError("Unsupported JSON top-level type.")
    except json.JSONDecodeError:
        records = []
        for i, line in enumerate(text.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON on line {i}: {e}") from e
        return records


def coerce_output_to_3(out: Any, noop: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(out, list):
        out = []
    cleaned = []
    for item in out:
        if not isinstance(item, dict):
            item = {}
        cleaned.append({
            "predicted_cmd": item.get("predicted_cmd", noop["predicted_cmd"]),
            "trap_path": item.get("trap_path", noop["trap_path"]),
            "trap_template": item.get("trap_template", noop["trap_template"]),
        })
    if len(cleaned) >= 3:
        return cleaned[:3]
    while len(cleaned) < 3:
        cleaned.append(dict(noop))
    return cleaned


def output_as_json_array_string(out3: List[Dict[str, Any]]) -> str:
    # Compact JSON string so the model learns “raw JSON only”.
    return json.dumps(out3, ensure_ascii=False, separators=(",", ":"))


def build_text_example(system: str, user: str, assistant: str) -> str:
    # Simple delimiters; you can later replace with a tokenizer chat_template if desired.
    return f"<SYSTEM>\n{system}\n\n<USER>\n{user}\n\n<ASSISTANT>\n{assistant}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_path", required=True, help="Input cleaned JSON array or JSONL")
    ap.add_argument("--out", required=True, help="Output JSONL path")

    ap.add_argument("--format", choices=["text", "messages"], default="text",
                    help="Output schema: one 'text' field, or a TRL-style 'messages' list")

    ap.add_argument("--system", default=DEFAULT_SYSTEM, help="System instruction text")
    ap.add_argument("--user-template", default=DEFAULT_USER_TEMPLATE,
                    help="User prompt template; must include {input}")

    ap.add_argument("--fix-output-3", action="store_true",
                    help="Pad/truncate output to exactly 3 using NO_OP (recommended)")
    ap.add_argument("--noop-cmd", default=DEFAULT_NOOP["predicted_cmd"])
    ap.add_argument("--noop-path", default=DEFAULT_NOOP["trap_path"])
    ap.add_argument("--noop-template", default=DEFAULT_NOOP["trap_template"])

    args = ap.parse_args()

    noop = {"predicted_cmd": args.noop_cmd, "trap_path": args.noop_path, "trap_template": args.noop_template}

    records = load_records(args.in_path)
    if not records:
        raise SystemExit("No records found.")

    with open(args.out, "w", encoding="utf-8") as f:
        for r in records:
            if not isinstance(r, dict):
                continue
            inp = r.get("input", "")
            if not isinstance(inp, str) or not inp.strip():
                continue

            user_text = args.user_template.format(input=inp)

            out = r.get("output", [])
            if args.fix_output_3:
                out3 = coerce_output_to_3(out, noop)
            else:
                # assume already valid list-of-3 dicts
                out3 = out

            # minimal safety: ensure required keys exist
            if not isinstance(out3, list) or len(out3) != 3:
                continue
            ok = True
            for item in out3:
                if not isinstance(item, dict) or not all(k in item for k in REQUIRED_KEYS):
                    ok = False
                    break
            if not ok:
                continue

            assistant_text = output_as_json_array_string(out3)

            if args.format == "text":
                row = {"text": build_text_example(args.system, user_text, assistant_text)}
            else:
                row = {"messages": [
                    {"role": "system", "content": args.system},
                    {"role": "user", "content": user_text},
                    {"role": "assistant", "content": assistant_text},
                ]}

            f.write(json.dumps(row, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
