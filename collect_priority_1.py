import os
import time
import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md

DOCS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "priority_1")

URLS = {
    "gened_requirements": {
        "url": "https://gened.umd.edu/node/35",
        "type": "html"
    },
    "academic_policies": {
        "url": "https://academiccatalog.umd.edu/undergraduate/registration-academic-requirements-regulations/",
        "type": "html"
    },
    "registration_guide": {
        "url": "https://registrar.umd.edu/sites/default/files/2025-03/reg-guide-2025-26.pdf",
        "type": "pdf"
    },
    "academic_calendar": {
        "url": "https://registrar.umd.edu/calendars/advisor-calendar",
        "type": "html"
    },
    "grading_policy": {
        "url": "https://policies.umd.edu/academic-affairs/university-of-maryland-grading-symbols-and-notations-used-on-academic-transcripts",
        "type": "html"
    }
}

def download_pdf(url, filename):
    filepath = os.path.join(DOCS_DIR, f"{filename}.pdf")
    if os.path.exists(filepath):
        print(f"SKIP (exists): {filename}.pdf")
        return
    
    print(f"Downloading PDF: {filename}...")
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers, stream=True)
        response.raise_for_status()
        with open(filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"OK: {filename}.pdf")
    except Exception as e:
        print(f"FAIL: {filename}.pdf - {e}")

def scrape_html(url, filename):
    filepath = os.path.join(DOCS_DIR, f"{filename}.md")
    if os.path.exists(filepath):
        print(f"SKIP (exists): {filename}.md")
        return
        
    print(f"Scraping HTML: {filename}...")
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.extract()
            
        markdown_text = md(str(soup), heading_style="ATX")
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(markdown_text)
        print(f"OK: {filename}.md")
    except Exception as e:
        print(f"FAIL: {filename}.md - {e}")

def process_urls():
    os.makedirs(DOCS_DIR, exist_ok=True)
    print(f"Saving documents to {DOCS_DIR}")
    print("=" * 60)
    
    # Process both types
    for key, info in URLS.items():
        if info["type"] == "pdf":
            download_pdf(info["url"], key)
        else:
            scrape_html(info["url"], key)
            time.sleep(1) # Be respectful
                
    print("\n" + "=" * 60)
    print("Collection complete.")

if __name__ == "__main__":
    process_urls()
