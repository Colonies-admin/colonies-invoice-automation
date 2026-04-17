import pdfplumber
import re


def detect_fournisseur(text: str) -> str:
    if "ENGIE" in text.upper():
        return "ENGIE"
    if "ORANGE" in text.upper():
        return "ORANGE"
    return "INCONNU"


def extract_orange(text: str) -> dict:
    result = {}

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

    match = re.search(r'COLONIES\s+ETAGE 0\s+(.+?)\s+\d{5}', text)
    if match:
        result['adresse'] = match.group(1).strip()

    return result


def extract_engie(text: str) -> dict:
    result = {}

    # Numéro de facture
    match = re.search(r'N°\s*(\d{12,15})', text)
    if match:
        result['numero_facture'] = match.group(1).strip()

    # Référence client
    match = re.search(r'r[eé]f[eé]rence client\s*:?\s*([\d\s]+)', text, re.IGNORECASE)
    if match:
        ref = match.group(1).replace(' ', '').strip()
        result['numero_compte'] = ref
        if result.get('numero_facture'):
            result['fragment_at'] = ref + '-' + result['numero_facture']

    # Date prélèvement
    mois = {'janvier':'01','février':'02','mars':'03','avril':'04','mai':'05',
            'juin':'06','juillet':'07','août':'08','septembre':'09',
            'octobre':'10','novembre':'11','décembre':'12'}
    match = re.search(r'prélevé le\s+(\d{1,2})\s+(\w+)\s+(\d{4})', text, re.IGNORECASE)
    if match:
        jour = match.group(1).zfill(2)
        mois_str = match.group(2).lower()
        annee = match.group(3)
        mois_num = mois.get(mois_str, '00')
        result['date_prelevement'] = f"{jour}.{mois_num}.{annee}"

    # Montant TTC
    match = re.search(r'total TTC\s+([\d,\.]+)\s*€', text, re.IGNORECASE)
    if match:
        result['montant_ttc'] = match.group(1).replace(',', '.')

    # Adresse lieu de consommation
    match = re.search(r'Lieu de consommation\s*:?\s*COLONIES\s+(.+?)\s+\d{5}', text, re.IGNORECASE | re.DOTALL)
    if match:
        result['adresse'] = match.group(1).strip().replace('\n', ' ')

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
    else:
        print(f"    ⚠️  Fournisseur non reconnu")

    return result


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        data = extract_invoice_data(sys.argv[1])
        for k, v in data.items():
            print(f"{k}: {v}")
