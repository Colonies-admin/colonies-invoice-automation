import os
import sys
sys.path.insert(0, '.')
from modules.orange_scraper import download_orange_invoices

results = download_orange_invoices(output_dir="pdfs")

print("Resultats:")
for r in results:
    status = "OK" if r["status"] == "ok" else "ERREUR"
    msg = r.get("message", "")
    print(status + " - ligne " + str(r["index"]) + " - " + str(r.get("pdf_path", "")) + " " + msg)
