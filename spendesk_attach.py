import os
import sys
import base64
import requests

AIRTABLE_API_URL = "https://api.airtable.com/v0"
BASE_ID = "appgCCvaGhmGjOaH6"
TABLE_ID = "tblZZiXKB9LQEcq7h"
REPO_OWNER = "Colonies-admin"
REPO_NAME = "colonies-invoice-automation"


def get_headers():
    token = os.environ.get("AIRTABLE_TOKEN")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }


def group_files_by_id(folder):
    groups = {}
    for f in sorted(os.listdir(folder)):
        if not f[:4].isdigit():
            continue
        name = os.path.splitext(f)[0]
        parts = name.rsplit('-', 1)
        if len(parts) == 2 and parts[1].isdigit():
            base_id_key = parts[0]
        else:
            base_id_key = name

        if base_id_key not in groups:
            groups[base_id_key] = []
        groups[base_id_key].append(f)

    return groups


def find_record_by_invoice(invoice_no):
    url = f"{AIRTABLE_API_URL}/{BASE_ID}/{TABLE_ID}"
    headers = get_headers()
    params = {
        "filterByFormula": f'SEARCH("{invoice_no}", {{Invoice n°}})',
        "maxRecords": 5
    }
    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        print(f"    ❌ Erreur AT: {response.status_code} {response.text}")
        return None
    records = response.json().get("records", [])
    if not records:
        return None
    return records[0]["id"]


def attach_files(record_id, files, folder):
    for f in files:
        filepath = os.path.join(folder, f)
        with open(filepath, "rb") as file:
            content = base64.standard_b64encode(file.read()).decode("utf-8")

        ext = os.path.splitext(f)[1].lower()
        if ext == ".pdf":
            content_type = "application/pdf"
        elif ext in (".jpg", ".jpeg"):
            content_type = "image/jpeg"
        elif ext == ".png":
            content_type = "image/png"
        else:
            content_type = "application/octet-stream"

        url = f"{AIRTABLE_API_URL}/{BASE_ID}/{TABLE_ID}/{record_id}/uploadAttachment"
        headers = {
            "Authorization": f"Bearer {os.environ.get('AIRTABLE_TOKEN')}",
            "Content-Type": "application/json"
        }
        data = {
            "contentType": content_type,
            "filename": f,
            "file": content
        }
        response = requests.post(url, headers=headers, json=data)
        if response.status_code not in (200, 202):
            print(f"    ❌ Erreur upload {f}: {response.status_code} {response.text}")
            return False

    return True


def move_to_done(files, folder, done_folder):
    os.makedirs(done_folder, exist_ok=True)
    for f in files:
        src = os.path.join(folder, f)
        dst = os.path.join(done_folder, f)
        os.rename(src, dst)


def main():
    folder = sys.argv[1] if len(sys.argv) > 1 else "pdfs_input"
    done_folder = "pdfs_done/spendesk"

    print("\n" + "=" * 60)
    print(f"  Spendesk Attach — dossier : {folder}")
    print("=" * 60)

    groups = group_files_by_id(folder)

    if not groups:
        print("  Aucun fichier Spendesk trouvé.")
        return

    ok = 0
    errors = 0

    for base_key, files in groups.items():
        invoice_no = os.path.splitext(files[0])[0]
        parts = invoice_no.rsplit('-', 1)
        if len(parts) == 2 and parts[1].isdigit():
            invoice_no = parts[0]

        print(f"\n─── {invoice_no}")
        print(f"    Fichiers : {', '.join(files)}")

        record_id = find_record_by_invoice(invoice_no)
        if not record_id:
            print(f"    ⚠️  Invoice n° '{invoice_no}' non trouvé dans AT — skipped")
            errors += 1
            continue

        success = attach_files(record_id, files, folder)
        if success:
            print(f"    ✅ PDF(s) attaché(s) → record {record_id}")
            move_to_done(files, folder, done_folder)
            ok += 1
        else:
            errors += 1

    print("\n" + "=" * 60)
    print(f"  RÉSUMÉ : {ok} OK  |  {errors} erreurs  |  {ok + errors} total")
    print("=" * 60)


if __name__ == "__main__":
    main()
