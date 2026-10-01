import os
import sys
import time
import json
import fitz  # PyMuPDF
from PIL import Image
import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

PROMPT = """
You are a strict data extraction AI for a corporate sustainability audit.
Your ONLY job is to read the image of the ESG report page provided and extract quantitative environmental claims that compare two periods or scenarios.
Examples of what to extract: "reduced by 15%", "saved 2.5 million liters", "decreased from X to Y", "scope 1 emissions were 50 tCO2e (a drop of 5% YoY)".
Do NOT extract future targets (e.g., "we aim to reduce by 2030").

Output MUST be a pure, valid JSON array. DO NOT wrap the JSON in markdown blocks (e.g., do not use ```json). Just return the raw array.
Each object in the array must contain exactly these keys:
- metric: The specific metric name (e.g., 'Scope 1 Emissions', 'Municipal Water Withdrawal')
- operation: Strictly one of: 'percentage_change', 'absolute_change', 'yoy_direction', 'value_equality'
- stated_result: The numerical result (number only, e.g., 60.07)
- unit: The unit of measurement (e.g., '%', 'lakh kWh', 'tCO2e')
- period_current: The current period (e.g., 'FY24')
- period_compare: The baseline or previous period (e.g., 'FY23', 'BAU scenario', 'baseline')
- original_quote: The exact verbatim sentence from the text proving this claim.

If no comparison claims exist on this page, return exactly this: []
"""

def extract_claims_from_images(pdf_path, start_page, end_page):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[!] ERROR: GEMINI_API_KEY environment variable not found. Please set it in backend/.env")
        sys.exit(1)

    genai.configure(api_key=api_key)
    # Using gemini-1.5-pro as requested
    model = genai.GenerativeModel("gemini-3.5-flash", generation_config={"response_mime_type": "application/json"})
    
    print(f"Reading PDF: {pdf_path}")
    doc = fitz.open(pdf_path)
    
    all_claims = []
    
    # Calculate zero-indexed bounds
    # Note: start_page and end_page are 1-indexed for the user. (e.g. Page 3 is index 2)
    start_idx = start_page - 1
    end_idx = min(end_page - 1, len(doc) - 1)
    
    print(f"Targeting pages {start_page} to {end_idx + 1} (total {end_idx - start_idx + 1} pages).")
    
    for i in range(start_idx, end_idx + 1):
        actual_page_num = i + 1
        print(f"\n--> Rendering Page {actual_page_num} to image...")
        
        # 1. Render page to image using PyMuPDF
        page = doc[i]
        # Increase resolution slightly (2x) for better OCR accuracy by Gemini
        matrix = fitz.Matrix(2, 2)
        pix = page.get_pixmap(matrix=matrix)
        
        # Convert PyMuPDF Pixmap to PIL Image
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        
        print(f"--> Prompting Gemini Vision with Page {actual_page_num}...")
        try:
            # 2. Pass the Prompt AND the PIL Image directly to Gemini
            response = model.generate_content([PROMPT, img])
            
            # Clean the response text
            raw_text = response.text.strip()
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            if raw_text.startswith("```"):
                raw_text = raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
                
            result = json.loads(raw_text.strip())
            
            # Append provenance metadata
            for r in result:
                r['source_batch'] = actual_page_num
                r['source_pages'] = f"Page {actual_page_num}"
                
            all_claims.extend(result)
            print(f"    Found {len(result)} claims on page {actual_page_num}.")
        except Exception as e:
            print(f"    [!] Error processing page {actual_page_num}: {e}")
            
        # Add a 15-second delay to avoid hitting the Gemini Free Tier rate limits (15 RPM)
        if i < end_idx:
            print("    [Rate Limit] Waiting 15 seconds before next request...")
            time.sleep(15)

    # Save output
    os.makedirs("data/claims", exist_ok=True)
    out_path = "data/claims/extracted_claims_vision.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_claims, f, indent=2)
        
    print(f"\nFinished Vision LLM Extraction phase. Total claims found: {len(all_claims)}")
    print(f"Successfully saved final structured artifacts to '{out_path}'")

if __name__ == "__main__":
    pdf_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../infosys-esg-report-2021-22.pdf"))
    if not os.path.exists(pdf_path):
        print(f"[!] Error: Could not find PDF at {pdf_path}.")
        sys.exit(1)
        
    extract_claims_from_images(pdf_path, start_page=3, end_page=20)
