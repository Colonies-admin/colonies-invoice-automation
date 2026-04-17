import os
import sys
import argparse
import glob
import shutil

print("Script démarré", flush=True)

from modules.sheets_reader import get_mapping, mark_as_done
from modules.airtable_writer import find_record_by_fragment, update_record, attach_pdf
from modules.pdf_extractor import extract_invoice_data

SHEET_ID       = os.environ.get("GOOGLE_SHEET_ID")
AIRTABLE_BASE  = os.environ.get("AIRTABLE_BASE_ID")
AIRTABLE_TABLE = os.environ.get("AIRTABLE_TABLE_ID")

NATURE = "OPS"


def process_folder(dossier: str, mois: str):
    print(f"\n{'='*60}")
    print(f"  Lancement : {dossier} | Mois : {mois}")
    print(f"{'='*60}\n")

    # Créer le dossier pdfs_done s'il n'existe pas
    done_folder = dossier.replace("pdfs_input", "pdfs_done")
    os.makedirs(done_folder, exist_ok=True)

    print("📋 Chargement du mapping Google Sheets...")
    mapping = get_mapping(SHEET_ID, mois)
    print(f"   → {len(mapping)} comptes chargés\n")

    pdfs = sorted(glob.glob(os.path.join(dossier, "*.pdf")))
    if not pdfs:
        print(f"❌ Aucun PDF trouvé dans le dossier : {dossier}")
        sys.exit(1)
    print(f"📂 {len(pdfs)} PDFs trouvés\n")

    ok, ko = 0, 0

    for pdf_path in pdfs:
        filename = os.path.basename(pdf_path)
        print(f"─── {filename}")

        try:
            data = extract_invoice_data(pdf_path)
            fournisseur = data.get('fournisseur', 'INCONNU')
            print(f"    ✅ Extraction OK ({fournisseur})")
            print(f"       Facture     : {data.get('numero_facture')}")
            print(f"       Fragment AT : {data.get('fragment_at')}")
            print(f"       Compte      : {data.get('numero_compte')}")
            print(f"       Montant TTC : {data.get('montant_ttc')} €")
            print(f"       Prélèvement : {data.get('date_prelevement')}")
            print(f"       TAG OPS     : {data.get('tag_ops')}")

            fragment      = data.get("fragment_at")
            numero_compte = data.get("numero_compte")
            tag_ops       = data.get("tag_ops", "ELE-ELECTRICITY")

            if not fragment:
                print(f"    ⚠️  Fragment AT introuvable - skipped")
                ko += 1
                continue

            compte_info = mapping.get(numero_compte)
            if not compte_info:
                print(f"    ⚠️  Compte {numero_compte} absent du mapping Sheets - skipped")
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
                project_code, tag_ops, NATURE
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

            mark_as_done(SHEET_ID, mois, compte_info["row_idx"], compte_info["status_col"])

            # Déplacer le PDF dans pdfs_done
            done_path = os.path.join(done_folder, filename)
            shutil.move(pdf_path, done_path)
            print(f"    📁 PDF déplacé vers pdfs_done/")

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
    parser.add_argument("--mois", required=True, help="Onglet du Google Sheets à utiliser")
    args = parser.parse_args()

    process_folder(args.dossier, args.mois)
