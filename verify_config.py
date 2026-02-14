import toml
from notion_client import Client
import sys

def verify():
    print("--- Verifying Configuration ---")
    
    # 1. Load Secrets
    try:
        secrets = toml.load(".streamlit/secrets.toml")
        print("[OK] loaded .streamlit/secrets.toml")
    except Exception as e:
        print(f"[ERROR] Failed to load secrets.toml: {e}")
        return

    # Extract keys (handling both top-level and [secrets] section just in case)
    token = secrets.get("NOTION_TOKEN")
    db_id = secrets.get("DATABASE_ID")
    goal_db_id = secrets.get("GOAL_DATABASE_ID")

    # Fallback to checking inside "secrets" key if top-level is missing (common streamlit pattern confusion)
    if not token and "secrets" in secrets:
         token = secrets["secrets"].get("NOTION_TOKEN")
         db_id = secrets["secrets"].get("DATABASE_ID")
         goal_db_id = secrets["secrets"].get("GOAL_DATABASE_ID")

    print(f"Token found: {'Yes' if token else 'No'}")
    print(f"Database ID: {db_id}")
    print(f"Goal Database ID: {goal_db_id}")

    if not token or not db_id:
        print("[ERROR] Missing Token or Database ID")
        return

    # 2. Verify Client Auth
    notion = Client(auth=token)
    try:
        user = notion.users.me()
        name = user.get('name', 'Unknown')
        if not name:
            name = user.get('bot', {}).get('owner', {}).get('user', {}).get('name', 'Unknown')
        print(f"[OK] Authentication Successful. Bot User: {name}")
    except Exception as e:
        print(f"[ERROR] Authentication Failed: {e}")
        return

    # 3. Verify Database Access
    for name, did in [("Learning Log", db_id), ("Goal DB", goal_db_id)]:
        if not did:
            print(f"[WARN] Skipping {name} (No ID provided)")
            continue
            
        print(f"Testing access to {name} ({did})...")
        try:
            # Try to retrieve database details
            # We use request directly to mirror the app's workaround, and also ensure the ID is valid
            db = notion.request(path=f"databases/{did}", method="GET")
            title = "Untitled"
            if "title" in db and db["title"]:
                 title = db["title"][0].get("plain_text", "Untitled")
            print(f"[OK] Successfully accessed {name}: {title}")
            
            # Test Query (POST) via httpx directly
            print(f"Testing query via httpx on {name}...")
            import httpx
            
            url = f"https://api.notion.com/v1/databases/{did}/query"
            headers = {
                "Authorization": f"Bearer {token}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json"
            }
            
            try:
                resp = httpx.post(url, headers=headers, json={"page_size": 1})
                if resp.status_code == 200:
                    print(f"[OK] HTTPX Query success. Found {len(resp.json().get('results', []))} items.")
                else:
                    print(f"[ERROR] HTTPX Query failed: {resp.status_code} - {resp.text}")
                    
            except Exception as e:
                 print(f"[ERROR] HTTPX Request failed: {e}")
            
        except Exception as e:
            print(f"[ERROR] Failed to access/query {name}: {e}")
            print("   -> Check if the integration is added to this database in Notion.")
            print("   -> Check if the Database ID is correct.")

    # 4. Search for accessible databases
    print("\n--- Verification Complete ---")

if __name__ == "__main__":
    verify()
