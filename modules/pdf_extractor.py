import google.genai as genai
import base64
import json
import os


def extract_invoice_data(pdf_path: str) -> dict:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY manquant dans les secrets")

    client = genai.Client(api_key=api_key)

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

    response = client.models.generate_content(
        model="gemini-1.5-flash",
        contents=[
            genai.types.Part.from_bytes(data=pdf_data, mime_type="application/pdf"),
            prompt
        ]
    )

    response_text = response.text.strip()

    if response_text.startswith("```"):
        response_text = response_text.split("```")[1]
        if response_text.startswith("json"):
            response_text = response_text[4:]
    response_text = response_text.strip()

    result = json.loads(response_text)

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
