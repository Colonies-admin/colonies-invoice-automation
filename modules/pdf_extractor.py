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

    # TVA Orange : "montant total de la TVA payée 10,80€"
    match = re.search(r'montant total de la TVA pay[eé]e\s*([\d,\.]+)\s*€', text, re.IGNORECASE)
    if match:
        result['tva'] = match.group(1).replace(',', '.')
    else:
        result['tva'] = None

    return result


def extract_engie(text: str) -> dict:
    result = {}
    result['tag_ops'] = detect_energie(text)

    # --- Détection échéancier Engie ---
    # On traite les échéanciers Engie comme des factures normales (match Airtable inclus)
    is_echeancier_engie = (
        "Echéancier N°" in text
        or "Échéancier N°" in text
        or "ECHEANCIER" in text.upper()
    )
    result['is_echeancier'] = False  # pas de traitement spécial pour Engie

    if is_echeancier_engie:
        result['tag_ops'] = "GAS-GAS"

        # N° échéancier : "Echéancier N°\nPP912500414117" → on garde juste les chiffres
        match = re.search(r'Ech[eé]ancier\s*N°\s*\n?[A-Z]*(\d+)', text, re.IGNORECASE)
        if match:
            result['numero_facture'] = match.group(1).strip()
            # fragment_at sera construit avec ref_client-numero_facture comme facture normale

        # Ref client : "Votre référence client\nCOLONIES\n300003329622"
        match = re.search(r'[Vv]otre\s+r[eé]f[eé]rence\s+client\s*\nCOLONIES\s*\n(\d+)', text)
        if match:
            result['numero_compte'] = match.group(1).strip()

        # Adresse conso : "Lieu de consommation\nCOLONIES\n9 RUE DE MAYENNE\n94000 CRETEIL"
        match = re.search(
            r'Lieu de consommation\s*\nCOLONIES\s*\n([^\n]+)\n(\d{5})\s+([^\n]+)',
            text, re.IGNORECASE
        )
        if match:
            result['adresse'] = f"{match.group(1).strip()} {match.group(3).strip()}"

        result['nature'] = "OPS"
        result['is_hq'] = False

        # Montant mensualité du mois courant (TTC)
        import datetime
        mois_fr = {1:'janvier', 2:'février', 3:'mars', 4:'avril', 5:'mai', 6:'juin',
                   7:'juillet', 8:'août', 9:'septembre', 10:'octobre', 11:'novembre', 12:'décembre'}
        mois_courant = mois_fr[datetime.date.today().month]
        # Cherche "16 avril 2026 496,53 € 0,00 € 99,32 € 595,85 €" → prend le dernier montant (TTC)
        match = re.search(
            rf'\d{{1,2}}\s+{mois_courant}\s+\d{{4}}\s+[\d\s,\.]+€\s+[\d\s,\.]+€\s+[\d\s,\.]+€\s+([\d\s,\.]+)€',
            text, re.IGNORECASE
        )
        if not match:
            # Fallback : première ligne du tableau, dernier montant
            match = re.search(
                r'\d{1,2}\s+\w+\s+\d{4}\s+[\d\s,\.]+€\s+[\d\s,\.]+€\s+[\d\s,\.]+€\s+([\d\s,\.]+)€',
                text
            )
        if match:
            result['montant_ttc'] = match.group(1).replace(' ', '').replace(',', '.')

        # Date prélèvement : cherche dans le tableau des mensualités (format "16 avril 2026")
        mois_map = {'janvier': '01', 'février': '02', 'mars': '03', 'avril': '04',
                    'mai': '05', 'juin': '06', 'juillet': '07', 'août': '08',
                    'septembre': '09', 'octobre': '10', 'novembre': '11', 'décembre': '12'}
        # Cherche après "Echéancier des prélèvements"
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
    if not result.get('date_prelevement'):
        match = re.search(r'prélevé le\s+(\d{1,2})\s+(\w+)\s+(\d{4})', text, re.IGNORECASE)
        if match:
            jour = match.group(1).zfill(2)
            mois_str = match.group(2).lower()
            annee = match.group(3)
            mois_num = mois.get(mois_str, '00')
            result['date_prelevement'] = f"{jour}.{mois_num}.{annee}"

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

    # TVA Endesa : plusieurs formats
    # Format GAZ : "MontantTVA TauxTVA20,00%appliquéà1111,20Eur 222,24 Eur"
    # Format ELE : "TVA 20,0 % 68,68 €" ou "TVA 20,0 % 68,68 €"
    match = re.search(r'MontantTVA\s+TauxTVA[\d\s,\.%]+appliqu[eé][àa][\d\s,\.]+Eur\s+([\d,\.]+)\s+Eur', text, re.IGNORECASE)
    if not match:
        match = re.search(r'MontantTVA\s+([\d,\.]+)', text, re.IGNORECASE)
    if not match:
        match = re.search(r'Montant\s*TVA\s+([\d,\.]+)', text, re.IGNORECASE)
    if not match:
        # Format ELE collé : "TVA20,0% 68,68€" (pas HORSTVA)
        match = re.search(r'(?<!HORS)TVA[\d,\.]+%\s+([\d,\.]+)€', text, re.IGNORECASE)
    if match:
        result['tva'] = match.group(1).replace(',', '.')
    else:
        result['tva'] = None

    return result


