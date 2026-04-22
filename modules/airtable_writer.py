import os
import requests
import base64

AIRTABLE_API_URL = "https://api.airtable.com/v0"
GITHUB_TOKEN = os.environ.get("GH_PAT")
REPO_OWNER = "Colonies-admin"
REPO_NAME = "colonies-invoice-automation"

def get_headers():
    token = os.environ.get("AIRTABLE_TOKEN")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

def get_pdf_raw_url(pdf_path):
    filename = os.path.basename(pdf_path)
    return f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/main/pdfs_input/{filename}"

def find_project_record_id(base_id, project_code):
    url = f"{AIRTABLE_API_URL}/{base_id}/Projects"
    headers = get_headers()
    params = {
        "filterByFormula": f'{{Project Code}} = "{project_code}"',
        "maxRecords": 1
    }
    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        print(f"Erreur recherche projet: {response.status_code} {response.text}")
        return None
    records = response.json().get("records", [])
    if not records:
        print(f"Projet {project_code} non trouvé dans Projects")
        return None
    return records[0]["id"]

def find_record_by_fragment(base_id, table_id, fragment):
    """Matching générique par fragment dans Bank reference (Orange, Engie, Endesa)."""
    url = f"{AIRTABLE_API_URL}/{base_id}/{table_id}"
    headers = get_headers()
    params = {
        "filterByFormula": f'SEARCH("{fragment}", {{Bank reference}})',
        "maxRecords": 5
    }
    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        print(f"Erreur recherche: {response.status_code} {response.text}")
        return None
    records = response.json().get("records", [])
    if not records:
        return None
    return records[0]["id"]

def find_record_by_client_and_amount(base_id, table_id, numero_client, montant_ttc):
    """
    Matching TotalEnergies.
    Bank reference format : "Prelevement TotalEnergies Electricite et Gaz France-Reference client XXXXXXX"
    Si plusieurs lignes pour le même N° client, affine par montant TTC.
    """
    url = f"{AIRTABLE_API_URL}/{base_id}/{table_id}"
    headers = get_headers()

    params = {
        "filterByFormula": f'SEARCH("{numero_client}", {{Bank reference}})',
        "maxRecords": 10
    }
    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        print(f"Erreur recherche client: {response.status_code} {response.text}")
        return None

    records = response.json().get("records", [])

    # DEBUG temporaire — à retirer après
    for r in records:
        print(f"       DEBUG fields: {r.get('fields', {})}")

    if not records:
        print(f"       ⚠️  Aucune ligne trouvée pour N° client {numero_client}")
        return None

    if len(records) == 1:
        return records[0]["id"]

    try:
        montant_float = float(str(montant_ttc).replace(',', '.'))
    except (ValueError, TypeError):
        print(f"       ⚠️  Montant invalide '{montant_ttc}' — retour première ligne")
        return records[0]["id"]

    for record in records:
        fields = record.get("fields", {})
        for field_name in ["Montant TTC", "Amount", "Montant", "Amount (€)", "Debit"]:
            val = fields.get(field_name)
            if val is not None:
                try:
                    if abs(float(val) - montant_float) < 0.02:
                        print(f"       ✅ Match par montant {montant_float}€ → record {record['id']}")
                        return record["id"]
                except (ValueError, TypeError):
                    continue

    print(f"       ⚠️  Pas de match exact par montant {montant_float}€ — retour première ligne")
    return records[0]["id"]

def update_record(base_id, table_id, record_id, project_code, tag_ops, nature):
    project_record_id = find_project_record_id(base_id, project_code)
    url = f"{AIRTABLE_API_URL}/{base_id}/{table_id}/{record_id}"
    headers = get_headers()
    fields = {
        "TAG OPS": tag_ops,
        "Nature": nature
    }
    if project_record_id:
        fields["Project Code"] = [project_record_id]
    else:
        print(f"⚠️  Project record ID non trouvé pour {project_code}")
    response = requests.patch(url, headers=headers, json={"fields": fields})
    if response.status_code != 200:
        print(f"Erreur update: {response.status_code} {response.text}")
    return response.status_code == 200

def attach_pdf(base_id, table_id, record_id, pdf_path, filename):
    raw_url = get_pdf_raw_url(pdf_path)
    url = f"{AIRTABLE_API_URL}/{base_id}/{table_id}/{record_id}"
    headers = get_headers()
    data = {
        "fields": {
            "Document": [{"url": raw_url, "filename": filename}]
        }
    }
    response = requests.patch(url, headers=headers, json=data)
    if response.status_code != 200:
        print(f"Erreur attach: {response.status_code} {response.text}")
    return response.status_code == 200
