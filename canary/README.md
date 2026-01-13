# Canarytoken Email Collector

Small Python daemon that:
- Connects to a Gmail inbox via IMAP.
- Searches for **unseen Canarytoken alert emails**.
- Parses the text/plain part of the email.
- Prints the parsed record and stores it in MongoDB.

## Requirements

- Python 3
- MongoDB server (`mongod`).
- Gmail account with IMAP enabled.
- Python packages: `pymongo`, `python-dotenv`.

## Install MongoDB

Install MongoDB for your OS using the [official MongoDB documentation](https://www.mongodb.com/docs/manual/installation/).

After installing, start and enable it:

```bash
sudo systemctl enable --now mongod
```

## Setup Python env

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pymongo python-dotenv
```

## Configure .env

Create a `.env` file in the same directory as `fetch-canary.py`:

```env
IMAP_USER="yourmail@gmail.com"
IMAP_APP_PASS="your app password"
MONGO_URI="mongodb://localhost:yourport"
```

> usually MONGO_URI="mongodb://localhost:27017"

## Run

```bash
source .venv/bin/activate
python3 fetch-canary.py
```

The script polls continuously (var `POLLING_SECONDS` in the code) and inserts new alerts into MongoDB.

## View stored data

Connect:

```bash
mongosh "mongodb://localhost:27017"
```

Select DB and inspect collections:

```javascript
use honeypot
show collections
```

Show latest alerts (sort + limit):

```javascript
db.canary_alerts.find().sort({ inserted_at_utc: -1 }).limit(10)
```

Filter examples:

```javascript
db.canary_alerts.find({ token_id: "tys2jxn1qpp2nt2anh4vjgdj9" })
db.canary_alerts.find({ source_ip: "132.205.151.32" })
```

Count documents:

```javascript
db.canary_alerts.countDocuments()
```
