import os, json, sys, time
import pymupdf
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PDF_PATH = r"c:\Users\jraj1\OneDrive\Desktop\xrbr\infosys2526.pdf"

# Only retry the pages that FAILED (503 errors) in the first run.
# Pages that already worked (28, 29, 71, 79) are excluded.
PAGES    = "17,26,30,31,70,85,143,144,145,160,173,174,175,176,177,178,179,180,181"
MODEL    = "gemini-3.5-flash-lite"   # less congested than gemini-3.5-flash
SCALE    = 2.0
RPM      = 10
MIN_INT  = 60.0 / RPM
MAX_CHARS = 12000

def expand_pages(spec):
    pages = []
    for p in spec.split(","):
        p = p.strip()
        if "-" in p:
            a, b = p.split("-")
            pages.extend(range(int(a), int(b)+1))
        else:
            pages.append(int(p))
    return sorted(set(pages))

SYSTEM = """You are a meticulous ESG analyst. Extract every TESTABLE QUANTITATIVE CLAIM from the page.
Return ONLY valid JSON:
{
  "page_section": "<what this page covers>",
  "claims": [{
    "metric": "snake_case",
    "metric_label": "label as printed",
    "qualifier": "segment or null",
    "operation": "value_equality|percentage_change|absolute_change|yoy_direction",
    "asserted_value": 0.0,
    "value_as_printed": "as printed",
    "unit": "%, GJ, kL, tCO2e, MT, kg, count, INR, INR cr, INR lakh, etc.",
    "comparator": "exact|approx|at_least|at_most",
    "current_period": "FY 2025-26",
    "prior_period": "FY 2024-25 or null",
    "boundary": "consolidated|standalone|unspecified",
    "is_target": false,
    "source_passage": "exact short quote from page",
    "source_type": "prose|table|infographic",
    "confidence": "high|medium|low"
  }]
}
Rules: Indian grouping 1,36,592=136592. Fiscal: FY 2025-26. Skip page numbers, headers, standards names.
Ratios stored as 0.97 are really 97% - extract as 97 with unit %. This is Infosys Integrated Annual Report FY 2025-26."""

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
last_call = 0.0

def call_gemini(img_bytes, text_layer, pg_num):
    global last_call
    gap = MIN_INT - (time.time() - last_call)
    if gap > 0:
        print(f"   (rate-limit: waiting {gap:.1f}s)", flush=True)
        time.sleep(gap)
    last_call = time.time()

    ctx = (
        f"DOCUMENT: Infosys Integrated Annual Report FY 2025-26\n"
        f"PDF Page: {pg_num} | Current Year: FY 2025-26 | Prior Year: FY 2024-25\n"
        f"TEXT LAYER:\n<<<\n{text_layer[:MAX_CHARS]}\n>>>\nExtract all claims from the image."
    )

    for attempt in range(3):
        try:
            resp = client.models.generate_content(
                model=MODEL,
                contents=[types.Part.from_bytes(data=img_bytes, mime_type="image/png"), ctx],
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM,
                    response_mime_type="application/json",
                    temperature=0.0,
                    max_output_tokens=8192,
                )
            )
            return json.loads(resp.text or "{}")
        except Exception as e:
            s = str(e)
            if any(k in s for k in ("429", "503", "UNAVAILABLE", "RESOURCE_EXHAUSTED")):
                w = 10 * (2**attempt)
                print(f"   [RETRY {attempt+1}/3] waiting {w}s...", flush=True)
                time.sleep(w)
            else:
                print(f"   [ERROR] {s[:120]}", flush=True)
                return {}
    return {}

doc = pymupdf.open(PDF_PATH)
page_list = expand_pages(PAGES)
all_claims = []

print(f"\n{'='*65}")
print(f"VeriBRSR PREVIEW — Infosys FY 2025-26 | {len(page_list)} pages")
print(f"Model: {MODEL}  |  NOTE: PREVIEW ONLY — nothing is saved")
print(f"{'='*65}\n")

for i, pg_num in enumerate(page_list):
    print(f"[{i+1}/{len(page_list)}] Processing page {pg_num}...", flush=True)
    page = doc[pg_num - 1]
    pix = page.get_pixmap(matrix=pymupdf.Matrix(SCALE, SCALE))
    result = call_gemini(pix.tobytes("png"), page.get_text("text").strip(), pg_num)
    section = result.get("page_section", "?")
    claims  = result.get("claims", [])
    print(f"   Section : {section}")
    print(f"   Claims  : {len(claims)}")
    for j, c in enumerate(claims):
        label   = c.get("metric_label") or c.get("metric", "?")
        qual    = c.get("qualifier") or ""
        val     = c.get("asserted_value", "?")
        unit    = c.get("unit", "")
        period  = c.get("current_period", "")
        op      = c.get("operation", "")
        conf    = c.get("confidence", "")
        passage = (c.get("source_passage") or "")[:80]
        tgt     = " [TARGET]" if c.get("is_target") else ""
        q_str   = f" [{qual}]" if qual else ""
        print(f"   {j+1:>3}. {label}{q_str} = {val} {unit} | {period} | {op} | {conf}{tgt}")
        print(f"        \"{passage}\"")
        c["_page"] = pg_num
        c["_section"] = section
        all_claims.append(c)
    print()

doc.close()
print(f"\n{'='*65}")
print(f"TOTAL CLAIMS: {len(all_claims)} across {len(page_list)} pages")
print(f"PREVIEW ONLY — no file was written.")
print(f"{'='*65}")
