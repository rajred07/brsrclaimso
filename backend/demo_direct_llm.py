import os
import json
import time
import google.generativeai as genai

# ---------------------------------------------------------
# GEMINI API SETUP
# ---------------------------------------------------------
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

def direct_pdf_to_llm(pdf_path):
    print(f"\n=== STARTING DIRECT-TO-LLM PIPELINE ===")
    print(f"Target PDF: {pdf_path}")
    
    if not os.path.exists(pdf_path):
         print("[!] No PDF found. Please provide a valid PDF file.")
         return
         
    file_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
    print(f"File size: {file_size_mb:.2f} MB")
    
    CACHE_FILE = "cache_direct_llm.json"
    if os.path.exists(CACHE_FILE):
        print(f"\n[!] Found '{CACHE_FILE}'. Loading claims from cache to save API costs...")
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            result_json = json.load(f)
            print("Gemini Structured Output (CACHED):")
            print(json.dumps(result_json, indent=2))
        print("\n=== PIPELINE COMPLETE ===")
        return
        
    # 1. Upload the PDF file to Gemini's servers
    print("\n[Uploading PDF to Gemini File API...]")
    try:
        uploaded_file = genai.upload_file(path=pdf_path)
        print(f"Uploaded file '{uploaded_file.display_name}' as: {uploaded_file.uri}")
        
        # Wait a moment for processing
        print("Waiting for file to process...")
        while uploaded_file.state.name == "PROCESSING":
            time.sleep(2)
            uploaded_file = genai.get_file(uploaded_file.name)
            
    except Exception as e:
        print(f"Error uploading file: {e}")
        return

    # 2. Build the Prompt
    prompt = """
    I have attached a company's Annual Report PDF.
    
    Your task is to act as an expert sustainability auditor. Read through the ENTIRE document and find ALL derived quantitative claims regarding Water, Energy, and Emissions.
    
    A derived quantitative claim is one that compares two numbers, states a percentage change, or shows year-over-year direction (e.g., "reduced by 20%", "decreased from 100 to 80").
    
    Return a JSON array where each object matches this schema. Do not output anything else.
    [
      {
        "metric": string,
        "operation": "percentage_change" | "absolute_change" | "yoy_direction" | "value_equality",
        "stated_result": number/string,
        "unit": string,
        "period_current": string,
        "period_compare": string,
        "page_num": integer,
        "original_quote": string
      }
    ]
    """
    
    print("\n[Prompting Gemini with the PDF File...]")
    
    # 3. Real API Call
    try:
        response = model.generate_content([prompt, uploaded_file])
        print("Gemini Structured Output:")
        # Pretty print the JSON returned
        result_json = json.loads(response.text)
        
        # Save to cache!
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(result_json, f, indent=2)
            print(f"\n[!] Saved extraction results to '{CACHE_FILE}' for future runs.")
            
        print(json.dumps(result_json, indent=2))
        
    except Exception as e:
        print(f"Gemini API Error: {e}")
        print(f"Raw Response: {response.text if 'response' in locals() else 'None'}")
        
    finally:
        # Clean up the uploaded file to save space
        print(f"\n[Cleaning up uploaded file: {uploaded_file.name}]")
        genai.delete_file(uploaded_file.name)

    print("\n=== PIPELINE COMPLETE ===")

import sys

if __name__ == "__main__":
    # If a PDF file is provided as a command-line argument, use it!
    if len(sys.argv) > 1:
        test_pdf = sys.argv[1]
    else:
        # Otherwise create a dummy PDF for testing
        import fitz 
        test_pdf = "sample_report.pdf"
        if not os.path.exists(test_pdf):
            print("\n[!] No PDF found. Creating a fake PDF for the demo...")
            doc = fitz.open()
            page = doc.new_page()
            page.insert_text((50, 50), "During FY25, our total water consumption was reduced by 22% from 100 ML in FY24 to 78 ML in FY25. This was a great achievement.")
            doc.save(test_pdf)
        
    direct_pdf_to_llm(test_pdf)
