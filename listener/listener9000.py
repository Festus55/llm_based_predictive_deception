import json
import logging
from datetime import datetime, timezone
from flask import Flask, request, jsonify
from pymongo import MongoClient

app = Flask(__name__)

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

logging.basicConfig(
    filename='valid_alerts.log',
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)

# DB connection
try: 
    client = MongoClient('mongodb://localhost:27017/', serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    db = client['honeypot_db']
    collection = db['canary_alerts']
except Exception as e: 
    print(f"[ERROR] MongoDB connection failed: {e}")
    exit(1)

@app.route('/webhook', methods=['POST'])
def webhook():
    if not request.is_json:
        return "Forbidden:  JSON required", 403

    try:
        data = request.json
    except Exception: 
        return "Forbidden:  Malformed JSON", 403

    is_valid = False
    if 'token' in data and 'manage_url' in data: 
        is_valid = True
    elif 'text' in data: 
        text_content = str(data['text'])
        if "AWS ID Token" in text_content or "AccessKeyId" in text_content:
            is_valid = True

    if not is_valid:
        return "Forbidden: Unknown Payload Format", 403

    sender_ip = request.remote_addr
    
    # adding metadata
    data['_received_at'] = datetime.now(timezone. utc)
    data['_sender_ip'] = sender_ip
    
    print("\n" + "="*60)
    print(f" [! ] \033[91mVALID CANARY ALERT RECEIVED\033[0m")
    print(f" [i] Source:  {sender_ip}")
    print("="*60)
    print(json.dumps(data, indent=4, default=str))

    collection.insert_one(data)
    logging.info(f"Alert stored from {sender_ip}")
    return jsonify({"status": "success"}), 200

if __name__ == '__main__':
    print(f"[*] Listener running on port 9000")
    app.run(host='0.0.0.0', port=9000)
