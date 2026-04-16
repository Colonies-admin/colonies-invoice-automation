import gspread
from google.oauth2.service_account import Credentials
import os
import json

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly"
]

def get_mapping(sheet_id: str, month_tab: str) -> dict:
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if not creds_json:
        raise ValueError("GOOGLE_CREDENTIALS manquant dans les secrets")
    
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    
    sheet = client.open_by_key(sheet_id)
    
    try:
        worksheet = sheet.worksheet(month_tab)
    except gspread.WorksheetNotFound:
        raise ValueError(f"Onglet '{month_tab}' introuvable dans le Google Sheets")
    
    all_values = worksheet.get_all_values()
    
    print(f"   → Lignes brutes récupérées : {len(all_values)}")
    print(f"   → Ligne 1 : {all_values[0] if all_values else 'vide'}")
    print(f"   → Ligne 2 : {all_values[1] if len(all_values) > 1 else 'vide'}")
    print(f"   → Ligne 3 : {all_values[2] if len(all_values) > 2 else 'vide'}")

    if len(all_values) < 2:
        return {}
    
    # Trouver la ligne d'en-tête (première ligne non vide)
    headers = []
    header_row_idx = 0
    for i, row in enumerate
