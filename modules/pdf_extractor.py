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
    match = re.search(r'(Electricité|Gaz naturel|FACTURE DE GAZ|FACTURE ELECTRICITÉ)\s*', text, re.IGNORECASE)
    if match:
        if "gaz" in match.group(1).lower():
            return "GAS-GAS"
        else:
            return "ELE-ELECTRICITY"
    return "ELE-ELECTRICITY"


def normalise_adresse(adresse: str) -> str:
    adresse = adresse.upper().strip()
    adresse = re.sub(r'\s+', ' ', adresse)
    adresse = re.sub(r'\s*\.\.\s*', ' ', adresse)
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

    match = re.search(r'N°\s*DE\s*FACTURE\s*\n(\d+)', text, re.IGNORECASE)
    if match:
        result['numero_facture'] = match.group(1).strip().lstrip('0')
    else:
        match = re.search(r'Facture\s*n[°º]\s*(\d+)', text, re.IGNORECASE)
        if match:
            result['numero_facture'] = match.group(1).strip().lstrip('0')

    if result.get('numero_facture'):
        result['fragment_at'] = result['numero_facture']

    match = re.search(r'pr[eé]lev[eé]\s+le\s+(\d{2})[/\.](\d{2})[/\.](\d{4})', text, re.IGNORECASE)
    if match:
        result['date_prelevement'] = f"{match.group(1)}.{match.group(2)}.{match.group(3)}"
    else:
        match = re.search(r"Date\s+d['']échéance\s+(\d{2})[/\.](\d{2})[/\.](\d{4})", text, re.IGNORECASE)
        if match:
            result['date_prelevement'] = f"{match.group(1)}.{match.group(2)}.{match.group(3)}"

    match = re.search(r'(?:Total TTC|MONTANT TOTAL\s*TTC\s*[AÀ]\s*PAYER)\s*[\n\s]*(\d[\d\s]*[,\.]\d{2})', text, re.IGNORECASE)
    if match:
        result['montant_ttc'] = match.group(1).replace(' ', '').replace(',', '.')

    match = re.search(r'LIEU DE CONSOMMATION\s*\n\s*\d+\s*\n(.+?)\s+\d{5}\s+(.+?)\s+France', text, re.IGNORECASE)
    if match:
        adresse_brute = match.group(1).strip() + ' ' + match.group(2).strip()
        adresse_norm = normalise_adresse(adresse_brute)
        if "21 RUE DE BRUXELLES" in adresse_norm:
            result['nature'] = "HQ"
            result['is_hq'] = True
        else:
            result['nature'] = "OPS"
            result['is_hq'] = False
            result['adresse'] = adresse_norm
    else:
        match = re.search(r'Adresse de fourniture\s*:\s*\d+\s*\n(.+?)\s+-\s*\d{5}\s*-\s*(.+?)\s+France', text, re.IGNORECASE)
        if match:
            adresse_brute = match.group(1).strip()
            adresse_norm = normalise_adresse(adresse_brute)
            if "21 RUE DE BRUXELLES" in adresse_norm:
                result['nature'] = "HQ"
                result['is_hq'] = True
            else:
                result['nature'] = "OPS"
                result['is_hq'] = False
                result['adresse'] = adresse_norm
        else:
            result['nature'] = "OPS"
            result['is_hq'] = False

    result['numero_compte'] = result.get('adresse', '')
    return result


def extract_invoice_data(pdf_path: str) -> dict:
    with pdfplumber.open(pdf_path) as pdf:
        text = ""
        for page in pdf.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"

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