def extract_totalenergies(text: str, filename: str = "") -> dict:
    result = {}
    text_upper = text.upper().replace(" ", "")

    # --- Détection échéancier GAZ ---
    is_echeancier = (
        "CHEANCIER" in text_upper
        or "MENSUALIT" in text_upper
        or filename.startswith("RE1_")
        or "TABLEAU DE MES MENSUALIT" in text.upper()
    )
    result['is_echeancier'] = is_echeancier

    # --- Type énergie ---
    if "FACTUREDEGAZ" in text_upper or is_echeancier:
        result['tag_ops'] = "GAS-GAS"
    elif "FACTUREDELEC" in text_upper or "ELECTRICIT" in text_upper:
        result['tag_ops'] = "ELE-ELECTRICITY"
    else:
        result['tag_ops'] = "ELE-ELECTRICITY"

    # --- Numéro client ---
    # Texte normal : "N° de client : 112362748"
    # Texte collé  : "Référenceclient:113329809"
    match = re.search(r'N°\s*de\s*client\s*:\s*(\d+)', text, re.IGNORECASE)
    if not match:
        match = re.search(r'R[eé]f[eé]rence\s*client\s*:?\s*(\d+)', text, re.IGNORECASE)
    if not match:
        # texte collé sans espaces
        match = re.search(r'[Rr][eé]f[eé]renceclient:(\d+)', text_upper)
    if match:
        result['numero_client'] = match.group(1).strip()

    # --- Numéro facture / échéancier ---
    match = re.search(r'N°\s*de\s*facture\s*:\s*(\d+)', text, re.IGNORECASE)
    if not match:
        match = re.search(r'Facture\s*n°\s*(\d+)', text, re.IGNORECASE)
    if not match and is_echeancier:
        # "N° 602500394072" dans le titre de l'échéancier
        match = re.search(r'N°\s*(\d{10,})', text, re.IGNORECASE)
    if match:
        result['numero_facture'] = match.group(1).strip()

    # --- Montant TTC ---
    if is_echeancier:
        # Tableau mensualités : "05avr.2026 129,00€" ou "05 avr. 2026  129,00 €"
        # Cherche la ligne du mois courant
        mois_fr = {1:'janv', 2:'févr', 3:'mars', 4:'avr', 5:'mai', 6:'juin',
                   7:'juil', 8:'août', 9:'sept', 10:'oct', 11:'nov', 12:'déc'}
        mois_courant = mois_fr[datetime.date.today().month]
        # Format collé sans espaces : "05avr.2026129,00€"
        match = re.search(
            rf'\d{{2}}{mois_courant}[^\n€]*?([\d]+[,\.]\d{{2}})€',
            text, re.IGNORECASE
        )
        if not match:
            # Format avec espaces : "05 avr. 2026  129,00 €"
            match = re.search(
                rf'\d{{2}}\s+{mois_courant}[^\n]*([\d]+[,\.]\d{{2}})\s*€',
                text, re.IGNORECASE
            )
        if not match:
            # Fallback : première ligne du tableau
            match = re.search(r'\d{2}[^\n]+([\d]+[,\.]\d{2})\s*€', text)
        if match:
            result['montant_ttc'] = match.group(1).replace(',', '.')
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
        # Cherche "05janv.2026" ou "05 janv. 2026" dans le tableau des mensualités
        mois = {'janv': '01', 'fevr': '02', 'mars': '03', 'avr': '04', 'mai': '05',
                'juin': '06', 'juil': '07', 'aout': '08', 'sept': '09', 'oct': '10',
                'nov': '11', 'dec': '12'}
        # Format collé : "05janv.2026"
        match = re.search(r'(\d{2})([a-zéû]+)\.?(\d{4})', text, re.IGNORECASE)
        if match:
            jour = match.group(1)
            mois_str = match.group(2).lower()[:4]
            # normaliser accents
            mois_str = mois_str.replace('é', 'e').replace('û', 'u').replace('è', 'e')
            annee = match.group(3)
            mois_num = mois.get(mois_str, '00')
            result['date_prelevement'] = f"{jour}.{mois_num}.{annee}"

    # --- Adresse de consommation ---
    adresse_conso = ""
    if is_echeancier:
        # Texte collé : "Lieudeconsommation:...\n22RUEDESHETRES\n92000NANTERRE"
        # On travaille sur le texte avec espaces supprimés pour trouver le bloc
        match = re.search(
            r'LIEUDECONSOMMATION[^\n]*\n([^\n]+)\n(\d{5})\s*([^\n]+)',
            text_upper, re.IGNORECASE
        )
        if match:
            rue = match.group(1).strip()
            ville = match.group(3).strip()
            adresse_conso = f"{rue} {ville}"
        else:
            # Fallback texte normal
            match = re.search(
                r'Lieu de consommation\s*:?\s*\n([^\n]+)\n(\d{5})\s+([^\n]+)',
                text, re.IGNORECASE
            )
            if match:
                adresse_conso = f"{match.group(1).strip()} {match.group(3).strip()}"
    else:
        # Format page 3 pdfplumber : colonnes sur même ligne
        # "Adresse du site Tarif...\nCOLONIES Segment...\n15 RUE DES ILES Raccordement...\n31500 TOULOUSE Option..."
        match = re.search(
            r'Adresse du site[^\n]*\nCOLONIES[^\n]*\n([^\n]+?)\s+(?:Raccordement|Segment|Option|Horizon|Profil|Zone|Tarif)[^\n]*\n(\d{5})\s+([^\s\n]+)',
            text, re.IGNORECASE
        )
        if match:
            adresse_conso = f"{match.group(1).strip()} {match.group(3).strip()}"
        else:
            # Format page 3 simple : "Adresse du site\nCOLONIES\n15 RUE DES ILES\n31500 TOULOUSE"
            match = re.search(
                r'Adresse du site[^\n]*\nCOLONIES\s*\n([^\n€]+)\n(\d{5})\s+([^\n€]+)',
                text, re.IGNORECASE
            )
            if match:
                adresse_conso = f"{match.group(1).strip()} {match.group(3).strip()}"
            else:
                # Fallback tableau page 2 : "31500 TOULOUSE,15 RUE DES\nILES"
                match = re.search(r'\d{5}\s+([^,\n]+),([^\n€]+)', text, re.IGNORECASE)
                if match:
                    ville = match.group(1).strip()
                    adresse = re.sub(r'\s+\d+[,\.]\d+.*$', '', match.group(2).strip()).strip()
                    adresse_conso = f"{adresse} {ville}"

    result['adresse_consommation'] = adresse_conso

    # --- Nature HQ / OPS : adresse de CONSOMMATION uniquement ---
    hq_addresses = ["21 RUE DE BRUXELLES", "16 RUE CASSETTE",
                    "21RUEDEBRUXELLES", "16RUECASSETTE"]
    is_hq = any(hq in adresse_conso.upper().replace(" ", "") for hq in
                [h.replace(" ", "") for h in hq_addresses])
    result['nature'] = "HQ" if is_hq else "OPS"
    result['is_hq'] = is_hq

    # --- numero_compte = numero_client pour matching Airtable ---
    if result.get('numero_client'):
        result['numero_compte'] = result['numero_client']

    # --- fragment_at ---
    if result.get('numero_facture'):
        result['fragment_at'] = result['numero_facture']

    # --- TVA TotalEnergies : "Total TVA 59,36 €" ---
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
