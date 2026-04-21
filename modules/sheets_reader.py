import gspread
from google.oauth2.service_account import Credentials
import os
import json

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def get_client():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if not creds_json:
        raise ValueError("GOOGLE_CREDENTIALS manquant dans les secrets")
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)

def normalise_adresse(adresse: str) -> str:
    import re
    adresse = adresse.upper().strip()
    adresse = re.sub(r'\s+', ' ', adresse)
    adresse = re.sub(r'\.\.\s*', ' ', adresse)
    return adresse.strip()

def clean_adresse_key(adresse: str) -> str:
    return adresse.upper().replace(' ', '').replace('ATELIER', '').replace('PAV', '').replace('1ET', '').strip()

def get_mapping(sheet_id: str, month_tab: str) -> dict:
    client = get_client()
    sheet = client.open_by_key(sheet_id)

    try:
        worksheet = sheet.worksheet(month_tab)
    except gspread.WorksheetNotFound:
        raise ValueError(f"Onglet '{month_tab}' introuvable dans le Google Sheets")

    all_values = worksheet.get_all_values()
    print(f"   → Lignes brutes réc
