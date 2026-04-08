import os
import json
import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly"
]

def test_connexion():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    
    # Liste tous les sheets accessibles par le compte de service
    all_sheets = client.list_spreadsheet_files()
    print(f"Sheets accessibles : {len(all_sheets)}")
    for s in all_sheets:
        print(f"  - {s['name']} : {s['id']}")

if __name__ == "__main__":
    test_connexion()
