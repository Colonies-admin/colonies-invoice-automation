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

def get_mapping(sheet_id: str, month_tab: str) -> dict:
    client = get_client()
    sheet = client.open_by_key(sheet_id)

    try:
        worksheet = sheet.worksheet(month_tab)
    except gspread.WorksheetNotFound:
        raise ValueError(f"Onglet '{month_tab}' introuvable dans le Google Sheets")

    all_values = worksheet.get_all_values()

    print(f"   → Lignes brutes récupérées : {len(all_values)}")

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

    def find_col(keyword):
        for i, h in enumerate(headers):
            if keyword.lower() in h.lower():
                return i
        return None

    idx_compte  = find_col("compte internet")
    idx_adresse = find_col("adresse")
    idx_projet  = find_col("project code")
    idx_contrat = find_col("contrat")
    idx_status  = find_col("status")

    print(f"   → idx_compte={idx_compte}, idx_adresse={idx_adresse}, idx_projet={idx_projet}, idx_contrat={idx_contrat}, idx_status={idx_status}")

    mapping = {}
    for row_idx, row in enumerate(all_values[header_row_idx + 1:], start=header_row_idx + 2):
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
            "row_idx":        row_idx,
            "status_col":     idx_status
        }

    return mapping


def mark_as_done(sheet_id: str, month_tab: str, row_idx: int, status_col: int):
    try:
        client = get_client()
        sheet = client.open_by_key(sheet_id)
        worksheet = sheet.worksheet(month_tab)
        worksheet.update_cell(row_idx, status_col + 1, True)
        print(f"       ✅ Case STATUS cochée (ligne {row_idx})")
    except Exception as e:
        print(f"       ⚠️  Erreur cochage STATUS : {e}")
