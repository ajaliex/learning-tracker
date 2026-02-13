import httpx
import toml
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

def inspect():
    print("--- Inspecting Data Structure ---")
    
    try:
        secrets = toml.load(".streamlit/secrets.toml")
        token = secrets.get("NOTION_TOKEN")
        db_id = secrets.get("DATABASE_ID")
        goal_db_id = secrets.get("GOAL_DATABASE_ID")
    except Exception as e:
        print(f"Failed to load secrets: {e}")
        return

    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }

    # Helper to check a DB
    def check_db(name, did):
        print(f"\nScanning {name} ({did})...")
        url = f"https://api.notion.com/v1/databases/{did}/query"
        try:
            resp = httpx.post(url, headers=headers, json={"page_size": 1})
            if resp.status_code != 200:
                print(f"[ERROR] HTTP {resp.status_code}: {resp.text}")
                return
            
            data = resp.json()
            results = data.get("results", [])
            
            if not results:
                print("[WARN] Database is empty (0 results returned).")
                return
            
            print(f"[OK] Found {len(results)} sample item(s).")
            first_item = results[0]
            props = first_item.get("properties", {})
            print("Property Names Found:")
            for key, val in props.items():
                type_name = val.get("type", "unknown")
                print(f" - '{key}' ({type_name})")
                
        except Exception as e:
            print(f"[ERROR] Request failed: {e}")

    check_db("Learning Log (Source of Truth)", db_id)
    check_db("Goal DB", goal_db_id)

if __name__ == "__main__":
    inspect()
