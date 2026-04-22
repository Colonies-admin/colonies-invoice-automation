import pdfplumber
import re
import datetime


def detect_fournisseur(text: str) -> str:
    if "ENDESA" in text.upper():
        return "ENDESA"
    if "TOTALENERGIES" in text.upper() or "TOTAL ENERGIES" in text.upper():
        return "TOTALENERGIES"
    if "ENGIE" in text.upper():
        return "ENGIE"
    if "ORANGE" in text.upper():
        return "ORANGE"
    return "INCONNU"


def detect_energie(text: str) -> str:
    if "FACTUREDEGAZ" in text.upper().replace(" ", "") or "FACTURE DE GAZ" in text.upper():
        return "GAS-GAS"
    if "FACTUREELECTRICITE" in text.upper().replace(" ", "") or "FACTURE ELECTRICITÉ" in text.upper():
        return "ELE-ELECTRICITY"
    return "ELE-ELECTRICITY"


def normalise_adresse(adresse: str) -> str:
    adresse = adresse.upper().strip()
    adresse = re.sub(r'\s+', ' ', adresse)
    adresse = re.sub(r'\.\.\s*', ' ', adresse)
    adresse = adresse.split(',')[0]
    adresse = re.split(r'\s*-\s*', adresse)[0]
    for mot in ['ATELIER', 'PAV', '1ET', '2ET', 'RDC', 'BATIMENT', 'BAT', 'LOGEMENT', '1ER']:
        adresse = adresse.replace(mot, '')
    adresse = re.sub(r'\s+', ' ', adresse).strip()
    return adresse


def extract_orange(text: str) -> dict:
    result = {}
    result['nature'] = "OPS"

    match = re.search(r'n° de facture\s*:\s*([A-Z0-9]{10,12}\s+\d{2}[A-Z]\d+[-\s]+\d[A-Z]\d{2})', text, re.IGNORECASE)
    if match:
        numero_brut = match.group(1).strip()
        result['numero_facture'] = numero_brut
        parties = numero_brut.split(' ')
        if len(parties) >= 2:
            trois_derniers = parties[0][-3:]
            segment = parties[1].replace('-', '').strip()[-3:]
            result['fragment_at'] = trois_derniers + segment

    match = re.search(r'n° de compte internet\s*:\s*(\d+)', text, re.IGNORECASE)
    if match:
        result['numero_compte'] = match.group(1).strip()

    match = re.search(r'au\s+(\d{2}\.\d{2}\.\d{4})', text)
    if match:
        result['date_prelevement'] = match.group(1).strip()

    match = re.search(r'(\d+[,\.]\d{2})\s*€\s*TTC', text)
    if match:
        result['montant_ttc'] = match.group(1).replace(',', '.')

    result['tag_ops'] = "INT-INTERNET"
    return result


def extract_engie(text: str) -> dict:
    result = {}
    result['tag_ops'] = detect_energie(text)

    match_lieu = re.search(r'Lieu de consommation.*?COLONIES\s+(.*?)\s+\d{5}', text, re.IGNORECASE | re.DOTALL)
    if match_lieu and "21 RUE DE BRUXELLES" in match_lieu.group(1).upper():
        result['nature'] = "HQ"
        result['is_hq'] = True
    else:
        result['nature'] = "OPS"
        result['is_hq'] = False

    match = re.search(r'N°\s*(\d{9,15})', text)
    if match:
        result['numero_facture'] = match.group(1).strip()

    match = re.search(r'r[eé]f[eé]rence client\s*:?\s*([\d\s]+)', text, re.IGNORECASE)
    if match:
        ref = match.group(1).replace(' ', '').strip()[:12]
        result['numero_compte'] = ref
        if result.get('numero_facture'):
            result['fragment_at'] = ref + '-' + result['numero_facture'].zfill(12)

    mois = {
        'janvier': '01', 'février': '02', 'mars': '03', 'avril': '04',
        'mai': '05', 'juin': '06', 'juillet': '07', 'août': '08',
        'septembre': '09', 'octobre': '10', 'novembre': '11', 'décembre': '12'
    }
    match = re.search(r'prélevé le\s+(\d{1,2})\s+(\w+)\s+(\d{4})', text, re.IGNORECASE)
    if match:
        jour = match.group(1).zfill(2)
        mois_str = match.group(2).lower()
        annee = match.group(3)
        mois_num = mois.get(mois_str, '00')
        result['date_prelevement'] = f"{jour}.{mois_num}.{annee}"

    match = re.search(r'total TTC\s+([\d\s]+[,\.]\d{2})', text, re.IGNORECASE)
    if match:
        result['montant_ttc'] = match.group(1).replace(' ', '').replace(',', '.')

    return result


