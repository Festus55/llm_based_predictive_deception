import json
import glob
import ijson
from datetime import datetime

LOG_GLOB = "./LOGS/cyberlab_*.json"
OUTPUT_PATH = "cowrie_sequences.jsonl"

def parse_timestamp(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))

def extract_commands_for_session(events):
    cmds = []
    for evt in events:
        eid = evt.get("eventid", "")

        if eid == "cowrie.command.input":
            cmd = evt.get("input")

        # commands as cowrie.command.success + message
        elif eid == "cowrie.command.success":
            msg = evt.get("message") or ""
            prefix = "Command found:"
            if msg.startswith(prefix):
                cmd = msg[len(prefix):].strip()
            else:
                cmd = msg

        else:
            cmd = None

        if cmd:
            cmds.append(cmd)

    return cmds


def build_sequence_examples(commands, max_history_len=10):
    examples = []
    for i in range(1, len(commands)):
        history = commands[:i]
        if len(history) > max_history_len:
            history = history[-max_history_len:]
        examples.append({
            "history": history,
            "next_cmd": commands[i],
        })
    return examples


def summarize_session_meta(events):
    meta = {
        "auth_success": False,
        "auth_failed_count": 0,
        "ssh_client_version": None,
        "session_duration": None,
        "src_ip": None,
        "src_country": None,
    }
    for evt in events:
        eid = evt.get("eventid")
        if eid == "cowrie.login.success":
            meta["auth_success"] = True
        elif eid == "cowrie.login.failed":
            meta["auth_failed_count"] += 1
        elif eid == "cowrie.client.version":
            meta["ssh_client_version"] = (
                evt.get("version") or evt.get("ssh_client_version")
            )
        elif eid == "cowrie.session.closed":
            if "duration" in evt:
                meta["session_duration"] = evt["duration"]
        elif eid == "cowrie.session.connect":
            meta["src_ip"] = evt.get("src_ip") or evt.get("src_ip_identifier")
            geo = evt.get("geolocation_data") or {}
            meta["src_country"] = geo.get("country_name")
    return meta

def save_jsonl_append(path, records):
    with open(path, "a") as f:
        for r in records:
            f.write(json.dumps(r, default=str) + "\n")


# -------- main (streaming) --------

# truncate output once at the start
open(OUTPUT_PATH, "w").close()

total_sessions = 0
total_examples = 0

for path in glob.glob(LOG_GLOB):
    print(f"Streaming {path}")

    with open(path, "rb") as f:
        # each top-level element of the big JSON array is one {session_id: [events...]} dict
        for item in ijson.items(f, "item"):
            for sid, events in item.items():
                # sort events for this session only
                events_sorted = sorted(
                    events,
                    key=lambda e: parse_timestamp(e["timestamp"])
                )

                # extract commands for this single session
                cmds = extract_commands_for_session(events_sorted)
                if len(cmds) < 2:
                    continue

                # build examples for this single session
                seq_examples = build_sequence_examples(cmds, max_history_len=10)
                meta = summarize_session_meta(events_sorted)

                # attach meta and session_id
                for ex in seq_examples:
                    ex["session_id"] = sid
                    ex["session_meta"] = meta

                # write them out immediately
                save_jsonl_append(OUTPUT_PATH, seq_examples)

                total_sessions += 1
                total_examples += len(seq_examples)

    print(f"  Done {path}")

print(f"Total sessions processed: {total_sessions}")
print(f"Total training examples: {total_examples}")
print(f"Saved distilled examples to {OUTPUT_PATH}")
