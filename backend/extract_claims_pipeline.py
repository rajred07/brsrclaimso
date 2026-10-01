"""
VeriBRSR: PDF Claim Extraction Pipeline
=========================================
Sends every page as an image to Gemini Vision for structured claim extraction.
Uses gemini-2.0-flash (FREE tier: 15 RPM, 1500 RPD, 1M tokens/min).

NOTE: This script uses only ASCII characters for Windows terminal compatibility.

Cost Analysis:
- Model: gemini-2.0-flash (Free tier available)
- Each page image ≈ 258 tokens (standard resolution)
- Prompt ≈ 500 tokens per call
- Output ≈ 1000 tokens per page
- Total per 11-page PDF: ~19,338 tokens (well within free 1M/min limit)
- API Calls: 11 (one per page) — within free 15 RPM limit
- Cost on FREE tier: $0.00
- Cost on PAID tier: ~$0.003 per document (essentially free)

Rate Limits (Free Tier - gemini-2.0-flash):
- 15 Requests Per Minute (RPM)
- 1,500 Requests Per Day (RPD)  
- 1,000,000 Tokens Per Minute (TPM)
"""

import os
import sys
import json
import time
import re
import pymupdf  # PyMuPDF
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field, asdict
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Ensure Windows terminal doesn't crash on UTF-8 characters
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ============================================================
# CONFIGURATION
# ============================================================

# Gemini model to use
# gemini-2.5-flash: FREE tier = 10 RPM, 500 RPD
GEMINI_MODEL = "gemini-2.5-flash"

# Rate limit safety: wait between API calls (seconds)
# 10 RPM = 1 call per 6 seconds, using 6.5s buffer for safety
RATE_LIMIT_DELAY = 6.5

# Image rendering resolution (2x for better OCR quality)
RENDER_SCALE = 2

# Core ESG target pages for Infosys ESG Report 2021-22
# Contains: GHG Scope 1/2/3, Renewable Energy, Water, Waste, Headcount, Diversity
CORE_ESG_PAGES = [4, 6, 12, 13, 14, 15, 17, 22, 26, 27, 28, 29, 31, 37]

# ============================================================
# DATA MODELS
# ============================================================

@dataclass
class ExtractedClaim:
    """Formal claim tuple c = (m, o, r, u, t1, t0, b, s) from paper Eq. (1)"""
    claim_id: str
    metric: str                    # e.g., "energy_consumption", "scope1_emissions"
    operation: str                 # "value_equality", "yoy_direction", "absolute_change", "percentage_change"
    asserted_value: float          # Numerical value. Decreases are negative.
    unit: str                      # "ML", "kL", "GJ", "MWh", "MT", "tCO2e", "%", "count", "INR cr"
    current_period: str            # "FY 2023-24"
    prior_period: Optional[str]    # "FY 2022-23" or None
    boundary: str                  # "standalone", "consolidated", "unspecified"
    source_passage: str            # Verbatim text from document
    source_type: str               # "prose", "table", "infographic"
    page_number: int
    confidence: str                # "high", "medium", "low"

@dataclass
class ExtractionResult:
    """Complete extraction output for a document"""
    company_name: str
    reporting_year: str
    pdf_path: str
    total_pages: int
    pages_processed: int
    total_claims: int
    api_calls_made: int
    estimated_tokens_used: int
    estimated_cost_usd: float
    claims: list = field(default_factory=list)
    page_summaries: list = field(default_factory=list)


# ============================================================
# GEMINI VISION EXTRACTION PROMPT
# ============================================================

