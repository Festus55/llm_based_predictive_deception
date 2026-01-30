#!/usr/bin/env python3
import argparse
import re
import statistics
from collections import Counter
from datetime import datetime

RE_NEW_CONN = re.compile(r"New connection: .*\[session: ([0-9a-f]+)\]", re.IGNORECASE)
RE_CMD = re.compile(r"\bCMD:\s*(.+)\s*$")


from datetime import datetime
import re

RE_TS = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{4}))"
)

def parse_ts_str(ts: str) -> datetime:
    # supporta microsecondi opzionali, timezone +0100 oppure 'Z'
    if ts.endswith("Z"):
        base = ts[:-1]
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(base, fmt).replace(tzinfo=datetime.timezone.utc)
            except Exception:
                pass
        raise ValueError(f"Unparseable UTC ts: {ts}")

    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(ts, fmt)
        except Exception:
            pass
    raise ValueError(f"Unparseable ts: {ts}")

def line_ts(line: str):
    m = RE_TS.match(line)
    if not m:
        return None
    try:
        return parse_ts_str(m.group("ts"))
    except Exception:
        return None
def parse_counts(path: str, since=None, until=None):
    current_session = None
    sessions_seen = []
    sessions_set = set()
    counts = Counter()

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            ts = line_ts(line)
            if since and ts and ts < since:
                continue
            if until and ts and ts > until:
                continue

            m = RE_NEW_CONN.search(line)
            if m:
                current_session = m.group(1)
                if current_session not in sessions_set:
                    sessions_set.add(current_session)
                    sessions_seen.append(current_session)
                continue

            m = RE_CMD.search(line)
            if m and current_session:
                counts[current_session] += 1

    return sessions_seen, counts

def mean_median(values):
    if not values:
        return None, None
    return (sum(values) / len(values), statistics.median(values))

def main():
    ap = argparse.ArgumentParser(description="Mean/median #CMD per session in Cowrie textlog (CMD: ...).")
    ap.add_argument("logfile", help="Log file path")
    ap.add_argument("--nonzero", action="store_true",
                    help="Prevents the counting on non command sessions")
    ap.add_argument("--csv-out", default=None,
                    help="Outputs a CSV (session,n_commands)")
    ap.add_argument("--since", default=None,
                    help="Includes onlylogs where timestamp >= this (es: 2026-01-13T20:00:00+0100)")
    ap.add_argument("--until", default=None,
                    help="Includes onlylogs where timestamp <= this (es: 2026-01-13T23:59:59+0100)")

    args = ap.parse_args()
    since = parse_ts_str(args.since) if args.since else None
    until = parse_ts_str(args.until) if args.until else None

    sessions, counts = parse_counts(args.logfile, since=since, until=until)

    all_counts = [counts.get(s, 0) for s in sessions]
    data = [c for c in all_counts if c > 0] if args.nonzero else all_counts

    mean, median = mean_median(data)

    print(f"sessions_total={len(sessions)}")
    print(f"sessions_with_cmd={sum(1 for c in all_counts if c>0)}")
    print(f"mean_commands={mean}")
    print(f"median_commands={median}")
    print(f"total_cmd_events={sum(all_counts)}")

    if args.csv_out:
        with open(args.csv_out, "w", encoding="utf-8", newline="") as out:
            out.write("session,n_commands\n")
            for s in sessions:
                out.write(f"{s},{counts.get(s,0)}\n")

if __name__ == "__main__":
    main()
