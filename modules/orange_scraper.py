import os
import time
from playwright.sync_api import sync_playwright

def download_orange_invoices(output_dir: str = "pdfs") -> list:
    """
    Se connecte au portail Orange Pro, navigue sur chaque ligne
    et télécharge la dernière facture disponible.
    Retourne une liste de chemins de PDFs téléchargés.
    """
    os.makedirs(output_dir, exist_ok=True)
    
    login = os.environ.get("ORANGE_LOGIN")
    password = os.environ.get("ORANGE_PASSWORD")
    
    results = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        # Connexion
        print("Connexion au portail Orange Pro...")
        page.goto("https://pro.orange.fr")
        page.wait_for_load_state("networkidle")
        
        # Login
        page.fill('input[type="email"]', login)
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")
        page.fill('input[type="password"]', password)
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")
        
        print("Connecte. Navigation vers les lignes...")
        
        # Navigation vers la liste des lignes
        page.goto("https://pro.orange.fr/espace-client/")
        page.wait_for_load_state("networkidle")
        time.sleep(3)
        
        # Récupère toutes les lignes
        lignes = page.query_selector_all('[data-testid="line-item"]')
        print(f"{len(lignes)} lignes trouvees")
        
        for i, ligne in enumerate(lignes):
            try:
                print(f"Traitement ligne {i+1}/{len(lignes)}...")
                ligne.click()
                page.wait_for_load_state("networkidle")
                time.sleep(2)
                
                # Cherche le lien de téléchargement de la facture
                with page.expect_download() as download_info:
                    page.click('a[href*="facture"], a[href*="invoice"], button:has-text("Télécharger")')
                
                download = download_info.value
                pdf_path = os.path.join(output_dir, f"facture_{i+1}.pdf")
                download.save_as(pdf_path)
                
                results.append({
                    "index": i+1,
                    "pdf_path": pdf_path,
                    "status": "ok"
                })
                print(f"OK - facture_{i+1}.pdf")
                
                # Retour à la liste
                page.go_back()
                page.wait_for_load_state("networkidle")
                time.sleep(2)
                
            except Exception as e:
                print(f"ERREUR ligne {i+1}: {str(e)}")
                results.append({
                    "index": i+1,
                    "pdf_path": None,
                    "status": "erreur",
                    "message": str(e)
                })
                page.go_back()
                page.wait_for_load_state("networkidle")
        
        browser.close()
    
    return results
