# sheets_reader.py
import gspread
from google.oauth2.service_account import Credentials
import os
import json
import re

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
    adresse = adresse.upper().strip()
    adresse = re.sub(r'\s+', ' ', adresse)
    adresse = re.sub(r'\.\.\s*', ' ', adresse)
    return adresse.strip()

def clean_adresse_key(adresse: str) -> str:
    adresse = adresse.upper()
    for mot in ['ATELIER', 'PAV', '1ET', '2ET', 'RDC', 'BAT', 'BATIMENT']:
        adresse = adresse.replace(mot, '')
    adresse = adresse.replace(' ', '')
    return adresse.strip()

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
    if idx_compte is None:
        idx_compte = find_col("ref client")
    is_endesa   = idx_compte is None

    idx_adresse = find_col("adresse")
    idx_projet  = find_col("project code")
    idx_contrat = find_col("contrat")
    idx_status  = find_col("status")

    print(f"   → idx_compte={idx_compte}, idx_adresse={idx_adresse}, idx_projet={idx_projet}, idx_contrat={idx_contrat}, idx_status={idx_status}")
    print(f"   → Mode matching : {'ADRESSE (Endesa)' if is_endesa else 'COMPTE'}")

    mapping = {}
    for row_idx, row in enumerate(all_values[header_row_idx + 1:], start=header_row_idx + 2):
        if not row:
            continue

        def get_val(idx):
            if idx is not None and idx < len(row):
                return row[idx].strip()
            return ""

        if is_endesa:
            adresse_raw = get_val(idx_adresse)
            if not adresse_raw:
                continue
            ref_contrat = get_val(idx_contrat)
            adresse_cle = clean_adresse_key(adresse_raw)

            if adresse_cle and ref_contrat:
                cle = adresse_cle + '_' + ref_contrat
            else:
                cle = adresse_cle
        else:
            cle = get_val(idx_compte)
            if not cle:
                continue

        mapping[cle] = {
            "adresse":        get_val(idx_adresse),
            "code_projet":    get_val(idx_projet),
            "numero_contrat": get_val(idx_contrat),
            "row_idx":        row_idx,
            "status_col":     idx_status,
            "adresse_cle":    clean_adresse_key(get_val(idx_adresse)) if is_endesa else None,
        }

    print(f"       → {len(mapping)} comptes chargés")
    return mapping


def find_or_create_endesa_line(sheet_id: str, month_tab: str, adresse: str, ref_contrat: str, mapping: dict) -> dict:
    """
    Pour Endesa :
    - Si adresse+contrat déjà dans mapping → retourne la ligne
    - Si adresse seule trouvée sans contrat → met à jour la ref contrat et retourne la ligne
    - Si adresse avec contrat différent → crée une nouvelle ligne avec même project code
    - Si adresse inconnue → skipe
    """
    adresse_cle = clean_adresse_key(adresse)
    cle_complete = adresse_cle + '_' + ref_contrat if ref_contrat else adresse_cle

    # Cas 1 : ligne exacte trouvée
    if cle_complete in mapping:
        return mapping[cle_complete]

    # Cas 2 : adresse seule trouvée sans ref contrat
    if adresse_cle in mapping:
        ligne = mapping[adresse_cle]
        if ref_contrat:
            print(f"       📝 Ajout ref contrat {ref_contrat} sur ligne existante ({adresse})")
            try:
                client = get_client()
                sheet = client.open_by_key(sheet_id)
                worksheet = sheet.worksheet(month_tab)
                # Trouver la colonne contrat
                headers = worksheet.row_values(1)
                if len(headers) < 2:
                    headers = worksheet.row_values(2)
                idx_contrat = next((i+1 for i, h in enumerate(headers) if 'contrat' in h.lower()), None)
                if idx_contrat:
                    worksheet.update_cell(ligne['row_idx'], idx_contrat, ref_contrat)
                    # Mettre à jour le mapping en mémoire
                    mapping[cle_complete] = {**ligne, 'numero_contrat': ref_contrat}
                    del mapping[adresse_cle]
                    return mapping[cle_complete]
            except Exception as e:
                print(f"       ⚠️  Erreur mise à jour ref contrat : {e}")
        return ligne

    # Cas 3 : adresse avec contrat différent → chercher une ligne avec même adresse
    lignes_meme_adresse = [v for k, v in mapping.items() if v.get('adresse_cle') == adresse_cle]
    if lignes_meme_adresse:
        project_code = lignes_meme_adresse[0]['code_projet']
        print(f"       📝 Nouveau contrat {ref_contrat} pour {adresse} → Project Code {project_code} — création ligne")
        try:
            client = get_client()
            sheet = client.open_by_key(sheet_id)
            worksheet = sheet.worksheet(month_tab)
            headers = worksheet.row_values(1)
            if len(headers) < 2:
                headers = worksheet.row_values(2)

            new_row = [''] * len(headers)
            for i, h in enumerate(headers):
                h_low = h.lower()
                if 'adresse' in h_low:
                    new_row[i] = adresse
                elif 'project' in h_low:
                    new_row[i] = project_code
                elif 'contrat' in h_low:
                    new_row[i] = ref_contrat
                elif 'status' in h_low:
                    new_row[i] = False

            worksheet.append_row(new_row)
            all_values = worksheet.get_all_values()
            new_row_idx = len(all_values)
            status_col = next((i for i, h in enumerate(headers) if 'status' in h.lower()), None)

            new_entry = {
                "adresse":        adresse,
                "code_projet":    project_code,
                "numero_contrat": ref_contrat,
                "row_idx":        new_row_idx,
                "status_col":     status_col,
                "adresse_cle":    adresse_cle,
            }
            mapping[cle_complete] = new_entry
            print(f"       ✅ Nouvelle ligne créée (ligne {new_row_idx})")
            return new_entry
        except Exception as e:
            print(f"       ❌ Erreur création ligne : {e}")
            return None

    # Cas 4 : adresse inconnue
    print(f"       ⚠️  Adresse '{adresse}' inconnue dans le mapping - skipped")
    return None


def mark_as_done(sheet_id: str, month_tab: str, row_idx: int, status_col: int):
    try:
        client = get_client()
        sheet = client.open_by_key(sheet_id)
        worksheet = sheet.worksheet(month_tab)
        worksheet.update_cell(row_idx, status_col + 1, True)
        print(f"       ✅ Case STATUS cochée (ligne {row_idx})")
    except Exception as e:
        print(f"       ⚠️  Erreur cochage STATUS : {e}")
