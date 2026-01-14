from pymongo import MongoClient
from bson. json_util import dumps
import sys

# Connect to DB with timeout
try:
    client = MongoClient('mongodb://localhost:27017/', serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
except Exception as e: 
    print(f"[ERROR] Cannot connect to MongoDB: {e}")
    sys.exit(1)

db = client['honeypot_db']
collection = db['canary_alerts']

# Get the last 10 alerts
alerts = list(collection.find().sort('_id', -1).limit(10))

if not alerts:
    print("No alerts found in the database.")
    sys.exit(0)

print(f"\n{'ID':<4} | {'TIME':<25} | {'IP ADDRESS':<15} | {'MEMO'}")
print("-" * 70)

for index, alert in enumerate(alerts):
    time = alert. get('time', alert.get('_received_at', 'N/A'))
    src_ip = alert.get('src_ip', alert.get('_sender_ip', 'Unknown'))
    memo = alert.get('memo', 'No Memo')[:40]  # Truncate long memos
    print(f"[{index}]  | {str(time):<25} | {src_ip:<15} | {memo}")

print("-" * 70)

try:
    choice = int(input("\nEnter the ID number to view FULL details (or -1 to exit): "))
    if choice == -1:
        sys.exit(0)
    if 0 <= choice < len(alerts):
        selected_alert = alerts[choice]
        print(f"\n" + "="*60)
        print(f" FULL DATA FOR ALERT FROM {selected_alert. get('src_ip', 'Unknown')}")
        print("="*60)
        print(dumps(selected_alert, indent=4))
    else: 
        print("Invalid selection.")
except ValueError: 
    print("Please enter a number.")
except KeyboardInterrupt: 
    print("\nExiting.")
