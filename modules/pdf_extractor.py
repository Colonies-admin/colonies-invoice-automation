import pdfplumber
import re


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
    # Ignorer les mentions "Site XX" ou "ATELIER" qui ne font pas partie de l'adresse réelle
    adresse = re.sub(r'\bATELIER\b', '', adresse)
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

    # Numéro facture électricité
    match = re.search(r'N°DEFACTURE\s*\n\d{2}/\d{2}/\d{4}\s+(\d+)', text, re.IGNORECASE)
    if match:
        result['numero_facture'] = match.group(1).strip().lstrip('0')
    else:
        # Gaz
        match = re.search(r'Facture\s*n[°º]\s+(\d+)', text, re.IGNORECASE)
        if match:
            result['numero_facture'] = match.group(1).strip().lstrip('0')

    if result.get('numero_facture'):
        result['fragment_at'] = result['numero_facture']

    # Référence compte de contrat
    match = re.search(r'RÉFÉRENCECOMPTEDECONTRAT\s*\n(\d+)', text, re.IGNORECASE)
    if not match:
        match = re.search(r'RÉFÉRENCE COMPTE DE CONTRAT\s*\n?(\d+)', text, re.IGNORECASE)
    if not match:
        match = re.search(r'REFERENCECOMPTEDECONTRAT\s*\n(\d+)', text, re.IGNORECASE)
    if match:
        result['ref_contrat'] = match.group(1).strip()

    # Date prélèvement
    match = re.search(r'pr[eé]lev[eé]\s+le\s+(\d{2})/(\d{2})/(\d{4})', text, re.IGNORECASE)
    if match:
        result['date_prelevement'] = f"{match.group(1)}.{match.group(2)}.{match.group(3)}"
    else:
        match = re.search(r"Date\s*d.échéance\s+(\d{2})/(\d{2})/(\d{4})", text, re.IGNORECASE)
        if match:
            result['date_prelevement'] = f"{match.group(1)}.{match.group(2)}.{match.group(3)}"

    # Montant TTC électricité
    match = re.search(r'MONTANTTOTAL\s*\nTTCAPAYER\s*\n([\d\s,\.]+)\s*€', text, re.IGNORECASE)
    if match:
        result['montant_ttc'] = match.group(1).replace(' ', '').replace(',', '.')
    else:
        match = re.search(r'Total\s+TTC\s+([\d,\.]+)\s+Eur', text, re.IGNORECASE)
        if match:
            result['montant_ttc'] = match.group(1).replace(',', '.')

    # Adresse électricité — accepte Site XX ou numéro PCE sur la première ligne
    # Ne pas se fier au numéro de site (Site 19 etc.) — on prend la ligne suivante
    match = re.search(r'LIEUDECONSOMMATION\s*\n[^\n]+\n(.+?)\n[^\n]*\n(\d{5})(\w[\w\s]+?)France', text, re.IGNORECASE)
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
        # Adresse gaz
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

    # Clé de matching : adresse + ref contrat si disponible
    adresse = result.get('adresse', '')
    ref_contrat = result.get('ref_contrat', '')
    if adresse and ref_contrat:
        result['numero_compte'] = adresse.replace(' ', '') + '_' + ref_contrat
    else:
        result['numero_compte'] = adresse.replace(' ', '')

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
    else:
        print(f"    ⚠️  Fournisseur non reconnu")

    return result


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        data = extract_invoice_data(sys.argv[1])
        for k, v in data.items():
            print(f"{k}: {v}")
