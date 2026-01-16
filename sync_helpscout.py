import os
import requests
import json
import time
import sys
from datetime import datetime, timedelta

# Credentials
APP_ID = os.getenv('HS_APP_ID')
APP_SECRET = os.getenv('HS_APP_SECRET')
TRACKER_FILE = "next_month.txt"

def print_flush(text):
    print(text)
    sys.stdout.flush()

def get_token():
    url = "https://api.helpscout.net/v2/oauth2/token"
    data = {"grant_type": "client_credentials", "client_id": APP_ID, "client_secret": APP_SECRET}
    response = requests.post(url, data=data)
    return response.json()['access_token']

def get_threads(convo_id, headers):
    url = f"https://api.helpscout.net/v2/conversations/{convo_id}/threads"
    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code == 200:
            return res.json().get('_embedded', {}).get('threads', [])
        return []
    except:
        return []

def get_target_month():
    """Reads the tracker file or defaults to current month."""
    if os.path.exists(TRACKER_FILE):
        with open(TRACKER_FILE, "r") as f:
            date_str = f.read().strip()
            return datetime.strptime(date_str, "%Y-%m-%d")
    # If first run, start with current month
    return datetime.now().replace(day=1)

def sync():
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    # 1. Determine the Month Range
    current_target = get_target_month()
    start_date = current_target.strftime("%Y-%m-%dT00:00:00Z")
    
    # End date is the last second of the month
    next_month = (current_target + timedelta(days=32)).replace(day=1)
    end_date = (next_month - timedelta(seconds=1)).strftime("%Y-%m-%dT23:59:59Z")
    
    print_flush(f"🚀 SYNCING BATCH: {start_date} to {end_date}")
    
    page = 1
    total_convos = 0

    while True:
        query = f"(createdAt:[{start_date} TO {end_date}])"
        url = f"https://api.helpscout.net/v2/conversations?query={query}&page={page}&status=all"
        
        res = requests.get(url, headers=headers)
        if res.status_code != 200:
            break
            
        data = res.json()
        conversations = data.get('_embedded', {}).get('conversations', [])
        
        if not conversations:
            break

        for convo in conversations:
            # Categorization Logic
            customer = convo.get('customer', {})
            company = customer.get('organization')
            if not company:
                email = customer.get('email', '')
                company = email.split('@')[-1] if '@' in email else "Uncategorized"
            
            clean_company = "".join(x for x in company if x.isalnum() or x in "._- ").strip().replace(" ", "_")
            convo['full_threads'] = get_threads(convo['id'], headers)
            
            year = convo['createdAt'][:4]
            folder_path = f"archive/{clean_company}/{year}"
            os.makedirs(folder_path, exist_ok=True)

            with open(f"{folder_path}/{convo['id']}.json", 'w') as f:
                json.dump(convo, f, indent=4)
            total_convos += 1
        
        print_flush(f"✅ Processed Page {page}")
        page += 1
        time.sleep(0.2)

    # 2. Update tracker for NEXT run (move back 1 month)
    prev_month = (current_target - timedelta(days=1)).replace(day=1)
    with open(TRACKER_FILE, "w") as f:
        f.write(prev_month.strftime("%Y-%m-%d"))

    print_flush(f"🏁 Month Complete. Total: {total_convos}. Tracker updated to {prev_month.strftime('%Y-%m')}")
    generate_index()

def generate_index():
    master_index = []
    if not os.path.exists("archive"): return
    for root, dirs, files in os.walk("archive"):
        for file in files:
            if file.endswith(".json") and file != "index.json":
                try:
                    with open(os.path.join(root, file), 'r') as f:
                        d = json.load(f)
                        master_index.append({
                            "id": d.get("id"),
                            "subject": d.get("subject"),
                            "company": root.split(os.sep)[1],
                            "date": d.get("createdAt"),
                            "path": os.path.join(root, file)
                        })
                except: continue
    with open("index.json", "w") as f:
        json.dump(master_index, f, indent=4)

if __name__ == "__main__":
    sync()