EXTRACTION_PROMPT = """You are an expert ESG and financial auditor analyzing a page from an Indian BRSR/ESG annual report (Infosys ESG Report 2021-22).

TASK: Extract ALL testable quantitative claims from this page image.

For each number, percentage, or quantitative statement you find, extract it as a structured claim.

OUTPUT FORMAT: Return a JSON object with this exact structure:
{
  "page_has_claims": true/false,
  "page_section": "section name (e.g., Environment, Climate change, Energy efficiency, Water, Waste, Social, Human Capital, Governance)",
  "claims": [
    {
      "metric": "normalized metric name (e.g., energy_consumption, scope1_emissions, scope2_emissions, scope3_emissions, renewable_energy_consumption, renewable_energy_share, water_consumption, wastewater_recycled, employee_headcount, female_representation, training_hours, csr_spends)",
      "metric_label": "exact human-readable label from the table/prose, e.g. 'Total Scope 1 GHG Emissions'",
      "operation": "value_equality | yoy_direction | absolute_change | percentage_change",
      "asserted_value": 8965.0,
      "unit": "GJ | kL | ML | MWh | kWh | tCO2e | MT | % | count | INR cr | INR lakh | sq.ft.",
      "current_period": "FY 2021-22",
      "prior_period": "FY 2020-21 or null",
      "boundary": "standalone | consolidated | water_stressed_areas | india_operations | unspecified",
      "source_passage": "exact text or label from the page",
      "source_type": "prose | table | infographic",
      "confidence": "high | medium | low"
    }
  ]
}

STRICT RULES:
1. SIGN CONVENTION: Reductions and decreases produce NEGATIVE asserted_value.
   "decreased by 2%" -> asserted_value = -2.0
   "reduced from 100 to 78" -> for absolute_change: asserted_value = -22.0

2. SPLIT COMPOUND CLAIMS: If a sentence has both a percentage and absolute figure,
   produce TWO separate claims (one percentage_change, one value_equality or absolute_change).

3. INFOGRAPHIC CALLOUTS: Numbers inside colored boxes, badges, icons, or performance
   highlight sections ARE claims. Pair each number with its label.
   Example: "67.52% | Of electricity from renewable sources" -> 
   metric="renewable_energy_share", asserted_value=67.52, unit="%"

4. TABLE DATA: Each table row with current and prior year values generates:
   - A value_equality claim for the current year value
   - If YoY growth % is shown, a percentage_change claim

5. INDIAN NUMBER FORMAT: "1,28,933" = 128933 (Indian lakhs format), 
   "2,64,000+" = 264000, "`" symbol = INR (rupees), "cr" = crore = 10^7

6. BOUNDARY — CRITICAL RULES:
   a. Use "consolidated" for global/worldwide totals (the default for BRSR mandatory disclosures).
   b. Use "india_operations" if the label or context clearly says "India operations only".
   c. Use "water_stressed_areas" if the table heading says "water-stressed areas" or 
      "facilities in areas of water stress" — these are LEADERSHIP INDICATOR sub-tables, NOT the main totals.
   d. NEVER mark water-stressed sub-table values as "consolidated".

7. SKIP DASH/NULL ROWS — CRITICAL:
   If a table cell contains ONLY "—", "-", "Nil", "N/A", "Not applicable", or is blank,
   DO NOT extract it as a claim with asserted_value=0.
   Simply skip that row entirely. A dash means "not applicable", not zero.

8. MANDATORY BRSR TABLE vs LEADERSHIP INDICATOR TABLE:
   BRSR mandatory tables (Principles 1-9) report GLOBAL consolidated totals.
   Leadership Indicator sub-tables (often titled "in areas of water stress") report SUBSETS. 
   When BOTH exist on the same page for the same metric:
   - Extract the MANDATORY BRSR total as boundary="consolidated"
   - Extract the leadership sub-table value ONLY if clearly labeled, with boundary="water_stressed_areas"
   - DO NOT mix them up.

9. SCOPE 2 EMISSIONS — CRITICAL:
   BRSR reports Scope 2 in TWO methods:
   - "Market-based" (using energy attribute certificates) -> metric="scope2_emissions_market_based"
   - "Location-based" (using grid emission factors) -> metric="scope2_emissions_location_based"
   Extract BOTH as separate claims with distinct metric names.

10. DO NOT VERIFY or CALCULATE anything. Only extract what the page states.

11. If the page has NO quantitative claims (e.g., it's a cover page or section divider),
   set page_has_claims to false and return empty claims array.

12. For metric names, normalize to snake_case.

13. ALWAYS include metric_label field with the exact human-readable label from the document.
"""


# ============================================================
# CORE PIPELINE
# ============================================================

