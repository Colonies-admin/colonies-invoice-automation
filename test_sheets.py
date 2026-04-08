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
    
    sheet_id = os.environ.get("GOOGLE_SHEETS_ID")
    sheet = client.open_by_key(sheet_id)
    
    worksheets = sheet.worksheets()
    print("✅ Connexion réussie. Onglets trouvés :")
    for ws in worksheets:
        print(f"  - {ws.title}")

if __name__ == "__main__":
    test_connexion()
