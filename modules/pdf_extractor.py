import pdfplumber
import re

def extract_invoice_data(pdf_path: str) -> dict:
    """
    Extrait les données clés d'une facture Orange.
    Retourne un dict avec : numero_facture, fragment_at, 
    numero_compte, adresse, date_prelevement, montant_ttc
    """
    with pdfplumber.open(pdf_path) as pdf:
        text = ""
        for page in pdf.pages:
            text += page.extract_text() + "\n"

    result = {}

    # Numéro de facture (ex: 01C256N449 26B8- 1C03)
    match = re.search(r'n° de facture\s*:\s*([A-Z0-9]{10,12}\s+\d{2}[A-Z]\d+[-\s]+\d[A-Z]\d{2})', text, re.IGNORECASE)
    if match:
        numero_brut = match.group(1).strip()
        result['numero_facture'] = numero_brut

        # Génération du fragment AT
        # Règle : 3 derniers chiffres avant l'espace + segment après l'espace sans tiret
        parties = numero_brut.split(' ')
        if len(parties) >= 2:
            trois_derniers = parties[0][-3:]
            segment = parties[1].replace('-', '').strip()
            result['fragment_at'] = trois_derniers + segment
    
    # Numéro de compte internet
    match = re.search(r'n° de compte internet\s*:\s*(\d+)', text, re.IGNORECASE)
    if match:
        result['numero_compte'] = match.group(1).strip()

    # Date de prélèvement (ex: au 20.03.2026)
    match = re.search(r'au\s+(\d{2}\.\d{2}\.\d{4})', text)
    if match:
        result['date_prelevement'] = match.group(1).strip()

    # Montant TTC total
    match = re.search(r'(\d+[,\.]\d{2})\s*€\s*TTC', text)
    if match:
        result['montant_ttc'] = match.group(1).replace(',', '.')

    # Adresse (ligne après COLONIES ETAGE 0)
    match = re.search(r'COLONIES\s+ETAGE 0\s+(.+?)\s+\d{5}', text)
    if match:
        result['adresse'] = match.group(1).strip()

    return result


if __name__ == "__main__":
    # Test rapide sur un PDF local
    import sys
    if len(sys.argv) > 1:
        data = extract_invoice_data(sys.argv[1])
        for k, v in data.items():
            print(f"{k}: {v}")
