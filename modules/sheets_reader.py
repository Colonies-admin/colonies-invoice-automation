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
    # Supprimer les suffixes parasites
    for mot in ['ATELIER', 'PAV', '1ET', '2ET', 'RDC', 'BAT', 'BATIMENT', 'LOGEMENT', '1ER']:
        adresse = adresse.replace(mot, '')
    adresse = adresse.split(',')[0]
    adresse = re.split(r'\s*-\s*', adresse)[0]
    # Supprimer les slashes (5/7 → 57)
    adresse = adresse.replace('/', '')
    # Normaliser les espaces avant les abréviations
    adresse = re.sub(r'\s+', ' ', adresse).strip()
    # Normaliser abréviations avec ou sans espaces autour
    adresse = re.sub(r'\bAVE\b', 'AVENUE', adresse)
    adresse = re.sub(r'(?<!\w)AVE(?!\w)', 'AVENUE', adresse)
    adresse = re.sub(r'\bBD\b', 'BOULEVARD', adresse)
    adresse = re.sub(r'\bIMP\b', 'IMPASSE', adresse)
    adresse = re.sub(r'\bSQ\b', 'SQUARE', adresse)
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

    # Trouver la ligne de headers
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

    # Détection du mode selon les colonnes disponibles
    idx_compte_internet = find_col("compte internet")
    idx_ref_client      = find_col("ref client")
    idx_numero_client   = find_col("n° client")   # TotalEnergies
    idx_contrat         = find_col("contrat")
    idx_adresse         = find_col("adresse")
    idx_projet          = find_col("project code")
    idx_status          = find_col("status")
    idx_type            = find_col("type")         # TotalEnergies ELE/GAZ

    # Priorité : compte internet > ref client > n° client > adresse seule (Endesa)
    if idx_compte_internet is not None:
        mode = "COMPTE"
        idx_cle = idx_compte_internet
    elif idx_ref_client is not None:
        mode = "COMPTE"
        idx_cle = idx_ref_client
    elif idx_numero_client is not None:
        mode = "NUMERO_CLIENT"   # TotalEnergies
        idx_cle = idx_numero_client
    else:
        mode = "ADRESSE"         # Endesa
        idx_cle = None

    print(f"   → Mode matching : {mode}")
    print(f"   → idx_cle={idx_cle}, idx_adresse={idx_adresse}, idx_projet={idx_projet}, idx_contrat={idx_contrat}, idx_status={idx_status}, idx_type={idx_type}")

    mapping = {}
    for row_idx, row in enumerate(all_values[header_row_idx + 1:], start=header_row_idx + 2):
        if not row:
            continue

        def get_val(idx):
            if idx is not None and idx < len(row):
                return row[idx].strip()
            return ""

        if mode == "ADRESSE":
            # Endesa : clé = adresse_normalisée + '_' + ref_contrat
            adresse_raw = get_val(idx_adresse)
            if not adresse_raw:
                continue
            ref_contrat = get_val(idx_contrat)
            adresse_cle = clean_adresse_key(adresse_raw)
            cle = adresse_cle + '_' + ref_contrat if ref_contrat else adresse_cle

        elif mode == "NUMERO_CLIENT":
            # TotalEnergies : clé = numero_client
            # Attention : plusieurs lignes peuvent avoir le même N° client (ex: Orsay ELE ×2)
            # On les stocke toutes sous la même clé en liste
            cle = get_val(idx_cle)
            if not cle:
                continue

            entry = {
                "adresse":        get_val(idx_adresse),
                "code_projet":    get_val(idx_projet),
                "numero_contrat": get_val(idx_contrat),
                "type":           get_val(idx_type),   # ELE ou GAZ
                "row_idx":        row_idx,
                "status_col":     idx_status,
                "adresse_cle":    clean_adresse_key(get_val(idx_adresse)),
            }

            # Stocker en liste pour gérer les doublons N° client
            if cle not in mapping:
                mapping[cle] = []
            mapping[cle].append(entry)
            continue

        else:
            # COMPTE : Orange / Engie
            cle = get_val(idx_cle)
            if not cle:
                continue

        mapping[cle] = {
            "adresse":        get_val(idx_adresse),
            "code_projet":    get_val(idx_projet),
            "numero_contrat": get_val(idx_contrat),
            "row_idx":        row_idx,
            "status_col":     idx_status,
            "adresse_cle":    clean_adresse_key(get_val(idx_adresse)) if mode == "ADRESSE" else None,
        }

    print(f"   → {len(mapping)} entrées chargées (mode {mode})")
    return mapping