def extract_endesa(text: str) -> dict:
    result = {}
    result['tag_ops'] = detect_energie(text)

    match = re.search(r'N°DEFACTURE\s*\n\d{2}/\d{2}/\d{4}\s+(\d+)', text, re.IGNORECASE)
    if match:
        result['numero_facture'] = match.group(1).strip().lstrip('0')
    else:
        match = re.search(r'Facture\s*n[°º]\s+(\d+)', text, re.IGNORECASE)
        if match:
            result['numero_facture'] = match.group(1).strip().lstrip('0')

    if result.get('numero_facture'):
        result['fragment_at'] = result['numero_facture']

    match = re.search(r'COMPTEDECONTRAT\s*\n(\d+)', text, re.IGNORECASE)
    if match:
        result['ref_contrat'] = match.group(1).strip()

    match = re.search(r'pr[eé]lev[eé]\s+le\s+(\d{2})/(\d{2})/(\d{4})', text, re.IGNORECASE)
    if match:
        result['date_prelevement'] = f"{match.group(1)}.{match.group(2)}.{match.group(3)}"
    else:
        match = re.search(r"Date\s*d.échéance\s+(\d{2})/(\d{2})/(\d{4})", text, re.IGNORECASE)
        if match:
            result['date_prelevement'] = f"{match.group(1)}.{match.group(2)}.{match.group(3)}"

    match = re.search(r'MONTANTTOTAL\s*\nTTCAPAYER\s*\n([\d\s,\.]+)\s*€', text, re.IGNORECASE)
    if match:
        result['montant_ttc'] = match.group(1).replace(' ', '').replace(',', '.')
    else:
        match = re.search(r'Total\s+TTC\s+([\d,\.]+)\s+Eur', text, re.IGNORECASE)
        if match:
            result['montant_ttc'] = match.group(1).replace(',', '.')

    match = re.search(r'LIEUDECONSOMMATION\s*\n[^\n]+\n([^\n]+)', text, re.IGNORECASE)
    if match:
        adresse_norm = normalise_adresse(match.group(1).strip())
        if "21RUEDEBRUXELLES" in adresse_norm.replace(" ", ""):
            result['nature'] = "HQ"
            result['is_hq'] = True
        else:
            result['nature'] = "OPS"
            result['is_hq'] = False
            result['adresse'] = adresse_norm
    else:
        match = re.search(r'Adressedefourniture:\d+\s*\n(.+?)-\s*(\d{5})(.+?)France', text, re.IGNORECASE)
        if match:
            adresse_norm = normalise_adresse(match.group(1).strip())
            if "21RUEDEBRUXELLES" in adresse_norm.replace(" ", ""):
                result['nature'] = "HQ"
                result['is_hq'] = True
            else:
                result['nature'] = "OPS"
                result['is_hq'] = False
                result['adresse'] = adresse_norm
        else:
            result['nature'] = "OPS"
            result['is_hq'] = False

    adresse = result.get('adresse', '')
    ref_contrat = result.get('ref_contrat', '')
    adresse_cle = adresse.replace(' ', '')
    if adresse_cle and ref_contrat:
        result['numero_compte'] = adresse_cle + '_' + ref_contrat
    else:
        result['numero_compte'] = adresse_cle

    return result


