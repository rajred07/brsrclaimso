import requests
from duckduckgo_search import DDGS
import os

def download_pdf():
    print("Searching for Infosys ESG Report 2021-22 PDF...")
    try:
        results = DDGS().text("Infosys ESG Report 2021-22 filetype:pdf site:infosys.com", max_results=5)
        pdf_url = None
        for res in results:
            if res['href'].endswith('.pdf'):
                pdf_url = res['href']
                break
        
        if not pdf_url:
            print("Could not find a direct PDF link. Checking alternative search...")
            results = DDGS().text("Infosys Sustainability Report 2021-2022 filetype:pdf site:infosys.com", max_results=5)
            for res in results:
                if res['href'].endswith('.pdf'):
                    pdf_url = res['href']
                    break

        if not pdf_url:
            # Fallback direct link attempt if search fails
            pdf_url = "https://www.infosys.com/sustainability/documents/infosys-esg-report-2021-22.pdf"

        print(f"Found URL to try: {pdf_url}")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(pdf_url, headers=headers)
        if response.status_code == 200 and b'%PDF' in response.content[:10]:
            save_path = os.path.abspath("data/raw/infosys_esg_2021_22.pdf")
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, 'wb') as f:
                f.write(response.content)
            print(f"SUCCESS: Downloaded to {save_path}")
        else:
            print(f"Failed to download. Status code: {response.status_code}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    download_pdf()
