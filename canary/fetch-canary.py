import time, os
import imaplib, re
from dotenv import load_dotenv
from email import policy
from email.parser import BytesParser
from datetime import datetime, timezone

from pymongo import MongoClient

IMAP_URL = "mail.pissmail.com"
IMAP_MAILBOX = "INBOX"
FROM = "noreply@canarytokens.org"
SUBJECT = "Your Canarytoken was Triggered" 

DB_NAME = "honeypot"
COLL_NAME = "canary_alerts"
POLLING_SECONDS = 10

load_dotenv()
USER = os.getenv("IMAP_USER")
APP_PASS = os.getenv("IMAP_PASS")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")

RX = {
    "token_type_ip": re.compile(r"^A\s+(?P<token_type>.+?)\s+Canarytoken .*? Source IP\s+(?P<source_ip>\d+\.\d+\.\d+\.\d+)\s*$", re.M),
    "reminder":      re.compile(r"^Reminder:\s*\n\s*(?P<reminder>.+?)\s*$", re.M),
    "source_ip":     re.compile(r"^Source IP:\s*\n\s*(?P<source_ip>\d+\.\d+\.\d+\.\d+)\s*$", re.M),
    "date":          re.compile(r"^Date:\s*\n\s*(?P<date>\d{4}/\d{2}/\d{2})\s*$", re.M),
    "time":          re.compile(r"^Time:\s*\n\s*(?P<time>\d{2}:\d{2})\s+UTC\s*$", re.M),
    "user_agent":    re.compile(r"^User agent:\s*\n\s*(?P<ua>.+?)\s*$", re.M),
    "token_id":      re.compile(r"^Canarytoken ID:\s*\n\s*(?P<token_id>[a-z0-9]+)\s*$", re.M),
    "history_url":   re.compile(r"^Alert History:\s*\n\s*(?P<history>https?://\S+)\s*$", re.M),
    "manage_url":    re.compile(r"^Manage Alert:\s*\n\s*(?P<manage>https?://\S+)\s*$", re.M),
}


def parse_bytes(raw_bytes: bytes):
    return BytesParser(policy=policy.default).parsebytes(raw_bytes)

def get_plain_text(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)  or b""
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
        return ""
    payload = msg.get_payload(decode=True)  or b""
    charset = msg.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")


def parse_canary_mail(msg):
    subj = (msg.get("Subject") or "").strip()
    if subj != SUBJECT:
        return None
    
    body = get_plain_text(msg)

    out = {
        "message_id": (msg.get("Message-Id") or "").strip(),
        "mail_from": (msg.get("From") or "").strip(),
        "mail_subject": subj,
        "mail_date": (msg.get("Date") or "").strip(),
        "raw_text": body,
        "inserted_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    m = RX["token_type_ip"].search(body)
    if m:
        out["token_type"] = m.group("token_type").strip()
        out["source_ip"]  = m.group("source_ip").strip()

    for k, rx in RX.items():
        if k == "token_type_ip":
            continue
        mm = rx.search(body)
        if mm:
            out.update({kk: vv.strip() for kk, vv in mm.groupdict().items()})

    if out.get("date") and out.get("time"):
        dt = datetime.strptime(out["date"] + " " + out["time"], "%Y/%m/%d %H:%M").replace(tzinfo=timezone.utc)
        out["triggered_at_utc"] = dt.isoformat()

    # not saving Manage URL (has auth=secret)
    out.pop("manage", None)

    if not out["message_id"]:
        return None

    return out

def mongo_collection():
    client = MongoClient(MONGO_URI)
    coll = client[DB_NAME][COLL_NAME]
    coll.create_index("message_id", unique=True)
    return client, coll


def imap_connect(user, app_pass):
    c = imaplib.IMAP4_SSL(IMAP_URL)
    c.login(user, app_pass)
    c.select(IMAP_MAILBOX)
    return c


def find_unseen_canary(imap_conn):
    query = f'(UNSEEN FROM "{FROM}" SUBJECT "{SUBJECT}")'
    typ, data = imap_conn.search(None, query)
    if typ != "OK":
        return []
    return data[0].split()


def fetch_one(imap_conn, msgnum):
    typ, msg_data = imap_conn.fetch(msgnum, "(RFC822)") # change with RFC822.PEEK to avoid flipping  messages to Seen 
    if typ != "OK":
        return None
    return msg_data[0][1]


def save_alert(coll, alert: dict):
    coll.update_one(
        {"message_id": alert["message_id"]},
        {"$setOnInsert": alert},
        upsert=True # insert once, ignore on next runs
    )

def run(user, app_pass):
    mongo_client, coll = mongo_collection()
    try:
        while True:
            imap_conn = None
            try:
                imap_conn = imap_connect(user, app_pass)
                for msgnum in find_unseen_canary(imap_conn):
                    raw = fetch_one(imap_conn, msgnum)
                    if not raw:
                        continue
                    msg = parse_bytes(raw)
                    alert = parse_canary_mail(msg)
                    if alert:
                        print(alert)
                        save_alert(coll, alert)
            finally:
                if imap_conn:
                    try:
                        imap_conn.logout()
                    except Exception:
                        pass

            time.sleep(POLLING_SECONDS)
    finally:
        mongo_client.close()

def main():
    run(USER, APP_PASS)

if __name__ == "__main__":
    main()

