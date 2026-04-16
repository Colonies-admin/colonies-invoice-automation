import google.generativeai as genai
import base64
import json
import os


def extract_invoice_data(pdf_path: str) -> dict:
    """
    Extrait les données clés d'une facture via Gemini API.
    Retourne un dict avec : numero_facture, fragment_at,
    numero_compte, adresse, date_prelevement, montant_ttc
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY manquant dans les secrets")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")

    # Lecture et encodage du PDF en base64
    with open(pdf_path, "rb") as f:
        pdf_data = f.read()

    prompt = """Extrait de cette facture Orange les informations suivantes et réponds UNIQUEMENT en JSON valide, sans texte avant ou après :

{
  "numero_facture": "le numéro de facture complet (ex: 01C256N449 26B8- 1C03)",
  "numero_compte": "le numéro de compte internet",
  "adresse": "l'adresse du site (rue et ville, sans code postal)",
  "date_prelevement": "la date de prélèvement au format JJ.MM.AAAA",
  "montant_ttc": "le montant TTC total en chiffres uniquement (ex: 49.99)"
}

Si une information est introuvable, mets null pour ce champ."""

    response = model.generate_content([
        {
            "mime_type": "application/pdf",
            "data": base64.b64encode(pdf_data).decode("utf-8")
        },
        prompt
    ])

    # Parsing de la réponse JSON
    response_text = response.text.strip()

    # Nettoyage au cas où Gemini ajoute des backticks
    if response_text.startswith("```"):
        response_text = response_text.split("```")[1]
        if response_text.startswith("json"):
            response_text = response_text[4:]
    response_text = response_text.strip()

    result = json.loads(response_text)

    # Génération du fragment_at depuis le numéro de facture
    # Règle : 3 derniers chiffres avant l'espace + segment après l'espace sans tiret
    numero = result.get("numero_facture")
    if numero:
        parties = numero.split(" ")
        if len(parties) >= 2:
            trois_derniers = parties[0][-3:]
            segment = parties[1].replace("-", "").strip()
            result["fragment_at"] = trois_derniers + segment
        else:
            result["fragment_at"] = None
    else:
        result["fragment_at"] = None

    return result


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        data = extract_invoice_data(sys.argv[1])
        for k, v in data.items():
            print(f"{k}: {v}")
