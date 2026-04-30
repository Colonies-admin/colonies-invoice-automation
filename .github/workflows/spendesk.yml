import os
import sys
import requests

AIRTABLE_API_URL = "https://api.airtable.com/v0"
BASE_ID = "appgCCvaGhmGjOaH6"
TABLE_ID = "tblZZiXKB9LQEcq7h"
GITHUB_TOKEN = os.environ.get("GH_PAT")
REPO_OWNER = "Colonies-admin"
REPO_NAME = "colonies-invoice-automation"


def get_headers():
    token = os.environ.get("AIRTABLE_TOKEN")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }


def get_raw_url(filename):
    return f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/main/pdfs_input/{filename}"


def group_files_by_id(folder):
    """
    Regroupe les fichiers Spendesk par leur ID unique (avant le dernier tiret).
    Ex: 4004b8d4-0.pdf et 4004b8d4-1.pdf → même groupe
    Retourne un dict { invoice_no: [fichier1, fichier2, ...] }
    """
    groups = {}
    for f in sorted(os.listdir(folder)):
        # Ignore les fichiers non Spendesk (pas de pattern date en début)
        if not f[:4].isdigit():
            continue
        # Supprime l'extension
        name = os.path.splitext(f)[0]
        # Retire le suffixe -0, -1, -2...
        parts = name.rsplit('-', 1)
        if len(parts) == 2 and parts[1].isdigit():
            invoice_no = name  # on garde le nom complet comme invoice_no
            base_id_key = parts[0]  # clé de regroupement sans le -0/-1
        else:
            invoice_no = name
            base_id_key = name

        if base_id_key not in groups:
            groups[base_id_key] = []
        groups[base_id_key].append(f)

    return groups


def find_record_by_invoice(invoice_no):
    """Cherche la ligne AT dont le champ 'Invoice n°' contient invoice_no."""
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
    """Attache une liste de fichiers à un record AT."""
    attachments = []
    for f in files:
        raw_url = get_raw_url(f)
        attachments.append({"url": raw_url, "filename": f})

    url = f"{AIRTABLE_API_URL}/{BASE_ID}/{TABLE_ID}/{record_id}"
    headers = get_headers()
    data = {"fields": {"Document": attachments}}
    response = requests.patch(url, headers=headers, json=data)
    if response.status_code != 200:
        print(f"    ❌ Erreur attach: {response.status_code} {response.text}")
        return False
    return True


def move_to_done(files, folder, done_folder):
    """Déplace les fichiers traités vers pdfs_done/spendesk/."""
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
        # L'invoice_no à chercher = nom du premier fichier sans extension
        invoice_no = os.path.splitext(files[0])[0]
        # Retire le suffixe -0
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
