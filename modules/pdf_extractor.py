def extract_endesa(text: str) -> dict:
    result = {}
    result['tag_ops'] = detect_energie(text)

    # Numéro de facture — électricité
    match = re.search(r'N°\s*DE\s*FACTURE\s*\n(\d+)', text, re.IGNORECASE)
    if match:
        result['numero_facture'] = match.group(1).strip().lstrip('0')
    else:
        # Gaz
        match = re.search(r'Facture\s*n[°º]\s*(\d+)', text, re.IGNORECASE)
        if match:
            result['numero_facture'] = match.group(1).strip().lstrip('0')

    if result.get('numero_facture'):
        result['fragment_at'] = result['numero_facture']

    # Date de prélèvement
    match = re.search(r'pr[eé]lev[eé]\s+le\s+(\d{2})[/\.](\d{2})[/\.](\d{4})', text, re.IGNORECASE)
    if match:
        result['date_prelevement'] = f"{match.group(1)}.{match.group(2)}.{match.group(3)}"
    else:
        match = re.search(r"Date\s+d['']échéance\s+(\d{2})[/\.](\d{2})[/\.](\d{4})", text, re.IGNORECASE)
        if match:
            result['date_prelevement'] = f"{match.group(1)}.{match.group(2)}.{match.group(3)}"

    # Montant TTC
    match = re.search(r'(?:Total TTC|MONTANT TOTAL\s*TTC\s*[AÀ]\s*PAYER)\s*[\n\s]*(\d[\d\s]*[,\.]\d{2})', text, re.IGNORECASE)
    if match:
        result['montant_ttc'] = match.group(1).replace(' ', '').replace(',', '.')

    # Adresse — électricité : après le numéro PCE sous LIEU DE CONSOMMATION
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
        # Adresse — gaz : après Adresse de fourniture
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
