import json
from typing import Dict, List, Any

INPUT_FILE  = "cowrie_sequences.jsonl"   # one JSON object per line
OUTPUT_FILE = "processed_sessions.json"

def process_cowrie_logs(
    input_path: str = INPUT_FILE,
    output_path: str = OUTPUT_FILE,
    eos_token: str = "<EOS>",
) -> None:
    """
    Read (history, next_cmd, session_id, session_meta) examples from a JSONL file,
    reconstruct the longest command sequence per session_id, and write them out
    as a JSON array of objects: {"commands": [..., "<EOS>"]}.
    """
    
    print(f"[*] Starting read from: {input_path}")

    reconstructed_sessions: Dict[str, Dict[str, Any]] = {}
    try:
        total_raw_examples = 0

        with open(input_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    # Skip broken lines
                    continue

                if not isinstance(entry, dict):
                    continue

                total_raw_examples += 1

                session_id = entry.get("session_id")
                history: List[str] = entry.get("history", []) or []
                next_cmd = entry.get("next_cmd")

                if not session_id or next_cmd is None:
                    continue

                # Reconstruct full sequence for this fragment
                current_full_sequence = list(history) + [next_cmd]
                current_len = len(current_full_sequence)

                # King-of-the-hill: keep the longest sequence per session
                existing = reconstructed_sessions.get(session_id)
                if existing is None or current_len > len(existing["commands"]):
                    reconstructed_sessions[session_id] = {
                        "commands": current_full_sequence,
                        "meta": entry.get("session_meta", {}),
                    }

        print(f"[*] Total raw examples processed: {total_raw_examples}")
        print(f"[*] Unique reconstructed sessions: {len(reconstructed_sessions)}")

        # --- WRITE OUTPUT AS JSON ARRAY ---
        print(f"[*] Writing output to: {output_path}")

        with open(output_path, "w", encoding="utf-8") as out_f:
            out_f.write("[\n")
            items = list(reconstructed_sessions.items())
            total_items = len(items)

            for i, (_sess_id, content) in enumerate(items):
                commands_list: List[str] = content["commands"]

                # new list
                commands_with_eos = commands_list + [eos_token]

                output_object = {
                    "commands": commands_with_eos
                    # You can also include meta if you decide it's useful later:
                    # "meta": content["meta"]
                }

                json.dump(output_object, out_f, ensure_ascii=False, indent=4)

                if i < total_items - 1:
                    out_f.write(",\n")
                else:
                    out_f.write("\n")

            out_f.write("]\n")

        print(
            f"[*] Done. Wrote {total_items} unique sessions to {output_path}."
        )

    except FileNotFoundError:
        print(f"[!] Error: input file {input_path} not found.")
    except MemoryError:
        print("[!] Error: input file too large for available RAM.")
    except Exception as e:
        print(f"[!] Unexpected error: {e}")


if __name__ == "__main__":
    process_cowrie_logs()
