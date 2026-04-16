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
    
    if len(all_values) < 2:
        return {}
    
    # Chercher la ligne qui contient "ADRESSE" comme header
    headers = []
    header_row_idx = 0
    for i, row in enumerate(all_values):
        if any("adresse" in cell.lower() for cell in row):
            headers = [cell.strip() for cell in row]
            header_row_idx = i
            break
    
    if not headers:
        print("   → Headers introuvables !")
        return {}

    print(f"   → Headers trouvés à la ligne {header_row_idx} : {headers}")

    # Trouver les index des colonnes par mot-clé
    def find_col(keyword):
        for i, h in enumerate(headers):
            if keyword.lower() in h.lower():
                return i
        return None
    
    idx_compte  = find_col("compte internet")
    idx_adresse = find_col("adresse")
    idx_projet  = find_col("project code")
    idx_contrat = find_col("contrat")

    print(f"   → idx_compte={idx_compte}, idx_adresse={idx_adresse}, idx_projet={idx_projet}, idx_contrat={idx_contrat}")

    mapping = {}
    for row in all_values[header_row_idx + 1:]:
        if not row:
            continue
        
        def get_val(idx):
            if idx is not None and idx < len(row):
                return row[idx].strip()
            return ""
        
        compte = get_val(idx_compte)
        if not compte:
            continue
        
        mapping[compte] = {
            "adresse":        get_val(idx_adresse),
            "code_projet":    get_val(idx_projet),
            "numero_contrat": get_val(idx_contrat),
        }
    
    return mapping
