import json
import os
import sys
import time
import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()

PROMPT = """
You are a strict data extraction AI for a corporate sustainability audit.
Your ONLY job is to read the text block provided and extract quantitative environmental claims that compare two periods or scenarios.
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

If no comparison claims exist in this text block, return exactly this: []
"""

def extract_claims(batches_file):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[!] ERROR: GEMINI_API_KEY environment variable not found.")
        print("Set it using: $env:GEMINI_API_KEY=\"your_key\"")
        sys.exit(1)

    genai.configure(api_key=api_key)
    # Using gemini-3.5-flash for standard extraction
    model = genai.GenerativeModel("models/gemini-3.5-flash", generation_config={"response_mime_type": "application/json"})
    
    with open(batches_file, "r", encoding="utf-8") as f:
        batches = json.load(f)
        
    print(f"Loaded {len(batches)} text batches from disk.")
    
    all_text = ""
    for batch in batches:
        all_text += batch['text'] + "\n\n"
        
    print(f"--> Prompting Gemini with all {len(batches)} batches in a single call...")
    all_claims = []
    try:
        full_prompt = PROMPT + "\n\nTEXT:\n" + all_text
        response = model.generate_content(full_prompt)
        
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
            r['source_batch'] = 'All'
            r['source_pages'] = 'Pages 3-20'
            
        all_claims.extend(result)
        print(f"    Found {len(result)} claims in the combined text.")
    except Exception as e:
        print(f"    [!] Error processing single batch call: {e}")
            
    # Save the output of this phase
    os.makedirs("data/claims", exist_ok=True)
    out_path = "data/claims/extracted_claims.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_claims, f, indent=2)
        
    print(f"\nFinished LLM Extraction phase. Total claims found: {len(all_claims)}")
    print(f"Successfully saved final structured artifacts to '{out_path}'")

if __name__ == "__main__":
    batches_file = "data/processed/batches.json"
    if not os.path.exists(batches_file):
        print(f"[!] Error: Could not find {batches_file}. You must run src/ingest.py first.")
        sys.exit(1)
        
    extract_claims(batches_file)
