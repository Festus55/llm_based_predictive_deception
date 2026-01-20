#!/usr/bin/env python3
"""
cowrie JSON log ingester - polls remote cowrie.json via SFTP, parses JSON lines, stores in MongoDB
(multiple Cowrie instances with separate collections)
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
POLL_SECONDS = 10 * 60  # 10 minutes

MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "honeypot_db"

# Cowrie instances configuration
COWRIE_INSTANCES = [
    {
        "name": "cowrie",
        "remote_path": "/home/cowrie/cowrie/var/log/cowrie/cowrie.json",
        "collection":  "events-cowrie",
        "state_key": "cowrie_offset"
    },
    {
        "name": "cowrie-standard",
        "remote_path":  "/home/cowrie/cowrie-standard/var/log/cowrie/cowrie.json",
        "collection": "events-cowrie-standard",
        "state_key": "cowrie_standard_offset"
    }
]

# track last read position
STATE_FILE = Path("./cowrie_state.json")


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state))


def fetch_and_ingest_instance(sftp, mongo, instance, state):
    """Fetch new lines from a single cowrie instance and insert into MongoDB."""
    name = instance["name"]
    remote_path = instance["remote_path"]
    collection_name = instance["collection"]
    state_key = instance["state_key"]
    
    offset = state.get(state_key, 0)
    collection = mongo[DB_NAME][collection_name]

    try:
        # check file size
        stat = sftp.stat(remote_path)
        file_size = stat.st_size

        # handle log rotation
        if file_size < offset:
            print(f"[INFO] [{name}] Log rotated, resetting offset from {offset} to 0")
            offset = 0

        if file_size == offset:
            print(f"[INFO] [{name}] No new data")
            return 0, offset

        # Read new content
        with sftp.open(remote_path, 'r') as f:
            f.seek(offset)
            new_content = f.read()
            new_offset = f.tell()

        # parse and insert
        docs = []
        for line in new_content.decode('utf-8', errors='replace').strip().split('\n'):
            line = line.strip()
            if not line: 
                continue
            try:
                event = json.loads(line)

                # unique id so that duplicate lines are skipped
                event['_id'] = hashlib.sha256(line.encode('utf-8')).hexdigest()
                event['_ingested_at'] = datetime.now(timezone.utc)
                event['_source_instance'] = name  # track which instance this came from
                docs.append(event)
            except json.JSONDecodeError:
                continue

        if not docs:
            return 0, new_offset

        # insert (with duplicate handling)
        try:
            result = collection.insert_many(docs, ordered=False)
            inserted = len(result.inserted_ids)
        except errors. BulkWriteError as e:
            inserted = e.details.get('nInserted', 0)
            dupes = len(e.details.get('writeErrors', []))
            if dupes > 0:
                print(f"[WARN] [{name}] {dupes} duplicates skipped")

        print(f"[OK] [{name}] Inserted {inserted} events into {collection_name}")
        return inserted, new_offset

    except FileNotFoundError:
        print(f"[WARN] [{name}] Remote file not found: {remote_path}")
        return 0, offset
    except Exception as e:
        print(f"[ERROR] [{name}] {e}")
        return 0, offset


def fetch_and_ingest():
    """Fetch new lines from all cowrie instances and insert into MongoDB."""
    state = load_state()

    # connect to MongoDB
    mongo = MongoClient(MONGO_URI)

    # connect via SSH/SFTP
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    total_inserted = 0

    try:
        ssh.connect(SSH_HOST, port=SSH_PORT, username=SSH_USER, key_filename=SSH_KEYFILE, timeout=30)
        sftp = ssh.open_sftp()

        # Process each Cowrie instance
        for instance in COWRIE_INSTANCES: 
            inserted, new_offset = fetch_and_ingest_instance(sftp, mongo, instance, state)
            total_inserted += inserted
            state[instance["state_key"]] = new_offset

        sftp.close()
        ssh.close()

        # Save state for all instances
        save_state(state)
        
        print(f"[OK] Total inserted:  {total_inserted} events")
        return total_inserted

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
    print(f"[*] Monitoring {len(COWRIE_INSTANCES)} Cowrie instances:")
    for instance in COWRIE_INSTANCES: 
        print(f"    - {instance['name']}:  {instance['remote_path']} -> {instance['collection']}")

    while True:
        print(f"\n[{datetime.now().isoformat()}] Checking for new events...")
        fetch_and_ingest()
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
