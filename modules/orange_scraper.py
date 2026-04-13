import os
import time
from playwright.sync_api import sync_playwright

def download_orange_invoices(output_dir="pdfs"):
    os.makedirs(output_dir, exist_ok=True)
    
    login = os.environ.get("ORANGE_LOGIN")
    password = os.environ.get("ORANGE_PASSWORD")
    
    results = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        page.set_default_timeout(60000)
        
        print("Connexion au portail Orange Pro...")
        page.goto("https://pro.orange.fr", wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        print("Page chargee: " + page.title())
        
        try:
            page.wait_for_selector('#login', timeout=30000)
            page.fill('#login', login)
            page.click('button[type="submit"]')
            page.wait_for_load_state("domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)
            page.wait_for_selector('#password', timeout=30000)
            page.fill('#password', password)
            page.click('button[type="submit"]')
            page.wait_for_load_state("domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)
            print("Connecte. URL: " + page.url)
        except Exception as e:
            print("Erreur login: " + str(e))
            page.screenshot(path="debug_login.png")
            raise
        
        print("Navigation vers les lignes...")
        page.goto("https://pro.orange.fr/espace-client/", wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        print("Page lignes chargee: " + page.url)
        
        lignes = page.query_selector_all('[data-testid="line-item"]')
        print(str(len(lignes)) + " lignes trouvees")
        
        for i, ligne in enumerate(lignes):
            try:
                print("Traitement ligne " + str(i+1) + "/" + str(len(lignes)) + "...")
                ligne.click()
                page.wait_for_load_state("domcontentloaded")
                page.wait_for_timeout(2000)
                
                with page.expect_download(timeout=30000) as download_info:
                    page.click('a[href*="facture"], a[href*="invoice"], button:has-text("Telecharger")')
                
                download = download_info.value
                pdf_path = os.path.join(output_dir, "facture_" + str(i+1) + ".pdf")
                download.save_as(pdf_path)
                
                results.append({
                    "index": i+1,
                    "pdf_path": pdf_path,
                    "status": "ok"
                })
                print("OK - facture_" + str(i+1) + ".pdf")
                
                page.go_back()
                page.wait_for_load_state("domcontentloaded")
                page.wait_for_timeout(2000)
                
            except Exception as e:
                print("ERREUR ligne " + str(i+1) + ": " + str(e))
                results.append({
                    "index": i+1,
                    "pdf_path": None,
                    "status": "erreur",
                    "message": str(e)
                })
                try:
                    page.go_back()
                    page.wait_for_load_state("domcontentloaded")
                except:
                    pass
        
        browser.close()
    
    return results
