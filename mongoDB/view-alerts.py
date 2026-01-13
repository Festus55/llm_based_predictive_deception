from pymongo import MongoClient
import json
from bson.json_util import dumps

# Connect to DB
client = MongoClient('mongodb://localhost:27017/')
db = client['honeypot_db']
collection = db['canary_alerts']

# Get the last 10 alerts
alerts = list(collection.find().sort('_id', -1).limit(10))

if not alerts:
    print("No alerts found in the database.")
    exit()

print(f"\n{'ID':<4} | {'TIME':<25} | {'IP ADDRESS':<15} | {'MEMO'}")
print("-" * 60)

# Print a summary list
for index, alert in enumerate(alerts):
    time = alert.get('time', 'N/A')
    src_ip = alert.get('src_ip', 'Unknown')
    memo = alert.get('memo', 'No Memo')
    print(f"[{index}]  | {time:<25} | {src_ip:<15} | {memo}")

print("-" * 60)

# Ask user which one to view
try:
    choice = int(input("\nEnter the ID number to view FULL details (or -1 to exit): "))
    if choice == -1:
        exit()
        
    if 0 <= choice < len(alerts):
        selected_alert = alerts[choice]
        print(f"\n" + "="*60)
        print(f" FULL DATA FOR ALERT FROM {selected_alert.get('src_ip')}")
        print("="*60)
        # This prints EVERYTHING stored in MongoDB for that entry
        print(dumps(selected_alert, indent=4))
    else:
        print("Invalid selection.")
except ValueError:
    print("Please enter a number.")

