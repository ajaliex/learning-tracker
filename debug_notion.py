from notion_client import Client
import os

print("Debugging Notion Client...")
try:
    # Use a dummy token if necessary, or try to load from secrets if accessible.
    # Since we can't easily load streamlit secrets here without running streamlit, 
    # we'll just check the attributes of the class/object.
    
    notion = Client(auth="dummy_token")
    print(f"Client object: {notion}")
    print(f"Databases endpoint: {notion.databases}")
    print(f"Attributes of notion.databases: {dir(notion.databases)}")
    
    if hasattr(notion.databases, 'query'):
        print("SUCCESS: 'query' method exists.")
    else:
        print("FAILURE: 'query' method DOES NOT exist.")

except Exception as e:
    print(f"An error occurred: {e}")
