import os
import requests
import json
import time
from datetime import datetime

# Credentials from GitHub Secrets
APP_ID = os.getenv('HS_APP_ID')
APP_SECRET = os.getenv('HS_APP_SECRET')
CHECKPOINT_FILE = "last_page.txt"

def get_token():
    url = "https://api.helpscout.net/v2/oauth2/token"
    data = {"grant_type": "client_credentials", "client_id": APP_ID, "client_secret": APP_SECRET}
    response = requests.post(url, data=data)
    return response.json()['access_token']

def get_threads(convo_id, headers):
    """Fetches the full history (replies/notes) of a conversation."""
    url = f"https://api.helpscout.net/v2/conversations/{convo_id}/threads"
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        return res.json().get('_embedded', {}).get('threads', [])
    return []

def sync():
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    # Checkpoint Logic
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "r") as f:
            page = int(f.read().strip())
    else:
        page = 1
    
    processed_this_run = 0

    while True:
        # SAFETY BATCH: Commit every 500 pages to avoid 6-hour timeout
        if processed_this_run >= 500:
            print(f"Batch limit reached. Progress saved at page {page}.")
            break

        url = f"https://api.helpscout.net/v2/conversations?page={page}&status=all&sortField=createdAt&sortOrder=asc"
        response = requests.get(url, headers=headers).json()
        conversations = response.get('_embedded', {}).get('conversations', [])
        
        if not conversations:
            print("Reached the end of history.")
            if os.path.exists(CHECKPOINT_FILE):
                os.remove(CHECKPOINT_FILE)
            break

        for convo in conversations:
            # 1. Categorization Logic (Company > Domain > Uncategorized)
            customer = convo.get('customer', {})
            company = customer.get('organization')
            if not company:
                company = customer.get('email', '').split('@')[-1] or "Uncategorized"
            
            # Sanitize folder name
            clean_company = "".join(x for x in company if x.isalnum() or x in "._- ").strip().replace(" ", "_")
            
            # 2. Get Full Conversation Detail (Threads/Notes)
            convo['full_threads'] = get_threads(convo['id'], headers)
            
            # 3. Save to Organized Folder Structure
            year = convo['createdAt'][:4]
            folder_path = f"archive/{clean_company}/{year}"
            os.makedirs(folder_path, exist_ok=True)

            file_path = f"{folder_path}/{convo['id']}.json"
            with open(file_path, 'w') as f:
                json.dump(convo, f, indent=4)
        
        # Update checkpoint
        page += 1
        processed_this_run += 1
        with open(CHECKPOINT_FILE, "w") as f:
            f.write(str(page))
            
        print(f"Successfully processed page {page - 1}")
        time.sleep(0.2) # Help Scout Rate Limit Protection

    # Re-build the Master Search Index
    generate_index()

def generate_index():
    """Creates a searchable map for the team's tools."""
    master_index = []
    print("Generating Master Index...")
    for root, dirs, files in os.walk("archive"):
        for file in files:
            if file.endswith(".json"):
                with open(os.path.join(root, file), 'r') as f:
                    data = json.load(f)
                    master_index.append({
                        "id": data.get("id"),
                        "subject": data.get("subject"),
                        "company": root.split('/')[1],
                        "tags": [tag['name'] for tag in data.get('tags', [])],
                        "customer": data.get('customer', {}).get('email'),
                        "status": data.get("status"),
                        "path": f"{root}/{file}"
                    })
    
    with open("index.json", "w") as f:
        json.dump(master_index, f, indent=4)

if __name__ == "__main__":
    sync()
