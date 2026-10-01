import os
import sys
import json
import time
import google.generativeai as genai

PROMPT = """
You are a strict data extraction AI for a corporate sustainability audit.
Your ONLY job is to read the attached PDF document and extract quantitative environmental claims that compare two periods or scenarios.
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
- source_pages: The exact page number(s) within this small document where you found the claim.

If no comparison claims exist, return exactly this: []
"""

def run_direct_extraction():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[!] ERROR: GEMINI_API_KEY environment variable not found.")
        sys.exit(1)

    genai.configure(api_key=api_key)
    
    pdf_path = "infosys_target_pages.pdf"
    if not os.path.exists(pdf_path):
        print(f"Error: {pdf_path} not found.")
        sys.exit(1)
        
    print(f"Uploading {pdf_path} to Gemini File API...")
    # Use the File API to upload
    uploaded_file = genai.upload_file(path=pdf_path, display_name="Target Pages")
    print(f"File uploaded successfully as: {uploaded_file.uri}")
    
    # Wait for the file to be processed
    print("Waiting for file processing...")
    while True:
        file_info = genai.get_file(uploaded_file.name)
        if file_info.state.name == "ACTIVE":
            break
        elif file_info.state.name == "FAILED":
            print("File processing failed.")
            sys.exit(1)
        time.sleep(2)
        
    print("File is active. Prompting Gemini (Multimodal)...")
    model = genai.GenerativeModel("models/gemini-3.5-flash", generation_config={"response_mime_type": "application/json"})
    
    try:
        response = model.generate_content([uploaded_file, PROMPT])
        
        raw_text = response.text.strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.startswith("```"):
            raw_text = raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
            
        result = json.loads(raw_text.strip())
        print(f"\nExtraction complete! Found {len(result)} claims.")
        
        os.makedirs("data/claims", exist_ok=True)
        out_path = "data/claims/extracted_claims.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
            
        print(f"Saved claims to {out_path}")
        
    except Exception as e:
        print(f"\n[!] Error during extraction: {e}")
        
    finally:
        # Cleanup
        print("Cleaning up file from Google servers...")
        genai.delete_file(uploaded_file.name)
        
if __name__ == "__main__":
    run_direct_extraction()