def extract_claims_from_pdf(pdf_path: str, api_key: str, target_pages: Optional[list] = None, output_path: Optional[str] = None) -> ExtractionResult:
    """
    Main pipeline: Opens PDF, renders each target page as image, 
    sends to Gemini Vision, collects structured claims with live progress.
    """
    from google import genai
    from google.genai import types
    
    # Initialize Gemini client
    client = genai.Client(api_key=api_key)
    
    # Open PDF
    doc = pymupdf.open(pdf_path)
    total_doc_pages = doc.page_count
    
    # Determine pages to process
    if target_pages:
        pages_to_process = [p for p in target_pages if 1 <= p <= total_doc_pages]
    else:
        pages_to_process = list(range(1, total_doc_pages + 1))
        
    num_pages = len(pages_to_process)
    
    print(f"=" * 60, flush=True)
    print(f"VeriBRSR Claim Extraction Pipeline", flush=True)
    print(f"=" * 60, flush=True)
    print(f"PDF: {Path(pdf_path).name}", flush=True)
    print(f"Target Pages ({num_pages}): {pages_to_process}", flush=True)
    print(f"Model: {GEMINI_MODEL}", flush=True)
    print(f"Rate Limit Delay: {RATE_LIMIT_DELAY}s between calls", flush=True)
    print(f"Estimated Time: ~{num_pages * (RATE_LIMIT_DELAY + 2.5):.0f} seconds", flush=True)
    print(f"Estimated Cost: $0.00 (FREE tier)", flush=True)
    print(f"=" * 60, flush=True)
    
    all_claims = []
    page_summaries = []
    total_tokens_estimate = 0
    api_calls = 0
    claim_counter = 0
    
    for idx, page_num in enumerate(pages_to_process):
        page = doc[page_num - 1]
        
        print(f"\n[{idx+1}/{num_pages}] Processing Page {page_num}...", end=" ", flush=True)
        
        # Fast local filter: if page has fewer than 2 numbers and short text, skip without API call
        page_text = page.get_text("text").strip()
        num_count = len(re.findall(r'\d+', page_text))
        if num_count < 2 and len(page_text) < 150:
            print("[SKIP] Non-quantitative page (Cover/Divider)")
            page_summaries.append({
                "page": page_num,
                "section": "Divider/Cover",
                "claims_found": 0,
                "has_claims": False
            })
            continue
            
        # Render page as PNG image at 2x resolution
        pix = page.get_pixmap(matrix=pymupdf.Matrix(RENDER_SCALE, RENDER_SCALE))
        img_bytes = pix.tobytes("png")
        img_size_kb = len(img_bytes) / 1024
        
        # Estimate tokens: ~258 tokens per image (standard) + prompt + output
        est_input_tokens = 258 + 500  # image + prompt
        est_output_tokens = 1000     # estimated response
        total_tokens_estimate += est_input_tokens + est_output_tokens
        
        # Rate limit: wait before API call (skip for first call)
        if api_calls > 0:
            time.sleep(RATE_LIMIT_DELAY)
        
        # Call Gemini Vision with retry logic
        max_retries = 3
        response_text = None
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=[
                        types.Part.from_bytes(data=img_bytes, mime_type="image/png"),
                        EXTRACTION_PROMPT
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.1
                    )
                )
                response_text = response.text
                api_calls += 1
                break
            except Exception as e:
                err_str = str(e)
                if ("429" in err_str or "RESOURCE_EXHAUSTED" in err_str) and attempt < max_retries - 1:
                    backoff = (attempt + 1) * 8
                    print(f"[RATE LIMIT] Waiting {backoff}s before retry...", end=" ")
                    time.sleep(backoff)
                elif attempt == max_retries - 1:
                    print(f"[ERROR] Failed after {max_retries} attempts: {err_str[:80]}")
                    page_summaries.append({
                        "page": page_num,
                        "section": "Error",
                        "claims_found": 0,
                        "has_claims": False,
                        "error": err_str
                    })
                    break
                else:
                    print(f"[RETRY] Transient error, retrying in 4s...", end=" ")
                    time.sleep(4)
        
        if not response_text:
            continue
            
        try:
            # Clean and parse JSON response
            clean_text = response_text.strip()
            if clean_text.startswith("```json"):
                clean_text = clean_text[7:]
            elif clean_text.startswith("```"):
                clean_text = clean_text[3:]
            if clean_text.endswith("```"):
                clean_text = clean_text[:-3]
            clean_text = clean_text.strip()
            
            page_data = json.loads(clean_text)
            page_claims = page_data.get("claims", [])
            page_section = page_data.get("page_section", "Unknown")
            has_claims = page_data.get("page_has_claims", len(page_claims) > 0)
            
            # Convert to ExtractedClaim objects
            for claim_data in page_claims:
                claim_counter += 1
                claim = ExtractedClaim(
                    claim_id=f"CLM-P{page_num}-{claim_counter:03d}",
                    metric=claim_data.get("metric", "unknown"),
                    operation=claim_data.get("operation", "value_equality"),
                    asserted_value=float(claim_data.get("asserted_value", 0)),
                    unit=claim_data.get("unit", ""),
                    current_period=claim_data.get("current_period", ""),
                    prior_period=claim_data.get("prior_period"),
                    boundary=claim_data.get("boundary", "unspecified"),
                    source_passage=claim_data.get("source_passage", ""),
                    source_type=claim_data.get("source_type", "infographic"),
                    page_number=page_num,
                    confidence=claim_data.get("confidence", "medium")
                )
                all_claims.append(claim)
            
            status = f"[FOUND] {len(page_claims)} claims" if has_claims else "[EMPTY] No claims"
            print(f"{status} [{page_section}] ({img_size_kb:.0f}KB)", flush=True)
            
            page_summaries.append({
                "page": page_num,
                "section": page_section,
                "claims_found": len(page_claims),
                "has_claims": has_claims
            })
            
            # Incremental save after each page so data is never lost
            if output_path:
                interim_res = ExtractionResult(
                    company_name="Infosys Limited",
                    reporting_year="FY 2021-22",
                    pdf_path=str(pdf_path),
                    total_pages=total_doc_pages,
                    pages_processed=api_calls,
                    total_claims=len(all_claims),
                    api_calls_made=api_calls,
                    estimated_tokens_used=total_tokens_estimate,
                    estimated_cost_usd=0.0,
                    claims=[asdict(c) for c in all_claims],
                    page_summaries=page_summaries
                )
                save_results(interim_res, output_path, verbose=False)
            
        except Exception as e:
            print(f"[PARSE ERROR] {str(e)[:80]}", flush=True)
            page_summaries.append({
                "page": page_num,
                "section": "Parse Error",
                "claims_found": 0,
                "has_claims": False,
                "error": str(e)
            })
    
    doc.close()
    
    # Calculate cost estimate
    # Free tier: $0.00
    # Paid tier: $0.075/1M input + $0.30/1M output (gemini-2.0-flash)
    paid_cost = (total_tokens_estimate * 0.075 / 1_000_000) + (est_output_tokens * total_pages * 0.30 / 1_000_000)
    
    result = ExtractionResult(
        company_name="Infosys Limited",
        reporting_year="FY 2021-22",
        pdf_path=str(pdf_path),
        total_pages=total_pages,
        pages_processed=api_calls,
        total_claims=len(all_claims),
        api_calls_made=api_calls,
        estimated_tokens_used=total_tokens_estimate,
        estimated_cost_usd=paid_cost,
        claims=[asdict(c) for c in all_claims],
        page_summaries=page_summaries
    )
    
    # Print summary
    print(f"\n{'=' * 60}")
    print(f"EXTRACTION COMPLETE")
    print(f"{'=' * 60}")
    print(f"Total Claims Extracted: {len(all_claims)}")
    print(f"API Calls Made: {api_calls}")
    print(f"Estimated Tokens Used: {total_tokens_estimate:,}")
    print(f"Cost (Free Tier): $0.00")
    print(f"Cost (Paid Tier): ${paid_cost:.4f}")
    print(f"{'=' * 60}")
    
    # Print claims by page
    print(f"\nClaims by Page:")
    for ps in page_summaries:
        marker = "[+]" if ps["has_claims"] else "[-]"
        print(f"  {marker} Page {ps['page']}: {ps['claims_found']} claims [{ps['section']}]")
    
    return result


