import httpx
import toml
import json

def debug_request():
    print("--- Debugging 400 Bad Request ---")
    
    try:
        secrets = toml.load(".streamlit/secrets.toml")
        token = secrets.get("NOTION_TOKEN") or secrets["secrets"].get("NOTION_TOKEN")
        db_id = secrets.get("DATABASE_ID") or secrets["secrets"].get("DATABASE_ID")
    except Exception as e:
        print(f"Failed to load secrets: {e}")
        return

    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    
    # Test case 1: start_cursor is None (Simulating app.py current state)
    print("\nTest Case 1: Sending start_cursor=None")
    body_with_none = {
        "start_cursor": None,
        "page_size": 100
    }
    try:
        resp = httpx.post(url, headers=headers, json=body_with_none)
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text[:200]}...")
    except Exception as e:
        print(f"Request failed: {e}")

    # Test case 2: Omitting start_cursor
    print("\nTest Case 2: Omitting start_cursor key")
    body_without_cursor = {
        "page_size": 100
    }
    try:
        resp = httpx.post(url, headers=headers, json=body_without_cursor)
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text[:200]}...")
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    debug_request()
