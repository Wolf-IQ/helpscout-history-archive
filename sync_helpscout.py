import os
import requests
import json
import time
import sys
from datetime import datetime

# Credentials from GitHub Secrets
APP_ID = os.getenv('HS_APP_ID')
APP_SECRET = os.getenv('HS_APP_SECRET')
CHECKPOINT_FILE = "last_page.txt"

def print_flush(text):
    """Ensures logs appear immediately in GitHub Actions."""
    print(text)
    sys.stdout.flush()

def get_token():
    url = "https://api.helpscout.net/v2/oauth2/token"
    data = {"grant_type": "client_credentials", "client_id": APP_ID, "client_secret": APP_SECRET}
    response = requests.post(url, data=data)
    return response.json()['access_token']

def get_threads(convo_id, headers):
    """Fetches the full history (replies/notes) of a conversation with error handling."""
    url = f"https://api.helpscout.net/v2/conversations/{convo_id}/threads"
    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code == 200:
            return res.json().get('_embedded', {}).get('threads', [])
        elif res.status_code == 429:
            print_flush("Rate limit hit. Sleeping for 10 seconds...")
            time.sleep(10)
            return get_threads(convo_id, headers)
        else:
            return []
    except Exception as e:
        print_flush(f"Error fetching threads for ticket {convo_id}: {e}")
        return []

def sync():
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "r") as f:
            page = int(f.read().strip())
    else:
        page = 1
    
    processed_this_run = 0

    while True:
        # Batch limit to prevent GitHub timeout
        if processed_this_run >= 500:
            print_flush(f"Batch limit reached. Progress saved at page {page}.")
            break

        url = f"https://api.helpscout.net/v2/conversations?page={page}&status=all&sortField=createdAt&sortOrder=asc"
        try:
            res = requests.get(url, headers=headers)
            response = res.json()
        except Exception as e:
            print_flush(f"Critical error on page {page}: {e}")
            break

        conversations = response.get('_embedded', {}).get('conversations', [])
        
        if not conversations:
            print_flush("Reached the end of history.")
            if os.path.exists(CHECKPOINT_FILE):
                os.remove(CHECKPOINT_FILE)
            break

        for convo in conversations:
            customer = convo.get('customer', {})
            company = customer.get('organization')
            if not company:
                company = customer.get('email', '').split('@')[-1] or "Uncategorized"
            
            clean_company = "".join(x for x in company if x.isalnum() or x in "._- ").strip().replace(" ", "_")
            
            # Fetch threads
            convo['full_threads'] = get_threads(convo['id'], headers)
            
            # Organize by Company/Year
            year = convo['createdAt'][:4]
            folder_path = f"archive/{clean_company}/{year}"
            os.makedirs(folder_path, exist_ok=True)

            file_path = f"{folder_path}/{convo['id']}.json"
            with open(file_path, 'w') as f:
                json.dump(convo, f, indent=4)
        
        page += 1
        processed_this_run += 1
        with open(CHECKPOINT_FILE, "w") as f:
            f.write(str(page))
            
        print_flush(f"Successfully processed page {page - 1}")
        time.sleep(0.3)

    generate_index()

def generate_index():
    """Robust index generation that handles inconsistent tag structures."""
    master_index = []
    print_flush("Generating Master Index...")
    
    if not os.path.exists("archive"):
        return

    for root, dirs, files in os.walk("archive"):
        for file in files:
            if file.endswith(".json") and file != "index.json":
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r') as f:
                        data = json.load(f)
                        
                        # Extract company name from the folder path safely
                        path_parts = root.split(os.sep)
                        company_name = path_parts[1] if len(path_parts) > 1 else "Unknown"
                        
                        # DEFENSIVE TAG EXTRACTION:
                        # Handles [{'name': 'tag1'}, {'id': 123}] or just ['tag1', 'tag2']
                        raw_tags = data.get('tags', [])
                        clean_tags = []
                        for tag in raw_tags:
                            if isinstance(tag, dict):
                                # Use .get() to avoid KeyError if 'name' is missing
                                tag_name = tag.get('name')
                                if tag_name:
                                    clean_tags.append(tag_name)
                            elif isinstance(tag, str):
                                clean_tags.append(tag)
                        
                        master_index.append({
                            "id": data.get("id"),
                            "subject": data.get("subject"),
                            "company": company_name,
                            "tags": clean_tags,
                            "customer": data.get('customer', {}).get('email'),
                            "status": data.get("status"),
                            "path": file_path
                        })
                except Exception as e:
                    # Skip the file if it's empty or corrupted
                    print_flush(f"Skipping {file}: {e}")
                    continue
    
    with open("index.json", "w") as f:
        json.dump(master_index, f, indent=4)
    print_flush(f"Index successfully generated with {len(master_index)} tickets.")

if __name__ == "__main__":
    sync()
