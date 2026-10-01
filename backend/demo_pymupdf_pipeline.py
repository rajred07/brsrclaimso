import os
import pymupdf as fitz  # PyMuPDF
import spacy
import json
import google.generativeai as genai

# ---------------------------------------------------------
# 0. GEMINI API SETUP
# ---------------------------------------------------------
# The user MUST set the GEMINI_API_KEY environment variable.
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("[!] ERROR: GEMINI_API_KEY environment variable not found.")
    print("Please get a free API key from https://aistudio.google.com/ and set it.")
    print("Run this in your terminal before running the script:")
    print("  $env:GEMINI_API_KEY=\"your_actual_api_key_here\"")
    exit(1)

genai.configure(api_key=api_key)
# Using gemini-3.5-flash because 1.5 is retired
model = genai.GenerativeModel("models/gemini-3.5-flash", generation_config={"response_mime_type": "application/json"})

# ---------------------------------------------------------
# 1. SETUP
# ---------------------------------------------------------
print("Loading SpaCy English model...")
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    print("SpaCy model 'en_core_web_sm' not found. You must run: python -m spacy download en_core_web_sm")
    exit(1)

# ---------------------------------------------------------
# 2. INGESTION (PDF -> Blocks)
# ---------------------------------------------------------
def ingest_pdf(pdf_path, start_page=0, end_page=None):
    """Reads a PDF and extracts text blocks, preserving page numbers."""
    print(f"Reading PDF: {pdf_path}...")
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        print(f"Error opening PDF: {e}")
        return []

    blocks_data = []
    end = end_page if end_page is not None else len(doc)
    
    for page_num in range(start_page, end):
        page = doc[page_num]
        blocks = page.get_text("blocks")
        for b in blocks:
            text = b[4].strip()
            if b[6] == 0 and len(text) > 20:
                blocks_data.append({
                    "page_num": page_num + 1,
                    "text": text.replace('\n', ' ')
                })
                
    print(f"Extracted {len(blocks_data)} text blocks from pages {start_page+1} to {end}.")
    return blocks_data

# ---------------------------------------------------------
# 3. CANDIDATE FILTER (Blocks -> Sentences)
# ---------------------------------------------------------
def filter_candidates(blocks_data):
    """Uses SpaCy to segment sentences and applies rule-based filtering."""
    print("Filtering candidates (seeking quantitative/directional claims)...")
    
    directional_keywords = [
        "increase", "decrease", "reduce", "grow", "drop", 
        "from", "to", "compared", "higher", "lower", "savings"
    ]
    
    candidates = []
    
    for block in blocks_data:
        doc = nlp(block["text"])
        for sent in doc.sents:
            sentence = sent.text.strip()
            
            has_quant = any(char.isdigit() for char in sentence) or '%' in sentence
            sentence_lower = sentence.lower()
            has_direction = any(kw in sentence_lower for kw in directional_keywords)
            
            if has_quant and has_direction:
                candidates.append({
                    "page_num": block["page_num"],
                    "sentence": sentence,
                    "context_block": block["text"]
                })
                
    print(f"Found {len(candidates)} candidate claims.")
    return candidates

# ---------------------------------------------------------
# 4. LLM EXTRACTION (Real Gemini API Call)
# ---------------------------------------------------------
def llm_extract_claims(candidates):
    """Sends the filtered sentences to Gemini API for structured extraction."""
    print("\n--- Sending candidates to Gemini API ---")
    
    system_prompt = """
    You are an expert financial auditor. Your job is to extract quantitative sustainability claims from the provided text.
    You MUST output a single valid JSON object exactly matching this schema. Do NOT wrap it in markdown block quotes.
    If the sentence is not a valid quantitative claim, output an empty JSON object: {}
    
    Schema:
    {
      "metric": string,
      "operation": "percentage_change" | "absolute_change" | "yoy_direction" | "value_equality",
      "stated_result": number/string,
      "unit": string,
      "period_current": string,
      "period_compare": string
    }
    """
    
    extracted_results = []
    
    for idx, cand in enumerate(candidates):
        print(f"\n[Prompting Gemini with Sentence {idx+1}]")
        print(f"Input: \"{cand['sentence']}\"")
        
        full_prompt = f"{system_prompt}\n\nSentence to analyze:\n{cand['sentence']}"
        
        try:
            response = model.generate_content(full_prompt)
            result_json = json.loads(response.text)
            
            # If Gemini found a claim and didn't return an empty object
            if result_json and "metric" in result_json:
                result_json["page_num"] = cand["page_num"]
                extracted_results.append(result_json)
                print("Gemini Structured Output:")
                print(json.dumps(result_json, indent=2))
            else:
                print("Gemini Output: No valid claim detected.")
                
        except Exception as e:
            print(f"Gemini API Error: {e}")
            print(f"Raw Response: {response.text if 'response' in locals() else 'None'}")
            
    return extracted_results

# ---------------------------------------------------------
# RUN DEMO
# ---------------------------------------------------------
import sys

if __name__ == "__main__":
    # If a PDF file is provided as a command-line argument, use it!
    if len(sys.argv) > 1:
        test_pdf = sys.argv[1]
    else:
        # Otherwise create a dummy PDF for testing
        test_pdf = "sample_report.pdf"
        if not os.path.exists(test_pdf):
            print("\n[!] No PDF found. Creating a fake PDF for the demo...")
            doc = fitz.open()
            page = doc.new_page()
            page.insert_text((50, 50), "During FY25, our total water consumption was reduced by 22% from 100 ML in FY24 to 78 ML in FY25. This was a great achievement.")
            page.insert_text((50, 100), "We also hired 500 new employees. The company is doing well.")
            doc.save(test_pdf)
    
    print(f"\n=== STARTING NEURO-SYMBOLIC PIPELINE (PYMUPDF + GEMINI) ===")
    CACHE_FILE = "cache_pymupdf.json"
    if os.path.exists(CACHE_FILE):
        print(f"\n[!] Found '{CACHE_FILE}'. Loading claims from cache to save API costs...")
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            claims = json.load(f)
    else:
        blocks = ingest_pdf(test_pdf)
        candidates = filter_candidates(blocks)
        claims = llm_extract_claims(candidates)
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(claims, f, indent=2)
        print(f"\n[!] Saved extraction results to '{CACHE_FILE}' for future runs.")
    print("\n=== PIPELINE COMPLETE ===")
