import os
import requests
import json
import time
from datetime import datetime

APP_ID = os.getenv('HS_APP_ID')
APP_SECRET = os.getenv('HS_APP_SECRET')
CHECKPOINT_FILE = "last_page.txt"

def get_token():
    url = "https://api.helpscout.net/v2/oauth2/token"
    data = {"grant_type": "client_credentials", "client_id": APP_ID, "client_secret": APP_SECRET}
    return requests.post(url, data=data).json()['access_token']

def get_threads(convo_id, headers):
    url = f"https://api.helpscout.net/v2/conversations/{convo_id}/threads"
    res = requests.get(url, headers=headers)
    return res.json().get('_embedded', {}).get('threads', [])

def sync():
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    # Checkpoint logic: Read last successful page
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "r") as f:
            page = int(f.read().strip())
    else:
        page = 1
    
    while True:
        url = f"https://api.helpscout.net/v2/conversations?page={page}&status=all"
        response = requests.get(url, headers=headers).json()
        conversations = response.get('_embedded', {}).get('conversations', [])
        
        if not conversations:
            # If we reach the end, reset checkpoint for next daily sync
            if os.path.exists(CHECKPOINT_FILE):
                os.remove(CHECKPOINT_FILE)
            break

        for convo in conversations:
            customer = convo.get('customer', {})
            company = customer.get('organization')
            if not company:
                company = customer.get('email', '').split('@')[-1] or "Uncategorized"
            
            company_folder = "".join(x for x in company if x.isalnum() or x in "._- ").strip().replace(" ", "_")
            convo['threads'] = get_threads(convo['id'], headers)
            
            year = convo['createdAt'][:4]
            path = f"archive/{company_folder}/{year}"
            os.makedirs(path, exist_ok=True)

            with open(f"{path}/{convo['id']}.json", 'w') as f:
                json.dump(convo, f, indent=4)
        
        # Save progress
        with open(CHECKPOINT_FILE, "w") as f:
            f.write(str(page + 1))
            
        print(f"Processed page {page}")
        page += 1
        time.sleep(0.5)

    # Generate Index for Team Tools
    generate_index()

def generate_index():
    master_index = []
    for root, dirs, files in os.walk("archive"):
        for file in files:
            if file.endswith(".json"):
                # You can add more fields here like 'subject' or 'status'
                master_index.append({
                    "id": file.replace(".json", ""),
                    "path": f"{root}/{file}"
                })
    with open("index.json", "w") as f:
        json.dump(master_index, f, indent=4)

if __name__ == "__main__":
    sync()
