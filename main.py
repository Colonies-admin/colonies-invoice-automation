import os
import sys
import argparse
import glob
import shutil

print("Script démarré", flush=True)

from modules.sheets_reader import get_mapping, mark_as_done, normalise_adresse
from modules.airtable_writer import find_record_by_fragment, update_record, attach_pdf
from modules.pdf_extractor import extract_invoice_data

SHEET_ID       = os.environ.get("GOOGLE_SHEET_ID")
AIRTABLE_BASE  = os.environ.get("AIRTABLE_BASE_ID")
AIRTABLE_TABLE = os.environ.get("AIRTABLE_TABLE_ID")

MOIS_MAP = {
    '01': 'JANVIER', '02': 'FEVRIER', '03': 'MARS', '04': 'AVRIL',
    '05': 'MAI', '06': 'JUIN', '07': 'JUILLET', '08': 'AOUT',
    '09': 'SEPTEMBRE', '10': 'OCTOBRE', '11': 'NOVEMBRE', '12': 'DECEMBRE'
}


def get_onglet(fournisseur: str, date_prelevement: str) -> str:
    try:
        mois_num = date_prelevement.split('.')[1]
        mois_str = MOIS_MAP.get(mois_num, 'INCONNU')
        return f"{fournisseur}_{mois_str}"
    except Exception:
        return None


def get_done_folder(fournisseur: str, mois: str) -> str:
    mois_only = mois.split('_')[1].lower() if '_' in mois else mois.lower()
    return os.path.join("pdfs_done", fournisseur.lower(), mois_only)


def get_mapping_key(fournisseur: str, data: dict) -> str:
    if fournisseur == "ENDESA":
        return normalise_adresse(data.get('adresse', ''))
    return data.get('numero_compte', '')


def process_folder(dossier: str):
    print(f"\n{'='*60}")
    print(f"  Lancement : {dossier}")
    print(f"{'='*60}\n")

    pdfs = sorted(glob.glob(os.path.join(dossier, "*.pdf")))
    if not pdfs:
        print(f"❌ Aucun PDF trouvé dans le dossier : {dossier}")
        sys.exit(1)
    print(f"📂 {len(pdfs)} PDFs trouvés\n")

    mappings_cache = {}
    ok, ko = 0, 0

    for pdf_path in pdfs:
        filename = os.path.basename(pdf_path)
        print(f"─── {filename}")

        try:
            data = extract_invoice_data(pdf_path)
            fournisseur = data.get('fournisseur', 'INCONNU')
            nature      = data.get('nature', 'OPS')
            is_hq       = data.get('is_hq', False)

            print(f"    ✅ Extraction OK ({fournisseur})")
            print(f"       Facture     : {data.get('numero_facture')}")
            print(f"       Fragment AT : {data.get('fragment_at')}")
            print(f"       Adresse     : {data.get('adresse')}")
            print(f"       Montant TTC : {data.get('montant_ttc')} €")
            print(f"       Prélèvement : {data.get('date_prelevement')}")
            print(f"       TAG OPS     : {data.get('tag_ops')}")
            print(f"       Nature      : {nature}")

            mois = get_onglet(fournisseur, data.get('date_prelevement', ''))
            if not mois:
                print(f"    ⚠️  Impossible de détecter le mois - skipped")
                ko += 1
                continue
            print(f"       Onglet      : {mois}")

            fragment    = data.get("fragment_at")
            tag_ops     = data.get("tag_ops", "ELE-ELECTRICITY")
            mapping_key = get_mapping_key(fournisseur, data)

            if not fragment:
                print(f"    ⚠️  Fragment AT introuvable - skipped")
                ko += 1
                continue

            if mois not in mappings_cache:
                print(f"    📋 Chargement mapping {mois}...")
                try:
                    mappings_cache[mois] = get_mapping(SHEET_ID, mois)
                except Exception as e:
                    print(f"    ⚠️  Onglet {mois} introuvable dans Sheets - skipped")
                    ko += 1
                    continue

            mapping = mappings_cache[mois]

            if is_hq:
                project_code = None
                compte_info  = None
            else:
                compte_info = mapping.get(mapping_key)
                if not compte_info:
                    print(f"    ⚠️  Clé '{mapping_key}' absente du mapping - skipped")
                    ko += 1
                    continue
                project_code = compte_info.get("code_projet")
                print(f"       Project code : {project_code}")

            record_id = find_record_by_fragment(AIRTABLE_BASE, AIRTABLE_TABLE, fragment)
            if not record_id:
                print(f"    ⚠️  Fragment '{fragment}' non trouvé dans Airtable - skipped")
                ko += 1
                continue

            updated = update_record(
                AIRTABLE_BASE, AIRTABLE_TABLE, record_id,
                project_code, tag_ops, nature
            )
            if not updated:
                print(f"    ❌ Erreur mise à jour Airtable")
                ko += 1
                continue

            attached = attach_pdf(
                AIRTABLE_BASE, AIRTABLE_TABLE, record_id,
                pdf_path, filename
            )
            if attached:
                print(f"    ✅ Airtable mis à jour + PDF attaché")
            else:
                print(f"    ⚠️  Mis à jour mais PDF non attaché")

            if compte_info:
                mark_as_done(SHEET_ID, mois, compte_info["row_idx"], compte_info["status_col"])

            done_folder = get_done_folder(fournisseur, mois)
            os.makedirs(done_folder, exist_ok=True)
            done_path = os.path.join(done_folder, filename)
            shutil.move(pdf_path, done_path)
            print(f"    📁 PDF déplacé vers {done_folder}/")

            ok += 1

        except Exception as e:
            print(f"    ❌ Erreur : {e}")
            ko += 1

        print()

    print(f"{'='*60}")
    print(f"  RÉSUMÉ : {ok} OK  |  {ko} erreurs  |  {len(pdfs)} total")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Automation factures fournisseurs → Airtable")
    parser.add_argument("--dossier", required=True, help="Chemin du dossier contenant les PDFs")
    args = parser.parse_args()

    process_folder(args.dossier)
