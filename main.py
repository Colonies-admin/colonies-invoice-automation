import os
import sys
import argparse
import glob
import shutil
import datetime

print("Script démarré", flush=True)

from modules.sheets_reader import get_mapping, mark_as_done, find_or_create_endesa_line, find_totalenergies_entry
from modules.airtable_writer import find_record_by_fragment, find_record_by_client_and_amount, update_record, attach_pdf
from modules.pdf_extractor import extract_invoice_data

SHEET_ID       = os.environ.get("GOOGLE_SHEET_ID")
AIRTABLE_BASE  = os.environ.get("AIRTABLE_BASE_ID")
AIRTABLE_TABLE = os.environ.get("AIRTABLE_TABLE_ID")

MOIS_MAP = {
    '01': 'JANVIER', '02': 'FEVRIER', '03': 'MARS', '04': 'AVRIL',
    '05': 'MAI', '06': 'JUIN', '07': 'JUILLET', '08': 'AOUT',
    '09': 'SEPTEMBRE', '10': 'OCTOBRE', '11': 'NOVEMBRE', '12': 'DECEMBRE'
}


FOURNISSEUR_ONGLET = {
    "TOTALENERGIES": "TOTAL",
}

def get_onglet(fournisseur: str, date_prelevement: str) -> str:
    try:
        mois_num = date_prelevement.split('.')[1]
        mois_str = MOIS_MAP.get(mois_num, 'INCONNU')
        prefix = FOURNISSEUR_ONGLET.get(fournisseur, fournisseur)
        return f"{prefix}_{mois_str}"
    except Exception:
        return None


def get_done_folder(fournisseur: str, mois: str) -> str:
    mois_only = mois.split('_')[1].lower() if '_' in mois else mois.lower()
    return os.path.join("pdfs_done", fournisseur.lower(), mois_only)


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
            fournisseur  = data.get('fournisseur', 'INCONNU')
            nature       = data.get('nature', 'OPS')
            is_hq        = data.get('is_hq', False)
            is_echeancier = data.get('is_echeancier', False)

            print(f"    ✅ Extraction OK ({fournisseur})")
            print(f"       Facture      : {data.get('numero_facture')}")
            print(f"       Fragment AT  : {data.get('fragment_at')}")
            print(f"       Adresse conso: {data.get('adresse_consommation', data.get('adresse'))}")
            print(f"       Montant TTC  : {data.get('montant_ttc')} €")
            print(f"       Prélèvement  : {data.get('date_prelevement')}")
            print(f"       TAG OPS      : {data.get('tag_ops')}")
            print(f"       Nature       : {nature}")
            if fournisseur == "TOTALENERGIES":
                print(f"       N° client    : {data.get('numero_client')}")
                print(f"       Échéancier   : {is_echeancier}")

            # --- Onglet Sheets ---
            if is_echeancier:
                # Pour un échéancier, on utilise le mois courant (pas la date du tableau)
                mois_num = str(datetime.date.today().month).zfill(2)
                mois_str = MOIS_MAP.get(mois_num, 'INCONNU')
                mois = f"TOTAL_{mois_str}"
            else:
                mois = get_onglet(fournisseur, data.get('date_prelevement', ''))
            if not mois:
                print(f"    ⚠️  Impossible de détecter le mois - skipped")
                ko += 1
                continue
            print(f"       Onglet       : {mois}")

            tag_ops  = data.get("tag_ops", "ELE-ELECTRICITY")

            # --- Échéancier TotalEnergies : pas de record Airtable, juste log + STATUS ---
            if is_echeancier:
                print(f"    📋 Échéancier GAZ détecté — montant mensuel {data.get('montant_ttc')}€")
                print(f"       Pas de transaction Airtable à matcher pour un échéancier.")

                if mois not in mappings_cache:
                    try:
                        mappings_cache[mois] = get_mapping(SHEET_ID, mois)
                    except Exception as e:
                        print(f"    ⚠️  Onglet {mois} introuvable - skipped")
                        ko += 1
                        continue

                mapping = mappings_cache[mois]
                numero_client = data.get('numero_client', '')
                compte_info_list = find_totalenergies_entry(mapping, numero_client, tag_ops)

                if compte_info_list:
                    # find_totalenergies_entry peut retourner un dict ou une liste
                    entries = compte_info_list if isinstance(compte_info_list, list) else [compte_info_list]
                    for entry in entries:
                        mark_as_done(SHEET_ID, mois, entry["row_idx"], entry["status_col"])

                done_folder = get_done_folder(fournisseur, mois)
                os.makedirs(done_folder, exist_ok=True)
                shutil.move(pdf_path, os.path.join(done_folder, filename))
                print(f"    📁 PDF déplacé vers {done_folder}/")
                ok += 1
                print()
                continue

            # --- Matching Sheets ---
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

            elif fournisseur == "TOTALENERGIES":
                numero_client = data.get('numero_client', '')
                compte_info = find_totalenergies_entry(mapping, numero_client, tag_ops)
                if not compte_info:
                    ko += 1
                    continue
                # Si liste (2 ELE même N° client), on prend la première pour le project_code
                # (les deux ont le même project_code dans ce cas)
                entry = compte_info[0] if isinstance(compte_info, list) else compte_info
                project_code = entry.get("code_projet")
                print(f"       Project code : {project_code}")

            elif fournisseur == "ENDESA":
                adresse     = data.get('adresse', '')
                ref_contrat = data.get('ref_contrat', '')
                compte_info = find_or_create_endesa_line(
                    SHEET_ID, mois, adresse, ref_contrat, mapping
                )
                if not compte_info:
                    ko += 1
                    continue
                project_code = compte_info.get("code_projet")
                print(f"       Project code : {project_code}")

            else:
                # Orange / Engie
                numero_compte = data.get("numero_compte", "")
                compte_info = mapping.get(numero_compte)
                if not compte_info:
                    print(f"    ⚠️  Compte {numero_compte} absent du mapping - skipped")
                    ko += 1
                    continue
                project_code = compte_info.get("code_projet")
                print(f"       Project code : {project_code}")

            # --- Matching Airtable ---
            if fournisseur == "TOTALENERGIES":
                numero_client = data.get('numero_client', '')
                montant_ttc   = data.get('montant_ttc', '')
                date_prel     = data.get('date_prelevement', '')
                record_id = find_record_by_client_and_amount(
                    AIRTABLE_BASE, AIRTABLE_TABLE, numero_client, montant_ttc, date_prel
                )
            else:
                fragment = data.get("fragment_at")
                if not fragment:
                    print(f"    ⚠️  Fragment AT introuvable - skipped")
                    ko += 1
                    continue
                record_id = find_record_by_fragment(AIRTABLE_BASE, AIRTABLE_TABLE, fragment)

            if not record_id:
                print(f"    ⚠️  Ligne non trouvée dans Airtable - skipped")
                ko += 1
                continue

            # --- Update + attach ---
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

            # --- STATUS Sheets ---
            if compte_info:
                entry = compte_info[0] if isinstance(compte_info, list) else compte_info
                mark_as_done(SHEET_ID, mois, entry["row_idx"], entry["status_col"])

            # --- Déplacer PDF ---
            done_folder = get_done_folder(fournisseur, mois)
            os.makedirs(done_folder, exist_ok=True)
            shutil.move(pdf_path, os.path.join(done_folder, filename))
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