def find_totalenergies_entry(mapping: dict, numero_client: str, tag_ops: str) -> dict | None:
    """
    Cherche la ligne TotalEnergies dans le mapping.
    Si plusieurs lignes pour le même N° client (ex: Orsay ELE ×2),
    affine par type ELE/GAZ. Le montant sera utilisé dans airtable_writer.
    Retourne un dict unique ou None.
    """
    entries = mapping.get(numero_client)
    if not entries:
        print(f"       ⚠️  N° client '{numero_client}' introuvable dans le mapping")
        return None

    # Si une seule entrée → direct
    if len(entries) == 1:
        return entries[0]

    # Plusieurs entrées → filtrer par type ELE/GAZ
    type_cherche = "ELE" if tag_ops == "ELE-ELECTRICITY" else "GAZ"
    filtered = [e for e in entries if type_cherche in e.get('type', '').upper()]

    if len(filtered) == 1:
        return filtered[0]
    elif len(filtered) > 1:
        # Encore plusieurs (ex: 2 ELE sur même adresse) → on retourne la liste,
        # airtable_writer choisira par montant
        print(f"       ⚠️  {len(filtered)} lignes {type_cherche} pour N° client {numero_client} → affinement par montant dans Airtable")
        return filtered  # liste, pas dict
    else:
        print(f"       ⚠️  Aucune ligne {type_cherche} pour N° client {numero_client}")
        return entries[0]  # fallback première entrée


def find_or_create_endesa_line(sheet_id: str, month_tab: str, adresse: str, ref_contrat: str, mapping: dict) -> dict:
    adresse_cle = clean_adresse_key(adresse)
    cle_complete = adresse_cle + '_' + ref_contrat if ref_contrat else adresse_cle

    # Cas 1 : ligne exacte trouvée
    if cle_complete in mapping:
        return mapping[cle_complete]

    # Cas 2 : adresse seule trouvée sans ref contrat → ajouter ref contrat
    if adresse_cle in mapping:
        ligne = mapping[adresse_cle]
        adresse_sheets = ligne['adresse']
        if ref_contrat:
            print(f"       📝 Ajout ref contrat {ref_contrat} sur ligne existante ({adresse_sheets})")
            try:
                client = get_client()
                sheet = client.open_by_key(sheet_id)
                worksheet = sheet.worksheet(month_tab)
                headers = worksheet.row_values(1)
                if not any('adresse' in h.lower() for h in headers):
                    headers = worksheet.row_values(2)
                idx_contrat = next((i+1 for i, h in enumerate(headers) if 'contrat' in h.lower()), None)
                if idx_contrat:
                    worksheet.update_cell(ligne['row_idx'], idx_contrat, ref_contrat)
                    mapping[cle_complete] = {**ligne, 'numero_contrat': ref_contrat}
                    del mapping[adresse_cle]
                    return mapping[cle_complete]
            except Exception as e:
                print(f"       ⚠️  Erreur mise à jour ref contrat : {e}")
        return ligne

    # Cas 3 : adresse avec contrat différent → créer nouvelle ligne
    lignes_meme_adresse = [v for k, v in mapping.items() if v.get('adresse_cle') == adresse_cle]
    if lignes_meme_adresse:
        project_code   = lignes_meme_adresse[0]['code_projet']
        adresse_sheets = lignes_meme_adresse[0]['adresse']
        print(f"       📝 Nouveau contrat {ref_contrat} pour {adresse_sheets} → Project Code {project_code} — création ligne")
        try:
            client = get_client()
            sheet = client.open_by_key(sheet_id)
            worksheet = sheet.worksheet(month_tab)
            headers = worksheet.row_values(1)
            if not any('adresse' in h.lower() for h in headers):
                headers = worksheet.row_values(2)

            new_row = [''] * len(headers)
            for i, h in enumerate(headers):
                h_low = h.lower()
                if 'adresse' in h_low:
                    new_row[i] = adresse_sheets
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
                "adresse":        adresse_sheets,
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