def save_results(result: ExtractionResult, output_path: str, verbose: bool = True):
    """Save extraction results to JSON file."""
    output = {
        "metadata": {
            "company": result.company_name,
            "reporting_year": result.reporting_year,
            "pdf": result.pdf_path,
            "total_pages": result.total_pages,
            "pages_processed": result.pages_processed,
            "total_claims": result.total_claims,
            "api_calls": result.api_calls_made,
            "tokens_used": result.estimated_tokens_used,
            "cost_usd": result.estimated_cost_usd,
            "model": GEMINI_MODEL
        },
        "page_summaries": result.page_summaries,
        "claims": result.claims
    }
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    if verbose:
        print(f"\n[SAVED] Results saved to: {output_path}", flush=True)


# ============================================================
# MAIN ENTRY POINT
# ============================================================

if __name__ == "__main__":
    # Paths
    pdf_path = r"c:\Users\jraj1\OneDrive\Desktop\xrbr\infosys-esg-report-2021-22.pdf"
    output_path = r"c:\Users\jraj1\OneDrive\Desktop\xrbr\backend\data\claims\extracted_claims.json"
    
    # API Key
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: Set GEMINI_API_KEY in .env file", flush=True)
        sys.exit(1)
    
    print(f"\n[KEY] API Key: {api_key[:10]}...{api_key[-4:]}", flush=True)
    
    # Run extraction on core 14 ESG pages (Scope 1/2/3, Energy, Water, Waste, Headcount)
    result = extract_claims_from_pdf(
        pdf_path=pdf_path, 
        api_key=api_key, 
        target_pages=CORE_ESG_PAGES,
        output_path=output_path
    )
    
    # Final save
    save_results(result, output_path, verbose=True)
    
    # Print sample claims
    print(f"\n[CLAIMS] Sample Extracted Claims (first 5):")
    print("-" * 80)
    for claim in result.claims[:5]:
        print(f"  [{claim['claim_id']}] {claim['metric']}")
        print(f"    Operation: {claim['operation']}")
        print(f"    Value: {claim['asserted_value']} {claim['unit']}")
        print(f"    Period: {claim['current_period']}" + 
              (f" vs {claim['prior_period']}" if claim['prior_period'] else ""))
        print(f"    Boundary: {claim['boundary']}")
        print(f"    Source: \"{claim['source_passage'][:80]}...\"")
        print(f"    Confidence: {claim['confidence']}")
        print()

