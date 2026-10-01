import os
import sys
import json
import time
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

PROMPT = """
You are a strict data extraction AI for a corporate sustainability audit.
Your ONLY job is to read the attached PDF report and extract quantitative environmental claims that compare two periods or scenarios.
Examples of what to extract: "reduced by 15%", "saved 2.5 million liters", "decreased from X to Y", "scope 1 emissions were 50 tCO2e (a drop of 5% YoY)".
Do NOT extract future targets (e.g., "we aim to reduce by 2030").

Output MUST be a pure, valid JSON array. DO NOT wrap the JSON in markdown blocks (e.g., do not use ```json). Just return the raw array.
Each object in the array must contain exactly these keys:
- metric: The specific metric name (e.g., 'Scope 1 Emissions', 'Energy Consumption Total', 'Scope 2 Emissions')
- operation: Strictly one of: 'percentage_change', 'absolute_change'
- stated_result: The numerical result (number only, e.g., 60.07). If it's a reduction, output a positive number if the text says "reduced by X%".
- unit: The unit of measurement (e.g., '%', 'lakh kWh', 'tCO2e')
- period_current: The current period (e.g., 'FY22')
- period_compare: The baseline or previous period (e.g., 'FY21')
- original_quote: The exact verbatim sentence from the text proving this claim.

If no comparison claims exist, return exactly this: []
"""

def process_pdf():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[!] ERROR: GEMINI_API_KEY environment variable not found in .env")
        sys.exit(1)

    genai.configure(api_key=api_key)
    
    pdf_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../infosys-esg-report-2021-22.pdf"))
    if not os.path.exists(pdf_path):
        print(f"[!] Error: Could not find PDF at {pdf_path}")
        sys.exit(1)

    print(f"Uploading {pdf_path} to Gemini...")
    sample_file = genai.upload_file(path=pdf_path, display_name="Infosys ESG Report")

    print(f"Uploaded file '{sample_file.display_name}' as: {sample_file.uri}")
    
    # Wait for the file to be processed
    print("Waiting for file processing...")
    while True:
        file_info = genai.get_file(sample_file.name)
        if file_info.state.name == 'ACTIVE':
            break
        elif file_info.state.name == 'FAILED':
            print("File processing failed.")
            sys.exit(1)
        time.sleep(2)

    print("Prompting Gemini 3.5 Flash to read the entire PDF directly...")
    model = genai.GenerativeModel(model_name="gemini-3.5-flash", generation_config={"response_mime_type": "application/json"})
    
    response = model.generate_content([sample_file, PROMPT])
    
    raw_text = response.text.strip()
    if raw_text.startswith("```json"):
        raw_text = raw_text[7:]
    if raw_text.startswith("```"):
        raw_text = raw_text[3:]
    if raw_text.endswith("```"):
        raw_text = raw_text[:-3]
        
    result = json.loads(raw_text.strip())
    
    for r in result:
        r['source_batch'] = "PDF"
        r['source_pages'] = "Whole Document"
        
    out_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../data/claims/extracted_claims.json"))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
        
    print(f"\nSuccessfully extracted {len(result)} claims from the PDF directly!")
    print(f"Saved to {out_path}")
    
    # Clean up the uploaded file
    genai.delete_file(sample_file.name)

if __name__ == "__main__":
    process_pdf()
