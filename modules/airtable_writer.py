import os
import requests
import base64

AIRTABLE_API_URL = "https://api.airtable.com/v0"

def get_headers():
    token = os.environ.get("AIRTABLE_TOKEN")
    return {
        "Authorization": f"Bearer " + token,
        "Content-Type": "application/json"
    }

def find_record_by_fragment(base_id, table_id, fragment):
    url = AIRTABLE_API_URL + "/" + base_id + "/" + table_id
    headers = get_headers()
    params = {
        "filterByFormula": 'SEARCH("' + fragment + '", {Bank reference})',
        "maxRecords": 5
    }
    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        print("Erreur recherche: " + str(response.status_code) + " " + response.text)
        return None
    records = response.json().get("records", [])
    if not records:
        return None
    return records[0]["id"]

def update_record(base_id, table_id, record_id, project_code, tag_ops, nature):
    url = AIRTABLE_API_URL + "/" + base_id + "/" + table_id + "/" + record_id
    headers = get_headers()
    data = {
        "fields": {
            "Project code": project_code,
            "TAG OPS": tag_ops,
            "Nature": nature
        }
    }
    response = requests.patch(url, headers=headers, json=data)
    if response.status_code != 200:
        print("Erreur update: " + str(response.status_code) + " " + response.text)
    return response.status_code == 200

def attach_pdf(base_id, table_id, record_id, pdf_path, filename):
    with open(pdf_path, "rb") as f:
        pdf_content = base64.b64encode(f.read()).decode("utf-8")
    url = AIRTABLE_API_URL + "/" + base_id + "/" + table_id + "/" + record_id
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
    if response.status_code != 200:
        print("Erreur attach: " + str(response.status_code) + " " + response.text)
    return response.status_code == 200
