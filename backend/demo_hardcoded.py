import os
import json
import google.generativeai as genai

# ---------------------------------------------------------
# SETUP
# ---------------------------------------------------------
CACHE_FILE = "cached_claims_v2.json"

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("[!] ERROR: GEMINI_API_KEY environment variable not found.")
    print("Please set your API key first:")
    print("  $env:GEMINI_API_KEY=\"your_key\"")
    exit(1)

genai.configure(api_key=api_key)
# Using gemini-3.5-flash as the fast, standard model
model = genai.GenerativeModel("models/gemini-3.5-flash", generation_config={"response_mime_type": "application/json"})

# ---------------------------------------------------------
# HARDCODED DEMO TEXT
# ---------------------------------------------------------
DEMO_TEXT = """
Infosys Sustainability and BRSR Core Performance Report - Fiscal 2024

During the fiscal year 2024, our sustainability initiatives achieved remarkable results across all global operations as we aggressively target our ESG Vision 2030 goals. Water stewardship remains a critical priority for our campuses in water-stressed regions. We rejuvenated five lakes in Bengaluru, enhancing the water holding capacity by about 5 billion liters compared to the baseline before rejuvenation. Consequently, our total municipal water withdrawal decreased from 2.5 million kiloliters in FY23 to 2.1 million kiloliters in FY24, representing a 16% reduction year-over-year. 

Energy efficiency and greenhouse gas mitigation saw equally impressive gains. Through aggressive retrofitting across our tier-2 city campuses, we replaced direct FCU units with chilled water units of air conditioning, which saved 1.1 lakh kWh of electricity. Furthermore, the implementation of our new radiant cooling system—which is about 50% more efficient than regular air-conditioning—contributed to massive campus-wide savings. Due to these combined efforts, we successfully reduced our scope 1 and 2 emissions by 60.07% over the BAU (Business As Usual) scenario. The retrofit project alone reduced our absolute emissions by 80.84 tCO2e compared to before the retrofit. 

On the waste management front, three of our India campuses in Bengaluru, Chennai, and Pune received True Zero Waste Platinum certifications from Green Business Certification Inc. We successfully recycled 99.5% of all e-waste generated, up from 94% in the previous reporting period. Finally, we are proud to announce that we have remained completely carbon neutral for 5 years in a row, from Fiscal 2020 through Fiscal 2024, demonstrating that economic growth can be entirely decoupled from environmental degradation.
"""

# ---------------------------------------------------------
# LLM EXTRACTION LOGIC
# ---------------------------------------------------------
def extract_claims_from_text(text):
    print("\n[Checking Cache...]")
    
    # 1. Check if we already have a cached result
    if os.path.exists(CACHE_FILE):
        print(f"--> Found cached results in '{CACHE_FILE}'! Skipping API call.")
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            cached_data = json.load(f)
            return cached_data
            
    print("--> No cache found. Calling Gemini API... (This might take a few seconds)")

    # 2. If no cache, call the API
    system_prompt = """
    You are an expert financial auditor. Your job is to extract quantitative sustainability claims from the provided text.
    Return a JSON array where each object matches this schema. Do not output anything else.
    [
      {
        "metric": string,
        "operation": "percentage_change" | "absolute_change" | "yoy_direction" | "value_equality",
        "stated_result": number/string,
        "unit": string,
        "period_current": string,
        "period_compare": string,
        "original_quote": string
      }
    ]
    """
    
    full_prompt = f"{system_prompt}\n\nText to analyze:\n{text}"
    
    try:
        response = model.generate_content(full_prompt)
        result_json = json.loads(response.text)
        
        # 3. Save the result to cache so we never pay for this exact extraction again
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(result_json, f, indent=2)
            
        print(f"--> API call successful! Saved results to '{CACHE_FILE}' for next time.")
        return result_json
        
    except Exception as e:
        print(f"Gemini API Error: {e}")
        return None

# ---------------------------------------------------------
# RUN
# ---------------------------------------------------------
if __name__ == "__main__":
    print("=== STARTING HARDCODED TEXT DEMO ===")
    print("\n[Input Text:]")
    print("-" * 50)
    print(DEMO_TEXT.strip())
    print("-" * 50)
    
    claims = extract_claims_from_text(DEMO_TEXT)
    
    if claims:
        print("\n[Extracted Structured Claims:]")
        print(json.dumps(claims, indent=2))
        
    print("\n=== DEMO COMPLETE ===")
    print("Tip: Run this script again, and watch how it loads instantly from the cache!")
