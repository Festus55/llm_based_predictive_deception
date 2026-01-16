#!/usr/bin/env python3
import argparse, json, re
from typing import Any, Tuple

"""usage
python3 collapse_hx.py --in {train|val}_prompt_completion_sanitized_hex.jsonl --out {train|val}_prompt_completion_sanitized_hex_collapsed.jsonl --mode prompt_completion
"""

HX_RUN_RE = re.compile(r'(?:<HX>)+')  # one or more consecutive <HX>

def collapse_hx_runs(s: str) -> Tuple[str, int]:
    changed = 0

    def repl(m: re.Match) -> str:
        nonlocal changed
        run = m.group(0)
        n = run.count("<HX>")
        changed += 1
        return f"<HX len={n}>"

    return HX_RUN_RE.sub(repl, s), changed

def sanitize_output_list(output: Any, fields=("predicted_cmd",)) -> Tuple[Any, int]:
    if not isinstance(output, list):
        return output, 0
    total = 0
    new_out = []
    for item in output:
        if not isinstance(item, dict):
            new_out.append(item)
            continue
        new_item = dict(item)
        for k in fields:
            v = new_item.get(k)
            if isinstance(v, str) and "<HX>" in v:
                new_v, c = collapse_hx_runs(v)
                new_item[k] = new_v
                total += c
        new_out.append(new_item)
    return new_out, total

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", dest="out", required=True)
    ap.add_argument("--mode", choices=["prompt_completion", "window_json"], required=True)
    ap.add_argument("--fields", default="predicted_cmd")
    args = ap.parse_args()
    fields = tuple(f.strip() for f in args.fields.split(",") if f.strip())

    lines = lines_changed = repl_total = 0

    with open(args.inp, "r", encoding="utf-8") as fin, open(args.out, "w", encoding="utf-8") as fout:
        for raw in fin:
            raw = raw.strip()
            if not raw:
                continue
            lines += 1
            obj = json.loads(raw)

            c = 0
            if args.mode == "prompt_completion":
                comp = obj.get("completion")
                if isinstance(comp, str):
                    try:
                        out_list = json.loads(comp)
                    except Exception:
                        fout.write(json.dumps(obj, ensure_ascii=False) + "\n")
                        continue
                    new_out, c = sanitize_output_list(out_list, fields=fields)
                    obj["completion"] = json.dumps(new_out, ensure_ascii=False)
            else:
                new_out, c = sanitize_output_list(obj.get("output"), fields=fields)
                obj["output"] = new_out

            if c > 0:
                lines_changed += 1
                repl_total += c

            fout.write(json.dumps(obj, ensure_ascii=False) + "\n")

    print(json.dumps({
        "lines_processed": lines,
        "lines_changed": lines_changed,
        "hx_runs_collapsed": repl_total,
        "fields": list(fields),
        "mode": args.mode,
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()
