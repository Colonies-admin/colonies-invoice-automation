import os

sheet_id = os.environ.get("GOOGLE_SHEETS_ID", "NON TROUVÉ")
print(f"Sheet ID = '{sheet_id}'")
print(f"Longueur = {len(sheet_id)}")

creds = os.environ.get("GOOGLE_CREDENTIALS", "NON TROUVÉ")
print(f"Credentials présents = {'oui' si len(creds) > 10 else 'non'}")
