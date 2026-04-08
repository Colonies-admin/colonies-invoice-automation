import os
import requests

def test_airtable():
    token = os.environ.get("AIRTABLE_TOKEN")
    base_id = os.environ.get("AIRTABLE_BASE_ID")
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    url = f"https://api.airtable.com/v0/meta/bases/{base_id}/tables"
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        tables = response.json().get("tables", [])
        print(f"✅ Connexion Airtable réussie. Tables trouvées :")
        for t in tables:
            print(f"  - {t['name']}")
    else:
        print(f"❌ Erreur : {response.status_code} - {response.text}")

if __name__ == "__main__":
    test_airtable()
