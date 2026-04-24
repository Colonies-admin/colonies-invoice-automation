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


def mark_status(compte_info, project_code_at, sheet_id, mois, adresse_conso=""):
    """
    Coche le STATUS dans le Sheets.
    Utilise l'adresse de consommation pour identifier la bonne ligne
    quand plusieurs lignes ont le même N° client et type.
    """
    if not compte_info:
        return

    if not isinstance(compte_info, list):
        mark_as_done(sheet_id, mois, compte_info["row_idx"], compte_info["status_col"])
        return

    entry_to_mark = None

    # 1. Essaie par adresse conso (plus fiable)
    if adresse_conso:
        adresse_key = adresse_conso.upper().replace(" ", "")
        for e in compte_info:
            if not e.get('_used'):
                e_adresse = e.get('adresse_cle', '') or e.get('adresse', '').upper().replace(" ", "")
                if e_adresse and adresse_key.startswith(e_adresse[:10]):
                    e['_used'] = True
                    entry_to_mark = e
                    break

    # 2. Essaie par project code Airtable
    if not entry_to_mark and project_code_at:
        for e in compte_info:
            if not e.get('_used') and e.get('code_projet', '').upper() == project_code_at.upper():
                e['_used'] = True
                entry_to_mark = e
                break

    # 3. Fallback : première non utilisée
    if not entry_to_mark:
        for e in compte_info:
            if not e.get('_used'):
                e['_used'] = True
                entry_to_mark = e
                break

    if entry_to_mark:
        mark_as_done(sheet_id, mois, entry_to_mark["row_idx"], entry_to_mark["status_col"])


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
            fournisseur   = data.get('fournisseur', 'INCONNU')
            nature        = data.get('nature', 'OPS')
            is_hq         = data.get('is_hq', False)
            is_echeancier = data.get('is_echeancier', False)

            print(f"    ✅ Extraction OK ({fournisseur})")
            print(f"       Facture      : {data.get('numero_facture')}")
            print(f"       Fragment AT  : {data.get('fragment_at')}")
            print(f"       Adresse conso: {data.get('adresse_consommation', data.get('adresse'))}")
            print(f"       Montant TTC  : {data.get('montant_ttc')} €")
            print(f"       Prélèvement  : {data.get('date_prelevement')}")
            print(f"       TAG OPS      : {data.get('tag_ops')}")
            print(f"       Nature       : {nature}")
            if fournisseur == "TOTALENERGIES" or (fournisseur == "ENGIE" and is_echeancier):
                print(f"       Échéancier   : {is_echeancier}")

            # --- Onglet Sheets ---
            if is_echeancier and fournisseur == "TOTALENERGIES":
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

            tag_ops = data.get("tag_ops", "ELE-ELECTRICITY")

            # --- Charger le mapping Sheets ---
            if mois not in mappings_cache:
                print(f"    📋 Chargement mapping {mois}...")
                try:
                    mappings_cache[mois] = get_mapping(SHEET_ID, mois)
                except Exception as e:
                    print(f"    ⚠️  Onglet {mois} introuvable dans Sheets - skipped")
                    ko += 1
                    continue

            mapping = mappings_cache[mois]

            # --- Échéancier ---
            if is_echeancier:
                print(f"    📋 Échéancier GAZ détecté — montant mensuel {data.get('montant_ttc')}€")
                print(f"       Pas de transaction Airtable à matcher pour un échéancier.")
                if fournisseur == "TOTALENERGIES":
                    numero_client = data.get('numero_client', '')
                    compte_info_list = find_totalenergies_entry(mapping, numero_client, tag_ops)
                else:
                    # Engie : matching par ref client (numero_compte)
                    numero_compte = data.get('numero_compte', '')
                    compte_info_list = mapping.get(numero_compte)
                if compte_info_list:
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
            compte_info  = None
            project_code = None

            if fournisseur == "TOTALENERGIES":
                numero_client = data.get('numero_client', '')
                adresse_conso_pdf = data.get('adresse_consommation', '').upper().replace(' ', '')
                compte_info = find_totalenergies_entry(mapping, numero_client, tag_ops)
                if not compte_info and not is_hq:
                    ko += 1
                    continue
                if compte_info:
                    if isinstance(compte_info, list):
                        # Cherche la bonne entrée par adresse conso
                        best_entry = None
                        if adresse_conso_pdf:
                            for e in compte_info:
                                e_adresse = e.get('adresse_cle', '') or e.get('adresse', '').upper().replace(' ', '')
                                if e_adresse and adresse_conso_pdf.startswith(e_adresse[:10]):
                                    best_entry = e
                                    break
                        entry = best_entry if best_entry else compte_info[0]
                    else:
                        entry = compte_info
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
                if not compte_info and not is_hq:
                    print(f"    ⚠️  Compte {numero_compte} absent du mapping - skipped")
                    ko += 1
                    continue
                if compte_info:
                    project_code = compte_info.get("code_projet")
                    print(f"       Project code : {project_code}")

            # --- Matching Airtable ---
            project_code_at = None  # Project code retourné par Airtable

            if fournisseur == "TOTALENERGIES":
                numero_client = data.get('numero_client', '')
                montant_ttc   = data.get('montant_ttc', '')
                date_prel     = data.get('date_prelevement', '')
                record_id, project_code_at = find_record_by_client_and_amount(
                    AIRTABLE_BASE, AIRTABLE_TABLE, numero_client, montant_ttc, date_prel
                )
                # Utilise le project code Airtable si disponible
                if project_code_at and not project_code:
                    project_code = project_code_at
                    print(f"       Project code (AT) : {project_code}")
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
            # Pour HQ sans compte_info, cherche quand même dans le mapping
            if is_hq and not compte_info and fournisseur == "TOTALENERGIES":
                numero_client = data.get('numero_client', '')
                compte_info = find_totalenergies_entry(mapping, numero_client, tag_ops)
            elif is_hq and not compte_info:
                numero_compte = data.get("numero_compte", "")
                compte_info = mapping.get(numero_compte)

            mark_status(compte_info, project_code_at, SHEET_ID, mois,
                       adresse_conso=data.get('adresse_consommation', data.get('adresse', '')))

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
