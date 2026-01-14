#!/usr/bin/env python3
"""
cowrie JSON Log Ingester - polls remote cowrie.json via SFTP, parses JSON lines, stores in MongoDB
"""
import json
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import paramiko
from pymongo import MongoClient, errors

# CONFIG
SSH_HOST = "35.208.122.89"
SSH_PORT = 6453
SSH_USER = "person"
SSH_KEYFILE = str(Path. home() / ".ssh" / "cowrie_person_key")
REMOTE_PATH = "/home/cowrie/cowrie/var/log/cowrie/cowrie.json"
POLL_SECONDS = 10 * 60  # 10 minutes

MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "honeypot_db"
COLLECTION_NAME = "cowrie_events"

# track last read position
STATE_FILE = Path("./cowrie_state.json")


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"offset": 0}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state))


def fetch_and_ingest():
    """fetch new lines from remote cowrie.json and insert into MongoDB."""
    state = load_state()
    offset = state.get("offset", 0)

    # connect to MongoDB
    mongo = MongoClient(MONGO_URI)
    collection = mongo[DB_NAME][COLLECTION_NAME]

    # connect via SSH/SFTP
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(SSH_HOST, port=SSH_PORT, username=SSH_USER, key_filename=SSH_KEYFILE, timeout=30)
        sftp = ssh.open_sftp()

        # check file size
        stat = sftp.stat(REMOTE_PATH)
        file_size = stat.st_size

        # handle log rotation
        if file_size < offset: 
            print(f"[INFO] Log rotated, resetting offset from {offset} to 0")
            offset = 0

        if file_size == offset: 
            print("[INFO] No new data")
            return 0

        # Read new content
        with sftp.open(REMOTE_PATH, 'r') as f:
            f.seek(offset)
            new_content = f.read()
            new_offset = f.tell()

        sftp.close()
        ssh.close()

        # parse and insert
        docs = []
        for line in new_content.decode('utf-8', errors='replace').strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                
                # unique id so that duplicate lines are skipped
                event['_id'] = hashlib. sha256(line. encode('utf-8')).hexdigest()
                event['_ingested_at'] = datetime.now(timezone.utc)
                docs.append(event)
            except json.JSONDecodeError:
                continue

        if not docs:
            save_state({"offset":  new_offset})
            return 0

        # insert (with duplicate handling)
        try:
            result = collection.insert_many(docs, ordered=False)
            inserted = len(result.inserted_ids)
        except errors. BulkWriteError as e: 
            inserted = e. details.get('nInserted', 0)
            dupes = len(e.details. get('writeErrors', []))
            if dupes > 0:
                print(f"[WARN] {dupes} duplicates skipped")

        save_state({"offset": new_offset})
        print(f"[OK] Inserted {inserted} events")
        return inserted

    except Exception as e: 
        print(f"[ERROR] {e}")
        return 0
    finally:
        try: 
            ssh.close()
        except:
            pass


def main():
    print(f"[*] Cowrie Log Ingester - polling every {POLL_SECONDS}s")
    print(f"[*] Remote:  {SSH_USER}@{SSH_HOST}:{SSH_PORT}{REMOTE_PATH}")

    while True:
        print(f"\n[{datetime.now().isoformat()}] Checking for new events...")
        fetch_and_ingest()
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
