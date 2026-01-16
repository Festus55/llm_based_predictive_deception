#!/usr/bin/env python3
"""
sanitizer_hex.py 

Replaces long runs of hex-escape blobs (\\xHH sequences) with tags, ONLY inside the
output array (completion JSON list or window_json output list).

Typical use: remove huge `echo -en \\x7f\\x45...` payloads in predicted_cmd while
keeping the surrounding command structure.

Example tag: <HEX_BLOB_1 bytes=412>

Notes:
- Operates on JSONL.
- In prompt_completion mode, `completion` is a JSON string containing the output list.
- In window_json mode, `output` is already the output list.

Usage:
python3 sanitizer_hex.py \
  --in {train|val}_prompt_completion_sanitized.jsonl \
  --out {train|val}_prompt_completion_sanitized_hex.jsonl \
  --mode prompt_completion \
  --min_bytes 80

"""

import argparse
import json
import re
from typing import Any, Tuple

# Match runs of \xHH (with double backslash in JSON strings, you'll see "\\xHH" in Python)
# We treat BOTH representations:
# - literal backslash-x: "\\x4f" in Python string
# - (rare) single backslash-x: "\x4f" already interpreted (won't usually exist in JSON)
HEX_BYTE_RE = re.compile(r'\\x[0-9A-Fa-f]{2}')

def replace_hex_bytes_if_many(s: str, min_bytes: int = 80, hex_token: str = "<HX>") -> Tuple[str, int]:
    nbytes = len(HEX_BYTE_RE.findall(s))
    if nbytes < min_bytes:
        return s, 0
    return HEX_BYTE_RE.sub(hex_token, s), 1

def sanitize_output_list(output: Any, min_bytes: int = 80, fields=("predicted_cmd",), hex_token: str = "<HX>") -> Tuple[Any, int]:
    """Sanitize ONLY within output list of dicts, only in selected fields."""
    if not isinstance(output, list):
        return output, 0

    total_replaced_fields = 0
    new_out = []

    for item in output:
        if not isinstance(item, dict):
            new_out.append(item)
            continue

        new_item = dict(item)
        for k in fields:
            v = new_item.get(k)
            if isinstance(v, str):
                new_v, changed = replace_hex_bytes_if_many(v, min_bytes=min_bytes, hex_token=hex_token)
                new_item[k] = new_v
                total_replaced_fields += changed

        new_out.append(new_item)

    return new_out, total_replaced_fields

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True, help="Input JSONL")
    ap.add_argument("--out", dest="out", required=True, help="Output JSONL")
    ap.add_argument("--min_bytes", type=int, default=80,
                    help="Replace only if >= this many \\xHH occurrences exist in the field (default: 80)")
    ap.add_argument("--hex_token", default="<HX>",
                    help="Token to substitute for each \\xHH when threshold is met (default: <HX>)")
    ap.add_argument("--mode", choices=["prompt_completion", "window_json"], required=True,
                    help="prompt_completion expects {prompt, completion}; window_json expects {input, output}")
    ap.add_argument("--fields", default="predicted_cmd",
                    help="Comma-separated list of fields inside each output object to sanitize (default: predicted_cmd)")
    ap.add_argument("--debug_first", type=int, default=0,
                    help="Print first N field values that contain any \\xHH plus their counts.")
    args = ap.parse_args()

    fields = tuple(f.strip() for f in args.fields.split(",") if f.strip())

    lines = 0
    fields_replaced = 0
    lines_changed = 0
    debug_left = args.debug_first

    with open(args.inp, "r", encoding="utf-8") as fin, open(args.out, "w", encoding="utf-8") as fout:
        for raw in fin:
            raw = raw.strip()
            if not raw:
                continue
            lines += 1
            obj = json.loads(raw)

            changed_this_line = 0

            if args.mode == "prompt_completion":
                comp = obj.get("completion")
                if isinstance(comp, str):
                    try:
                        out_list = json.loads(comp)
                    except Exception:
                        fout.write(json.dumps(obj, ensure_ascii=False) + "\n")
                        continue

                    # debug: show a few examples with counts
                    if debug_left > 0 and isinstance(out_list, list):
                        for it in out_list:
                            if not isinstance(it, dict):
                                continue
                            for k in fields:
                                v = it.get(k)
                                if isinstance(v, str):
                                    n = len(HEX_BYTE_RE.findall(v))
                                    if n > 0:
                                        print(f"DEBUG hex_bytes={n} field={k} value[:160]={v[:160]}")
                                        debug_left -= 1
                                        break
                            if debug_left <= 0:
                                break

                    new_out, changed_this_line = sanitize_output_list(
                        out_list, min_bytes=args.min_bytes, fields=fields, hex_token=args.hex_token
                    )
                    obj["completion"] = json.dumps(new_out, ensure_ascii=False)

            else:  # window_json
                new_out, changed_this_line = sanitize_output_list(
                    obj.get("output"), min_bytes=args.min_bytes, fields=fields, hex_token=args.hex_token
                )
                obj["output"] = new_out

            if changed_this_line > 0:
                lines_changed += 1
                fields_replaced += changed_this_line

            fout.write(json.dumps(obj, ensure_ascii=False) + "\n")

    print(json.dumps({
        "lines_processed": lines,
        "lines_changed": lines_changed,
        "fields_replaced": fields_replaced,
        "min_bytes": args.min_bytes,
        "hex_token": args.hex_token,
        "fields": list(fields),
        "mode": args.mode,
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()