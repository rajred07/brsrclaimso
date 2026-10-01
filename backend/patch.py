import os, json

with open(r'C:\Users\jraj1\OneDrive\Desktop\xrbr\backend\src\verify_engine.py', 'r', encoding='utf-8') as f:
    code = f.read()

# Add imports
if 'import google.generativeai as genai' not in code:
    code = 'import google.generativeai as genai\nfrom dotenv import load_dotenv\n' + code

# Define the LLM mapping function
llm_func = '''
def generate_llm_mapping(con, unique_metrics):
    load_dotenv()
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        print('[!] ERROR: GEMINI_API_KEY environment variable not found.')
        return {}
    
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('models/gemini-3.5-flash', generation_config={'response_mime_type': 'application/json'})
    
    # Get all distinct canonical names from DuckDB
    try:
        db_metrics_res = con.execute("SELECT DISTINCT canonical_name FROM normalized_facts").fetchall()
        db_metrics = [r[0] for r in db_metrics_res]
    except Exception as e:
        print(f'Error fetching canonical names: {e}')
        return {}
        
    prompt = f"""
You are a semantic mapping engine.
Your task is to map a list of 'Extracted Claims' (from a sustainability PDF) to the closest matching 'SEBI XBRL Canonical Name' from the provided database taxonomy.

Database Taxonomy (Canonical Names):
{json.dumps(db_metrics, indent=2)}

Extracted Claims to Map:
{json.dumps(unique_metrics, indent=2)}

Output a valid JSON dictionary where:
- The key is the exact Extracted Claim string.
- The value is an array containing the exact matching Canonical Name string from the Database Taxonomy.
- If an Extracted Claim clearly maps to nothing, return an empty array for that key.
- Be very smart about acronyms and sustainability terms (e.g. 'surface_water' maps to 'Surface Water Withdrawal').
"""
    print(f'--> Calling Gemini to map {len(unique_metrics)} metrics to taxonomy...')
    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        if text.startswith('```json'): text = text[7:]
        if text.endswith('```'): text = text[:-3]
        return json.loads(text)
    except Exception as e:
        print(f'LLM mapping failed: {e}')
        return {}
'''

if 'def generate_llm_mapping' not in code:
    code = code.replace('def verify_claims():', llm_func + '\n\ndef verify_claims():')

# Modify verify_claims to use it
injection = '''
    # Generate dynamic semantic mapping via LLM
    unique_metrics = list(set(c.get('metric') for c in claims if c.get('metric')))
    dynamic_mapping = generate_llm_mapping(con, unique_metrics)
    print(f'Generated semantic mapping for {len(dynamic_mapping)} metrics.')
'''
if 'dynamic_mapping = generate_llm_mapping' not in code:
    code = code.replace('    verified = []\n    supported_count = 0', injection + '\n    verified = []\n    supported_count = 0')

# Modify the call inside the loop to use dynamic_mapping first
call_replace = '''
        # First check LLM dynamic mapping, then fallback to hardcoded
        db_metrics = dynamic_mapping.get(metric_name)
        if not db_metrics or (isinstance(db_metrics, list) and len(db_metrics) == 0):
            db_metrics = map_metric(metric_name)
'''
if 'db_metrics = dynamic_mapping.get(metric_name)' not in code:
    code = code.replace('        db_metrics = map_metric(metric_name)', call_replace)

with open(r'C:\Users\jraj1\OneDrive\Desktop\xrbr\backend\src\verify_engine.py', 'w', encoding='utf-8') as f:
    f.write(code)
print('Updated verify_engine.py successfully!')
