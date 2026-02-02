#!/usr/bin/env python3
import argparse
import json
import csv
from datetime import datetime
from statistics import mean, median

def parse_ts(s: str) -> datetime | None:
    if not s:
        return None
    
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", help="Cowrie JSONL log file (one JSON object per line)")
    ap.add_argument("--out", default="cowrie_success_sessions_durations.csv", help="Output CSV with per-session durations")
    args = ap.parse_args()

    sessions = {}  # session_id -> info dict

    def get_session(sess_id: str):
        if sess_id not in sessions:
            sessions[sess_id] = {
                "session": sess_id,
                "src_ip": None,
                "connect_ts": None,
                "login_success_ts": None,
                "close_ts": None,
                "close_duration_s": None,  # cowrie.session.closed.duration
            }
        return sessions[sess_id]

    with open(args.path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue

            sess_id = ev.get("session")
            if not sess_id:
                continue

            s = get_session(sess_id)
            eventid = ev.get("eventid")
            ts = parse_ts(ev.get("timestamp"))
            if s["src_ip"] is None:
                s["src_ip"] = ev.get("src_ip")

            if eventid == "cowrie.session.connect":
                if s["connect_ts"] is None:
                    s["connect_ts"] = ts
            elif eventid == "cowrie.login.success":
                if s["login_success_ts"] is None:
                    s["login_success_ts"] = ts
            elif eventid == "cowrie.session.closed":
                # keep the last close timestamp seen
                s["close_ts"] = ts
                d = ev.get("duration")
                try:
                    s["close_duration_s"] = float(d)
                except Exception:
                    pass

    # Build per-success-session results
    results = []
    for s in sessions.values():
        if s["login_success_ts"] is None:
            continue  # not a successful session
        if s["close_ts"] is None:
            continue  # no close event => can't time it reliably

        # Total connection duration: close_duration_s
        conn_to_close = None
        if s["connect_ts"] and s["close_ts"]:
            conn_to_close = (s["close_ts"] - s["connect_ts"]).total_seconds()

        total_duration = s["close_duration_s"] if s["close_duration_s"] is not None else conn_to_close

        post_auth = None
        if s["login_success_ts"] and s["close_ts"]:
            post_auth = (s["close_ts"] - s["login_success_ts"]).total_seconds()

        results.append({
            "session": s["session"],
            "src_ip": s["src_ip"],
            "connect_ts": s["connect_ts"].isoformat() if s["connect_ts"] else "",
            "login_success_ts": s["login_success_ts"].isoformat() if s["login_success_ts"] else "",
            "close_ts": s["close_ts"].isoformat() if s["close_ts"] else "",
            "close_duration_s": s["close_duration_s"] if s["close_duration_s"] is not None else "",
            "conn_to_close_duration_s": conn_to_close if conn_to_close is not None else "",
            "post_auth_duration_s": post_auth if post_auth is not None else "",
            "total_duration_s": total_duration if total_duration is not None else "",
        })

    # Write CSV
    fieldnames = [
        "session", "src_ip",
        "connect_ts", "login_success_ts", "close_ts",
        "close_duration_s", "conn_to_close_duration_s",
        "post_auth_duration_s", "total_duration_s",
    ]
    with open(args.out, "w", newline="", encoding="utf-8") as out:
        w = csv.DictWriter(out, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(results)

    # Print stats
    totals = [r["total_duration_s"] for r in results if isinstance(r["total_duration_s"], (int, float))]
    post_auths = [r["post_auth_duration_s"] for r in results if isinstance(r["post_auth_duration_s"], (int, float))]

    print(f"Successful sessions (timed): {len(results)}")
    if totals:
        print(f"Average total duration: {mean(totals):.3f} s")
    if post_auths:
        print(f"Average post-login duration: {mean(post_auths):.3f} s")
        print(f"Median post-login duration: {median(post_auths):.3f} s")
    print(f"Wrote: {args.out}")

if __name__ == '__main__':
    main()