def extract_totalenergies(text: str) -> dict:
    result = {}
    text_upper = text.upper().replace(" ", "")

    # --- Détection échéancier GAZ ---
    is_echeancier = "CHEANCIER" in text_upper and "GAZ" in text_upper
    result['is_echeancier'] = is_echeancier

    # --- Type énergie ---
    if "FACTUREDEGAZ" in text_upper or is_echeancier:
        result['tag_ops'] = "GAS-GAS"
    elif "FACTUREDELEC" in text_upper or "ELECTRICIT" in text_upper:
        result['tag_ops'] = "ELE-ELECTRICITY"
    else:
        result['tag_ops'] = "ELE-ELECTRICITY"

    # --- Numéro client ---
    match = re.search(r'N°\s*de\s*client\s*:\s*(\d+)', text, re.IGNORECASE)
    if not match:
        match = re.search(r'R[eé]f[eé]rence\s*client\s*:\s*(\d+)', text, re.IGNORECASE)
    if match:
        result['numero_client'] = match.group(1).strip()

    # --- Numéro facture / échéancier ---
    match = re.search(r'N°\s*de\s*facture\s*:\s*(\d+)', text, re.IGNORECASE)
    if not match:
        match = re.search(r'Facture\s*n°\s*(\d+)', text, re.IGNORECASE)
    if not match and is_echeancier:
        match = re.search(r'N°\s*(\d{10,})', text, re.IGNORECASE)
    if match:
        result['numero_facture'] = match.group(1).strip()

    # --- Montant TTC ---
    if is_echeancier:
        # Mensualité du mois en cours, sinon première du tableau
        mois_fr = {1:'janv', 2:'févr', 3:'mars', 4:'avr', 5:'mai', 6:'juin',
                   7:'juil', 8:'août', 9:'sept', 10:'oct', 11:'nov', 12:'déc'}
        mois_courant = mois_fr[datetime.date.today().month]
        match = re.search(
            rf'\d{{2}}\s+{mois_courant}[^\n]*?([\d\s]+[,\.]\d{{2}})\s*€',
            text, re.IGNORECASE
        )
        if not match:
            match = re.search(
                r'\d{2}\s+\w+\.?\s+\d{4}\s+([\d\s]+[,\.]\d{2})\s*€',
                text, re.IGNORECASE
            )
        if match:
            result['montant_ttc'] = match.group(1).replace(' ', '').replace(',', '.')
        result['montant_mensuel'] = result.get('montant_ttc', '')
    else:
        match = re.search(r'Montant\s*TTC\s+([\d\s]+[,\.]\d{2})\s*€', text, re.IGNORECASE)
        if match:
            result['montant_ttc'] = match.group(1).replace(' ', '').replace(',', '.')

    # --- Date prélèvement ---
    match = re.search(r'pr[eé]l[eè]vement\s+(?:de\s+cette\s+facture\s+)?le\s+(\d{2})/(\d{2})/(\d{4})', text, re.IGNORECASE)
    if match:
        result['date_prelevement'] = f"{match.group(1)}.{match.group(2)}.{match.group(3)}"
    elif is_echeancier:
        mois = {'janv': '01', 'févr': '02', 'mars': '03', 'avr': '04', 'mai': '05',
                'juin': '06', 'juil': '07', 'août': '08', 'sept': '09', 'oct': '10',
                'nov': '11', 'déc': '12'}
        match = re.search(r'(\d{2})\s+(\w+)\.?\s+(\d{4})', text)
        if match:
            jour = match.group(1)
            mois_str = match.group(2).lower()[:4]
            annee = match.group(3)
            mois_num = mois.get(mois_str, '00')
            result['date_prelevement'] = f"{jour}.{mois_num}.{annee}"

    # --- Adresse de consommation ---
    adresse_conso = ""
    if is_echeancier:
        # "Lieu de consommation :\n22 RUE DES HETRES\n92000 NANTERRE"
        match = re.search(
            r'Lieu de consommation\s*:\s*\n([^\n]+)\n(\d{5})\s+([^\n]+)',
            text, re.IGNORECASE
        )
        if match:
            adresse_conso = f"{match.group(1).strip()} {match.group(3).strip()}"
    else:
        # Format page 3 ELE : "Adresse du site\nCOLONIES\n99B QUAI WINSTON\n94210 ST MAUR"
        match = re.search(
            r'Adresse du site\s*\nCOLONIES\s*\n([^\n]+)\n(?:[^\n]+\n)?(\d{5})\s+([^\n]+)',
            text, re.IGNORECASE
        )
        if match:
            adresse_conso = f"{match.group(1).strip()} {match.group(3).strip()}"
        else:
            # Format page 3 GAZ : "COLONIES\n37 RUE DES ROSIERS\nPAV\n94230 CACHAN"
            match = re.search(
                r'COLONIES\s*\n([^\n]+)\n(?:[A-Z]{2,}[^\n]*\n)?(\d{5})\s+([^\n]+)',
                text, re.IGNORECASE
            )
            if match:
                adresse_conso = f"{match.group(1).strip()} {match.group(3).strip()}"
            else:
                # Fallback tableau page 2 : "94210 ST MAUR,99B QUAI WINSTON CHURCHILL"
                match = re.search(r'\d{5}\s+[^,\n]+,([^\n]+)', text, re.IGNORECASE)
                if match:
                    adresse_conso = match.group(1).strip()

    result['adresse_consommation'] = adresse_conso

    # --- Nature HQ / OPS : adresse de CONSOMMATION uniquement ---
    hq_addresses = ["21 RUE DE BRUXELLES", "16 RUE CASSETTE"]
    is_hq = any(hq in adresse_conso.upper() for hq in hq_addresses)
    result['nature'] = "HQ" if is_hq else "OPS"
    result['is_hq'] = is_hq

    # --- numero_compte = numero_client pour matching Airtable ---
    if result.get('numero_client'):
        result['numero_compte'] = result['numero_client']

    # --- fragment_at ---
    if result.get('numero_facture'):
        result['fragment_at'] = result['numero_facture']

    return result


def extract_invoice_data(pdf_path: str) -> dict:
    with pdfplumber.open(pdf_path) as pdf:
        text = ""
        for i, page in enumerate(pdf.pages):
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
                if i == 0:
                    fournisseur_check = detect_fournisseur(extracted)
                    if fournisseur_check == "ENDESA":
                        text = extracted
                        break

    fournisseur = detect_fournisseur(text)
    result = {'fournisseur': fournisseur}

    if fournisseur == "ORANGE":
        result.update(extract_orange(text))
    elif fournisseur == "ENGIE":
        result.update(extract_engie(text))
    elif fournisseur == "ENDESA":
        result.update(extract_endesa(text))
    elif fournisseur == "TOTALENERGIES":
        result.update(extract_totalenergies(text))
    else:
        print(f"    ⚠️  Fournisseur non reconnu")

    return result


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        data = extract_invoice_data(sys.argv[1])
        for k, v in data.items():
            print(f"{k}: {v}")
