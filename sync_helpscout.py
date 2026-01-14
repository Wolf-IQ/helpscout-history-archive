import os
import requests
import json
import time
from datetime import datetime

APP_ID = os.getenv('HS_APP_ID')
APP_SECRET = os.getenv('HS_APP_SECRET')

def get_token():
    url = "https://api.helpscout.net/v2/oauth2/token"
    data = {"grant_type": "client_credentials", "client_id": APP_ID, "client_secret": APP_SECRET}
    return requests.post(url, data=data).json()['access_token']

def get_threads(convo_id, headers):
    """Fetches full conversation threads (replies and notes)."""
    url = f"https://api.helpscout.net/v2/conversations/{convo_id}/threads"
    res = requests.get(url, headers=headers)
    return res.json().get('_embedded', {}).get('threads', [])

def sync():
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    page = 1
    
    while True:
        # Fetching conversations page by page
        url = f"https://api.helpscout.net/v2/conversations?page={page}&status=all"
        response = requests.get(url, headers=headers).json()
        conversations = response.get('_embedded', {}).get('conversations', [])
        
        if not conversations:
            break

        for convo in conversations:
            customer = convo.get('customer', {})
            # Sorting logic: Organization > Domain > Uncategorized
            company = customer.get('organization')
            if not company:
                company = customer.get('email', '').split('@')[-1] or "Uncategorized"
            
            company_folder = "".join(x for x in company if x.isalnum() or x in "._- ").strip().replace(" ", "_")
            
            # Fetch full threads for the conversation
            convo['threads'] = get_threads(convo['id'], headers)
            
            # Path: data/CompanyName/Year/ID.json
            year = convo['createdAt'][:4]
            path = f"archive/{company_folder}/{year}"
            os.makedirs(path, exist_ok=True)

            with open(f"{path}/{convo['id']}.json", 'w') as f:
                json.dump(convo, f, indent=4)
        
        print(f"Processed page {page}")
        page += 1
        time.sleep(0.5) # Rate limit protection

if __name__ == "__main__":
    sync()
