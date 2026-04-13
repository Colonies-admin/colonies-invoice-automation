import os
import requests

AIRTABLE_API_URL = "https://api.airtable.com/v0"

def get_headers():
    token = os.environ.get("AIRTABLE_TOKEN")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

def find_record_by_fragment(base_id: str, table_id: str, fragment: str) -> str | None:
    """
    Cherche un enregistrement dans Airtable dont le champ
    contient le fragment du numéro de facture.
    Retourne l'ID de l'enregistrement ou None.
    """
    url = f"{AIRTABLE_API_URL}/{base_id}/{table_id}"
    headers = get_headers()
    
    params = {
        "filterByFormula": f'SEARCH("{fragment}", {{Description}})',
        "maxRecords": 5
    }
    
    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code != 200:
        print(f"Erreur recherche Airtable: {response.status_code} - {response.text}")
        return None
    
    records = response.json().get("records", [])
    if not records:
        return None
    
    return records[0]["id"]


def update_record(base_id: str, table_id: str, record_id: str, 
                  project_code: str, tag_ops: str, nature: str) -> bool:
    """
    Met à jour les champs Project code, TAG OPS, Nature
    sur un enregistrement Airtable existant.
    """
    url = f"{AIRTABLE_API_URL}/{base_id}/{table_id}/{record_id}"
    headers = get_headers()
    
    data = {
        "fields": {
            "Project code": project_code,
            "TAG OPS": tag_ops,
            "Nature": nature
        }
    }
    
    response = requests.patch(url, headers=headers, json=data)
    return response.status_code == 200


def attach_pdf(base_id: str, table_id: str, record_id: str, 
               pdf_path: str, filename: str) -> bool:
    """
    Attache un PDF à un enregistrement Airtable via upload.
    """
    import base64
    
    with open(pdf_path, "rb") as f:
        pdf_content = base64.b64encode(f.read()).decode("utf-8")
    
    url = f"{AIRTABLE_API_URL}/{base_id}/{table_id}/{record_id}"
    headers = get_headers()
    
    data = {
        "fields": {
            "Document": [
                {
                    "filename": filename,
                    "contentType": "application/pdf",
                    "data": pdf_content
                }
            ]
        }
    }
    
    response = requests.patch(url, headers=headers, json=data)
    return response.status_code == 200
