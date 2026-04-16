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
    
    rows = worksheet.get_all_records(
        expected_headers=["ADRESSE", "PROJECT CODE", "N° COMPTE INTERNET", "N° DE CONTRAT", "STATUS"]
    )
    
    mapping = {}
    for row in rows:
        compte = str(row.get("N° COMPTE INTERNET", "")).strip()
        if not compte:
            continue
        mapping[compte] = {
            "adresse": str(row.get("ADRESSE", "")).strip(),
            "code_projet": str(row.get("PROJECT CODE", "")).strip(),
            "numero_contrat": str(row.get("N° DE CONTRAT", "")).strip(),
        }
    
    return mapping
