import imaplib
import email
from email.header import decode_header
import os
from dotenv import load_dotenv

load_dotenv()

USERNAME = os.getenv("IMAP_USER") 
PASSWORD = os.getenv("IMAP_PASS")
IMAP_SERVER = "mail.pissmail.com"

def clean_header(header_value):
    if not header_value:
        return "(No Subject)"
    decoded_list = decode_header(header_value)
    default_charset = "utf-8"
    
    text_parts = []
    for decoded_bytes, charset in decoded_list:
        if isinstance(decoded_bytes, bytes):
            try:
                text_parts.append(decoded_bytes.decode(charset or default_charset))
            except LookupError:
                # Fallback if charset is unknown
                text_parts.append(decoded_bytes.decode(default_charset, errors="replace"))
        else:
            text_parts.append(str(decoded_bytes))
            
    return "".join(text_parts)

def list_all_emails():
    print(f"Connecting to {IMAP_SERVER}...")
    
    # port 993
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(USERNAME, PASSWORD)
    except Exception as e:
        print(f"❌ Login Failed: {e}")
        return

    print("Logged in.\nSelecting INBOX...")
    mail.select("INBOX")

    # 3. Search for ALL emails
    status, messages = mail.search(None, "ALL")
    
    if status != "OK" or not messages[0]:
        print("No emails found in INBOX.")
        return

    mail_ids = messages[0].split()
    total_emails = len(mail_ids)
    print(f"Found {total_emails} emails. Listing (Newest First):\n")

    print(f"{'ID':<6} | {'Date':<25} | {'From':<30} | {'Subject'}")
    print("-" * 100)

    # iterate reversed to show newest first
    for mail_id in mail_ids[::-1]: 
        
        # fetch only the header 
        _, msg_data = mail.fetch(mail_id, "(RFC822.HEADER)")
        
        for response_part in msg_data:
            if isinstance(response_part, tuple):
                # Parse the raw email bytes
                msg = email.message_from_bytes(response_part[1])
                
                # Extract and clean headers
                subject = clean_header(msg["Subject"])
                sender = clean_header(msg.get("From", "Unknown"))
                date = msg.get("Date", "")[:25] # Truncate date for table fit

                # Print row
                print(f"{mail_id.decode():<6} | {date:<25} | {sender[:30]:<30} | {subject}")

    mail.close()
    mail.logout()

if __name__ == "__main__":
    list_all_emails()
