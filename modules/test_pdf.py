import sys
import os
sys.path.insert(0, '.')
from modules.pdf_extractor import extract_invoice_data

# Test sur les 3 factures exemples
test_cases = [
    {
        "fichier": "test1.pdf",
        "fragment_attendu": "44926B8"
    },
    {
        "fichier": "test2.pdf", 
        "fragment_attendu": "3636B3"
    },
    {
        "fichier": "test3.pdf",
        "fragment_attendu": "9696B3"
    }
]

for tc in test_cases:
    if os.path.exists(tc["fichier"]):
        data = extract_invoice_data(tc["fichier"])
        fragment = data.get("fragment_at", "NON TROUVÉ")
        ok = "✅" if fragment == tc["fragment_attendu"] else "❌"
        print(f"{ok} {tc['fichier']} → fragment: {fragment} (attendu: {tc['fragment_attendu']})")
        print(f"   compte: {data.get('numero_compte')}")
        print(f"   date prélèvement: {data.get('date_prelevement')}")
        print(f"   montant TTC: {data.get('montant_ttc')}")
        print()
