"""
Orchestrateur principal - Automation Factures Orange
-----------------------------------------------------
Usage :
    python main.py --dossier ORANGE_AVRIL_2026 --mois AVRIL

Le dossier doit contenir les PDFs téléchargés manuellement depuis le portail Orange.
"""

import os
import sys
import argparse
import glob

from modules.sheets_reader import get_mapping
from modules.pdf_extractor import extract_invoice_data
from modules.airtable_writer import find_record_by_fragment, update_record, attach_pdf

# ─── Configuration (via variables d'environnement / GitHub Secrets) ───────────
SHEET_ID      = os.environ.get("GOOGLE_SHEET_ID")
AIRTABLE_BASE = os.environ.get("AIRTABLE_BASE_ID")
AIRTABLE_TABLE= os.environ.get("AIRTABLE_TABLE_ID")

TAG_OPS = "INT"
NATURE  = "OPS"


def process_folder(dossier: str, mois: str):
    print(f"\n{'='*60}")
    print(f"  Lancement : {dossier} | Mois : {mois}")
    print(f"{'='*60}\n")

    # 1. Chargement du mapping Google Sheets
    print("📋 Chargement du mapping Google Sheets...")
    mapping = get_mapping(SHEET_ID, mois)
    print(f"   → {len(mapping)} comptes chargés\n")

    # 2. Liste des PDFs dans le dossier
    pdfs = sorted(glob.glob(os.path.join(dossier, "*.pdf")))
    if not pdfs:
        print(f"❌ Aucun PDF trouvé dans le dossier : {dossier}")
        sys.exit(1)
    print(f"📂 {len(pdfs)} PDFs trouvés\n")

    # 3. Traitement de chaque PDF
    ok, ko = 0, 0

    for pdf_path in pdfs:
        filename = os.path.basename(pdf_path)
        print(f"─── {filename}")

        try:
            # Extraction via Claude API
            data = extract_invoice_data(pdf_path)
            print(f"    ✅ Extraction OK")
            print(f"       Facture     : {data.get('numero_facture')}")
            print(f"       Fragment AT : {data.get('fragment_at')}")
            print(f"       Compte      : {data.get('numero_compte')}")
            print(f"       Montant TTC : {data.get('montant_ttc')} €")
            print(f"       Prélèvement : {data.get('date_prelevement')}")

            fragment      = data.get("fragment_at")
            numero_compte = data.get("numero_compte")

            if not fragment:
                print(f"    ⚠️  Fragment AT introuvable - skipped")
                ko += 1
                continue

            # Récupération du project code via mapping
            compte_info = mapping.get(numero_compte)
            if not compte_info:
                print(f"    ⚠️  Compte {numero_compte} absent du mapping Sheets - skipped")
                ko += 1
                continue

            project_code = compte_info.get("code_projet")
            print(f"       Project code : {project_code}")

            # Recherche de l'enregistrement Airtable
            record_id = find_record_by_fragment(AIRTABLE_BASE, AIRTABLE_TABLE, fragment)
            if not record_id:
                print(f"    ⚠️  Fragment '{fragment}' non trouvé dans Airtable - skipped")
                ko += 1
                continue

            # Mise à jour des champs
            updated = update_record(
                AIRTABLE_BASE, AIRTABLE_TABLE, record_id,
                project_code, TAG_OPS, NATURE
            )
            if not updated:
                print(f"    ❌ Erreur mise à jour Airtable")
                ko += 1
                continue

            # Attach du PDF
            attached = attach_pdf(
                AIRTABLE_BASE, AIRTABLE_TABLE, record_id,
                pdf_path, filename
            )
            if attached:
                print(f"    ✅ Airtable mis à jour + PDF attaché")
                ok += 1
            else:
                print(f"    ⚠️  Mis à jour mais erreur attach PDF")
                ko += 1

        except Exception as e:
            print(f"    ❌ Erreur : {e}")
            ko += 1

        print()

    # 4. Résumé final
    print(f"{'='*60}")
    print(f"  RÉSUMÉ : {ok} OK  |  {ko} erreurs  |  {len(pdfs)} total")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Automation factures Orange → Airtable")
    parser.add_argument("--dossier", required=True, help="Chemin du dossier contenant les PDFs")
    parser.add_argument("--mois",    required=True, help="Onglet du Google Sheets à utiliser (ex: AVRIL)")
    args = parser.parse_args()

    process_folder(args.dossier, args.mois)
