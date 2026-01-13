import json
import logging
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

# 3. Database Connection
client = MongoClient('mongodb://localhost:27017/')
db = client['honeypot_db']
collection = db['canary_alerts']

@app.route('/webhook', methods=['POST'])
def webhook():
    # must be json
    if not request.is_json:
        return "Forbidden: JSON required", 403

    try:
        data = request.json
    except Exception:
        return "Forbidden: Malformed JSON", 403

    is_valid = False
    # standard Canary Alert
    if 'token' in data and 'manage_url' in data:
        is_valid = True
        
    # AWS Infrastructure Alert
    # must have 'text' key and contain specific keywords
    elif 'text' in data:
        text_content = str(data['text'])
        if "AWS ID Token" in text_content or "AccessKeyId" in text_content:
            is_valid = True

    if not is_valid:
        return "Forbidden: Unknown Payload Format", 403

    # SUCCESS
    sender_ip = request.remote_addr
    print("\n" + "="*60)
    print(f" [!] \033[91mVALID CANARY ALERT RECEIVED\033[0m") 
    print(f" [i] Source: {sender_ip}")
    print("="*60)
    print(json.dumps(data, indent=4))

    # Save to DB
    collection.insert_one(data)
    logging.info(f"Alert stored from {sender_ip}")
    return jsonify({"status": "success"}), 200

if __name__ == '__main__':
    print(f"[*] Payload-Secure Listener running on port 9000")
    app.run(host='0.0.0.0', port=9000)

