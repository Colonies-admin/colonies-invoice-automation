import os
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

    match = re.search(r'montant total de la TVA pay[eé]e\s*([\d,\.]+)\s*€', text, re.IGNORECASE)
    if match:
        result['tva'] = match.group(1).replace(',', '.')
    else:
        match_ht = re.search(r"total aupr[eè]s d'Orange\s+([\d,\.]+)\s+([\d,\.]+)", text, re.IGNORECASE)
        if match_ht:
            try:
                ht = float(match_ht.group(1).replace(',', '.'))
                ttc = float(match_ht.group(2).replace(',', '.'))
                result['tva'] = f"{ttc - ht:.2f}"
            except (ValueError, TypeError):
                result['tva'] = None
        else:
            result['tva'] = None

    return result


def extract_engie(text: str) -> dict:
    result = {}
    result['tag_ops'] = detect_energie(text)

    is_echeancier_engie = (
        "Echéancier N°" in text
        or "Échéancier N°" in text
        or "ECHEANCIER" in text.upper()
    )
    result['is_echeancier'] = False

    if is_echeancier_engie:
        result['tag_ops'] = "GAS-GAS"

        match = re.search(r'Ech[eé]ancier\s*N°\s*\n?[A-Z]*(\d+)', text, re.IGNORECASE)
        if match:
            result['numero_facture'] = match.group(1).strip()

        match = re.search(r'[Vv]otre\s+r[eé]f[eé]rence\s+client\s*\nCOLONIES\s*\n(\d+)', text)
        if match:
            result['numero_compte'] = match.group(1).strip()

        match = re.search(
            r'Lieu de consommation\s*\nCOLONIES\s*\n([^\n]+)\n(\d{5})\s+([^\n]+)',
            text, re.IGNORECASE
        )
        if match:
            result['adresse'] = f"{match.group(1).strip()} {match.group(3).strip()}"

        result['nature'] = "OPS"
        result['is_hq'] = False

        import datetime
        mois_fr = {1:'janvier', 2:'février', 3:'mars', 4:'avril', 5:'mai', 6:'juin',
                   7:'juillet', 8:'août', 9:'septembre', 10:'octobre', 11:'novembre', 12:'décembre'}
        mois_courant = mois_fr[datetime.date.today().month]
        match = re.search(
            rf'\d{{1,2}}\s+{mois_courant}\s+\d{{4}}\s+[\d\s,\.]+€\s+[\d\s,\.]+€\s+[\d\s,\.]+€\s+([\d\s,\.]+)€',
            text, re.IGNORECASE
        )
        if not match:
            match = re.search(
                r'\d{1,2}\s+\w+\s+\d{4}\s+[\d\s,\.]+€\s+[\d\s,\.]+€\s+[\d\s,\.]+€\s+([\d\s,\.]+)€',
                text
            )
        if match:
            result['montant_ttc'] = match.group(1).replace(' ', '').replace(',', '.')

        mois_map = {'janvier': '01', 'février': '02', 'mars': '03', 'avril': '04',
                    'mai': '05', 'juin': '06', 'juillet': '07', 'août': '08',
                    'septembre': '09', 'octobre': '10', 'novembre': '11', 'décembre': '12'}
        match = re.search(
            r'Ech[eé]ancier des pr[eé]l[eè]vements[^\n]*\n.*?(\d{1,2})\s+(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+(\d{4})',
            text, re.IGNORECASE | re.DOTALL
        )
        if match:
            jour = match.group(1).zfill(2)
            mois_str = match.group(2).lower()
            annee = match.group(3)
            mois_num = mois_map.get(mois_str, '00')
            result['date_prelevement'] = f"{jour}.{mois_num}.{annee}"

    match_lieu = re.search(r'Lieu de consommation.*?COLONIES\s+(.*?)\s+\d{5}', text, re.IGNORECASE | re.DOTALL)
    if match_lieu and "21 RUE DE BRUXELLES" in match_lieu.group(1).upper():
        result['nature'] = "HQ"
        result['is_hq'] = True
    else:
        result['nature'] = "OPS"
        result['is_hq'] = False

    if not result.get('numero_facture'):
        match = re.search(r'N°\s*(\d{9,15})', text)
        if match:
            result['numero_facture'] = match.group(1).strip()

    if not result.get('numero_compte'):
        match = re.search(r'r[eé]f[eé]rence client\s*:?\s*([\d\s]+)', text, re.IGNORECASE)
        if match:
            ref = match.group(1).replace(' ', '').strip()[:12]
            result['numero_compte'] = ref

    if not result.get('fragment_at') and result.get('numero_facture') and result.get('numero_compte'):
        result['fragment_at'] = result['numero_compte'] + '-' + result['numero_facture'].zfill(12)

    mois = {
        'janvier': '01', 'février': '02', 'mars': '03', 'avril': '04',
        'mai': '05', 'juin': '06', 'juillet': '07', 'août': '08',
        'septembre': '09', 'octobre': '10', 'novembre': '11', 'décembre': '12'
    }

    # Format 1 : "prélevé le DD mois YYYY"
    if not result.get('date_prelevement'):
        match = re.search(r'prélevé le\s+(\d{1,2})\s+(\w+)\s+(\d{4})', text, re.IGNORECASE)
        if match:
            jour = match.group(1).zfill(2)
            mois_str = match.group(2).lower()
            annee = match.group(3)
            mois_num = mois.get(mois_str, '00')
            result['date_prelevement'] = f"{jour}.{mois_num}.{annee}"

    # Format 2 : "prélevé le :\nCOLONIES XX,XX euros DD/MM/YYYY"
    if not result.get('date_prelevement'):
        match = re.search(
            r'pr[eé]lev[eé]\s+le\s*:\s*\n[^\n]+\s+(\d{2}/\d{2}/\d{4})',
            text, re.IGNORECASE
        )
        if match:
            d = match.group(1)
            result['date_prelevement'] = f"{d[:2]}.{d[3:5]}.{d[6:]}"

    # Format 3 : "prélevé le : DD/MM/YYYY" (même ligne)
    if not result.get('date_prelevement'):
        match = re.search(
            r'pr[eé]lev[eé]\s+le\s*:\s*(\d{2}/\d{2}/\d{4})',
            text, re.IGNORECASE
        )
        if match:
            d = match.group(1)
            result['date_prelevement'] = f"{d[:2]}.{d[3:5]}.{d[6:]}"

    if not result.get('montant_ttc'):
        match = re.search(r'total TTC\s+([\d\s]+[,\.]\d{2})', text, re.IGNORECASE)
        if match:
            result['montant_ttc'] = match.group(1).replace(' ', '').replace(',', '.')

    # TVA Engie : "TVA à 20,00 % calculée sur X € Y €"
    match = re.search(r'TVA\s+à\s+[\d,\.]+\s*%\s+calcul[eé]e?\s+sur\s+[\d\s,\.]+€\s+([\d\s,\.]+)€', text, re.IGNORECASE)
    if not match:
        match = re.search(r'Total\s+TVA\s*\([^)]*\)\s+([\d\s,\.]+)', text, re.IGNORECASE)
    if match:
        result['tva'] = match.group(1).replace(' ', '').replace(',', '.')
    else:
        result['tva'] = None

    # Fallback adresse de livraison (espace Entreprises & Collectivités)
    if not result.get('adresse') and not result.get('is_hq'):
        match = re.search(
            r'Adresse de livraison\s*:\s*\n([^\n]+)\n(\d{5})\s+([^\n]+)',
            text, re.IGNORECASE
        )
        if match:
            adresse_norm = normalise_adresse(match.group(1).strip())
            ville = match.group(3).strip()
            if "21 RUE DE BRUXELLES" in adresse_norm.upper():
                result['nature'] = "HQ"
                result['is_hq'] = True
            else:
                result['adresse'] = f"{adresse_norm} {ville}"

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

    match = re.search(r'MontantTVA\s+TauxTVA[\d\s,\.%]+appliqu[eé][àa][\d\s,\.]+Eur\s+([\d,\.]+)\s+Eur', text, re.IGNORECASE)
    if not match:
        match = re.search(r'MontantTVA\s+([\d,\.]+)', text, re.IGNORECASE)
    if not match:
        match = re.search(r'Montant\s*TVA\s+([\d,\.]+)', text, re.IGNORECASE)
    if not match:
        match = re.search(r'(?<!HORS)TVA[\d,\.]+%\s+([\d,\.]+)€', text, re.IGNORECASE)
    if match:
        result['tva'] = match.group(1).replace(',', '.')
    else:
        result['tva'] = None

    return result


