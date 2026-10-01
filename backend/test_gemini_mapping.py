import os
import json
from pathlib import Path
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv(Path(__file__).parent / ".env")

api_key = os.getenv("GEMINI_API_KEY")
print(f"Loaded GEMINI_API_KEY: {'Found' if api_key else 'Missing'}")

genai.configure(api_key=api_key)

xml_path = Path(__file__).parent / "data" / "filings" / "infosys--202425-7178" / "brsr_BRSR_1477079_03072025095250_WEB.xml"
print(f"Reading XML: {xml_path}")

with open(xml_path, 'r', encoding='utf-8') as f:
    soup = BeautifulSoup(f.read(), 'xml')

# Find all unique numerical concepts
concepts = {}
for tag in soup.find_all(True):
    if not tag.has_attr('contextRef'):
        continue
    val = tag.text.strip().replace(',', '')
    try:
        fval = float(val)
    except ValueError:
        continue
    
    concept_name = tag.name.split(':')[-1]
    unit_ref = tag.get('unitRef', '')
    if concept_name not in concepts:
        concepts[concept_name] = {
            "sample_value": fval,
            "sample_unit": unit_ref,
            "count": 1
        }
    else:
        concepts[concept_name]["count"] += 1

print(f"Found {len(concepts)} unique numerical concepts.")

# Filter to concepts that matter for ESG / BRSR
# e.g., Energy, Water, Emission, Waste, Employee, Worker, Turnover, Revenue, CSR, etc.
candidate_concepts = []
keywords = ['energy', 'water', 'emission', 'scope', 'waste', 'employee', 'worker', 'turnover', 'revenue', 'csr', 'board', 'safety', 'pat', 'profit']
for name, data in concepts.items():
    if any(k in name.lower() for k in keywords):
        candidate_concepts.append({"concept": name, **data})

print(f"Filtered {len(candidate_concepts)} ESG candidate concepts for Gemini mapping.")

# Now prompt Gemini to map them
prompt = f"""You are an expert ESG and SEBI BRSR XBRL financial data engineer.
Below is a list of raw XBRL concepts extracted from an Indian corporate BRSR XML report (Infosys 2024-25).
For each concept, provide:
1. "canonical_name": A clear, professional, human-readable ESG metric title (e.g. "Total Energy Consumption", "Scope 1 GHG Emissions", "Total Water Withdrawal", "Voluntary Employee Turnover Rate").
2. "category": Must be one of: ["Energy", "Emissions", "Water", "Waste", "Workforce", "Governance", "Social", "Financial"].
3. "standard_unit": Standard unit of measure (e.g. "GJ", "tCO2e", "kL", "Tonne", "count", "%", "INR", "ratio").

Raw concepts to map:
{json.dumps([c['concept'] for c in candidate_concepts[:60]], indent=2)}

Return ONLY a valid JSON object mapping each raw concept name to:
{{
  "canonical_name": "...",
  "category": "...",
  "standard_unit": "..."
}}
"""

model = genai.GenerativeModel("gemini-2.5-flash")
response = model.generate_content(prompt)
print("Gemini response received:")
print(response.text[:1000])