def extract_totalenergies(text: str, filename: str = "") -> dict:
    result = {}
    text_upper = text.upper().replace(" ", "")

    is_echeancier = (
        "CHEANCIER" in text_upper
        or "MENSUALIT" in text_upper
        or filename.startswith("RE1_")
        or "TABLEAU DE MES MENSUALIT" in text.upper()
    )
    result['is_echeancier'] = is_echeancier

    if "FACTUREDEGAZ" in text_upper or is_echeancier:
        result['tag_ops'] = "GAS-GAS"
    elif "FACTUREDELEC" in text_upper or "ELECTRICIT" in text_upper:
        result['tag_ops'] = "ELE-ELECTRICITY"
    else:
        result['tag_ops'] = "ELE-ELECTRICITY"

    match = re.search(r'N°\s*de\s*client\s*:\s*(\d+)', text, re.IGNORECASE)
    if not match:
        match = re.search(r'R[eé]f[eé]rence\s*client\s*:?\s*(\d+)', text, re.IGNORECASE)
    if not match:
        match = re.search(r'[Rr][eé]f[eé]renceclient:(\d+)', text_upper)
    if match:
        result['numero_client'] = match.group(1).strip()

    match = re.search(r'N°\s*de\s*facture\s*:\s*(\d+)', text, re.IGNORECASE)
    if not match:
        match = re.search(r'Facture\s*n°\s*(\d+)', text, re.IGNORECASE)
    if not match and is_echeancier:
        match = re.search(r'N°\s*(\d{10,})', text, re.IGNORECASE)
    if match:
        result['numero_facture'] = match.group(1).strip()

    if is_echeancier:
        mois_fr = {1:'janv', 2:'févr', 3:'mars', 4:'avr', 5:'mai', 6:'juin',
                   7:'juil', 8:'août', 9:'sept', 10:'oct', 11:'nov', 12:'déc'}
        mois_courant = mois_fr[datetime.date.today().month]
        match = re.search(
            rf'\d{{2}}{mois_courant}[^\n€]*?([\d]+[,\.]\d{{2}})€',
            text, re.IGNORECASE
        )
        if not match:
            match = re.search(
                rf'\d{{2}}\s+{mois_courant}[^\n]*([\d]+[,\.]\d{{2}})\s*€',
                text, re.IGNORECASE
            )
        if not match:
            match = re.search(r'\d{2}[^\n]+([\d]+[,\.]\d{2})\s*€', text)
        if match:
            result['montant_ttc'] = match.group(1).replace(',', '.')
        result['montant_mensuel'] = result.get('montant_ttc', '')
    else:
        match = re.search(r'Montant\s*TTC\s+([\d\s]+[,\.]\d{2})\s*€', text, re.IGNORECASE)
        if match:
            result['montant_ttc'] = match.group(1).replace(' ', '').replace(',', '.')

    match = re.search(r'pr[eé]l[eè]vement\s+(?:de\s+cette\s+facture\s+)?le\s+(\d{2})/(\d{2})/(\d{4})', text, re.IGNORECASE)
    if match:
        result['date_prelevement'] = f"{match.group(1)}.{match.group(2)}.{match.group(3)}"
    elif is_echeancier:
        mois = {'janv': '01', 'fevr': '02', 'mars': '03', 'avr': '04', 'mai': '05',
                'juin': '06', 'juil': '07', 'aout': '08', 'sept': '09', 'oct': '10',
                'nov': '11', 'dec': '12'}
        match = re.search(r'(\d{2})([a-zéû]+)\.?(\d{4})', text, re.IGNORECASE)
        if match:
            jour = match.group(1)
            mois_str = match.group(2).lower()[:4]
            mois_str = mois_str.replace('é', 'e').replace('û', 'u').replace('è', 'e')
            annee = match.group(3)
            mois_num = mois.get(mois_str, '00')
            result['date_prelevement'] = f"{jour}.{mois_num}.{annee}"

    adresse_conso = ""
    if is_echeancier:
        match = re.search(
            r'LIEUDECONSOMMATION[^\n]*\n([^\n]+)\n(\d{5})\s*([^\n]+)',
            text_upper, re.IGNORECASE
        )
        if match:
            rue = match.group(1).strip()
            ville = match.group(3).strip()
            adresse_conso = f"{rue} {ville}"
        else:
            match = re.search(
                r'Lieu de consommation\s*:?\s*\n([^\n]+)\n(\d{5})\s+([^\n]+)',
                text, re.IGNORECASE
            )
            if match:
                adresse_conso = f"{match.group(1).strip()} {match.group(3).strip()}"
    else:
        match = re.search(
            r'Adresse du site[^\n]*\nCOLONIES[^\n]*\n([^\n]+?)\s+(?:Raccordement|Segment|Option|Horizon|Profil|Zone|Tarif)[^\n]*\n(\d{5})\s+([^\s\n]+)',
            text, re.IGNORECASE
        )
        if match:
            adresse_conso = f"{match.group(1).strip()} {match.group(3).strip()}"
        else:
            match = re.search(
                r'Adresse du site[^\n]*\nCOLONIES\s*\n([^\n€]+)\n(\d{5})\s+([^\n€]+)',
                text, re.IGNORECASE
            )
            if match:
                adresse_conso = f"{match.group(1).strip()} {match.group(3).strip()}"
            else:
                match = re.search(r'\d{5}\s+([^,\n]+),([^\n€]+)', text, re.IGNORECASE)
                if match:
                    ville = match.group(1).strip()
                    adresse = re.sub(r'\s+\d+[,\.]\d+.*$', '', match.group(2).strip()).strip()
                    adresse_conso = f"{adresse} {ville}"

    result['adresse_consommation'] = adresse_conso

    hq_addresses = ["21 RUE DE BRUXELLES", "16 RUE CASSETTE",
                    "21RUEDEBRUXELLES", "16RUECASSETTE"]
    is_hq = any(hq in adresse_conso.upper().replace(" ", "") for hq in
                [h.replace(" ", "") for h in hq_addresses])
    result['nature'] = "HQ" if is_hq else "OPS"
    result['is_hq'] = is_hq

    if result.get('numero_client'):
        result['numero_compte'] = result['numero_client']

    if result.get('numero_facture'):
        result['fragment_at'] = result['numero_facture']

    match = re.search(r'Total\s+TVA\s+([\d\s]+[,\.]\d{2})\s*€', text, re.IGNORECASE)
    if match:
        result['tva'] = match.group(1).replace(' ', '').replace(',', '.')
    else:
        result['tva'] = None

    return result


def extract_invoice_data(pdf_path: str) -> dict:
    filename = os.path.basename(pdf_path).upper()

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
        result.update(extract_totalenergies(text, filename))
    else:
        print(f"    ⚠️  Fournisseur non reconnu")

    return result


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        data = extract_invoice_data(sys.argv[1])
        for k, v in data.items():
            print(f"{k}: {v}")
