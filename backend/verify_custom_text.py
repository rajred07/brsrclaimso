"""
VeriBRSR: Interactive Custom Text Verification Pipeline
======================================================
Allows any user to paste or input ESG prose claims.
Pipeline:
  1. Input Prose Text (from CLI argument, stdin, or interactive prompt)
  2. Gemini 2.5 Flash extracts testable quantitative claims
  3. Queries DuckDB (data/parsed/brsr_facts.duckdb) for ground-truth XBRL facts
  4. Deterministic Neuro-Symbolic Verification Engine computes math traces
  5. Outputs verification verdict (SUPPORTED / INCONSISTENT / INSUFFICIENT_EVIDENCE)
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

# Ensure Windows terminal doesn't crash on UTF-8 characters
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

load_dotenv()

# ============================================================
# DUCKDB CONFIGURATION & FACT RETRIEVAL
# ============================================================

DUCKDB_PATH = Path(__file__).parent / "data" / "parsed" / "brsr_facts.duckdb"

# Canonical Metric Mapping dictionary
METRIC_MAPPING = {
    # Emissions
    "scope1_emissions": ["Scope1Emissions"],
    "scope_1_emissions": ["Scope1Emissions"],
    "scope1": ["Scope1Emissions"],
    "scope2_emissions": ["Scope2Emissions"],
    "scope_2_emissions": ["Scope2Emissions"],
    "scope2": ["Scope2Emissions"],
    "scope1_and_scope2_emissions": ["Scope1Emissions", "Scope2Emissions"],
    "scope_1_and_2_emissions": ["Scope1Emissions", "Scope2Emissions"],
    "ghg_emissions": ["Scope1Emissions", "Scope2Emissions"],
    
    # Energy
    "energy_consumption": ["EnergyConsumptionTotal"],
    "total_energy_consumption": ["EnergyConsumptionTotal"],
    "power_consumption": ["EnergyConsumptionTotal"],
    "renewable_energy_consumption": ["EnergyConsumptionRenewable"],
    "renewable_energy": ["EnergyConsumptionRenewable"],
    "non_renewable_energy_consumption": ["EnergyConsumptionNonRenewable"],
    
    # Water
    "water_consumption": ["WaterConsumptionTotal"],
    "total_water_consumption": ["WaterConsumptionTotal"],
    "municipal_water_withdrawal": ["WaterConsumptionTotal"],
    "water_withdrawal": ["WaterConsumptionTotal"],
    "water_holding_capacity": ["WaterHoldingCapacity"],
}

PERIOD_MAPPING = {
    "FY22": "2021-04-01 to 2022-03-31",
    "FY 2021-22": "2021-04-01 to 2022-03-31",
    "FY2022": "2021-04-01 to 2022-03-31",
    "2021-22": "2021-04-01 to 2022-03-31",
    "2022": "2021-04-01 to 2022-03-31",
    
    "FY21": "2020-04-01 to 2021-03-31",
    "FY 2020-21": "2020-04-01 to 2021-03-31",
    "FY2021": "2020-04-01 to 2021-03-31",
    "2020-21": "2020-04-01 to 2021-03-31",
    "2021": "2020-04-01 to 2021-03-31",

    "FY24": "2023-04-01 to 2024-03-31",
    "FY23": "2022-04-01 to 2023-03-31",
}


def query_duckdb_fact(con, metric_name: str, period_key: str) -> Optional[Dict[str, Any]]:
    """Query normalized_facts table in DuckDB for canonical fact value."""
    canonical_candidates = METRIC_MAPPING.get(metric_name.lower(), [metric_name])
    mapped_period = PERIOD_MAPPING.get(period_key, period_key)

    for cand in canonical_candidates:
        # 1. Exact match on period
        q = "SELECT canonical_name, period, value, unit FROM normalized_facts WHERE canonical_name = ? AND period = ? LIMIT 1"
        res = con.execute(q, [cand, mapped_period]).fetchone()
        if res:
            return {"canonical_name": res[0], "period": res[1], "value": float(res[2]), "unit": res[3]}

        # 2. Substring match on period (e.g. '2022' in '2021-04-01 to 2022-03-31')
        q_like = "SELECT canonical_name, period, value, unit FROM normalized_facts WHERE canonical_name = ? AND period LIKE ? LIMIT 1"
        short_year = period_key.replace("FY", "").strip()
        res = con.execute(q_like, [cand, f"%{short_year}%"]).fetchone()
        if res:
            return {"canonical_name": res[0], "period": res[1], "value": float(res[2]), "unit": res[3]}

    return None


# ============================================================
# GEMINI EXTRACTION PROMPT
# ============================================================

EXTRACT_PROMPT = """You are a senior ESG and financial auditor for the VeriBRSR neuro-symbolic engine.
Analyze the following input text and extract all testable quantitative ESG claims.

INPUT TEXT:
\"\"\"{input_text}\"\"\"

For each quantitative statement (such as percentage change, absolute change, or reported numerical value), extract:
- metric: snake_case canonical name (e.g., energy_consumption, scope1_emissions, scope2_emissions, water_consumption, renewable_energy_consumption, waste_recycled)
- operation: "percentage_change" | "absolute_change" | "value_equality"
- stated_result: the claimed numeric value (e.g., 16, 60.07, 8965.0, 1.1). Numbers only, do not include units.
- unit: standard unit (e.g., "%", "kL", "GJ", "tCO2e", "kWh")
- period_current: reporting year (e.g., "FY22", "FY24")
- period_compare: prior/comparison period (e.g., "FY21", "FY23", "baseline", "BAU scenario")
- original_quote: verbatim substring from the input text

OUTPUT: Return ONLY valid JSON matching this schema:
{
  "claims": [
    {
      "metric": "energy_consumption",
      "operation": "percentage_change",
      "stated_result": 3.15,
      "unit": "%",
      "period_current": "FY22",
      "period_compare": "FY21",
      "original_quote": "..."
    }
  ]
}
"""


def extract_claims_with_gemini(text: str, api_key: str) -> List[Dict[str, Any]]:
    """Use Gemini 2.5 Flash / 1.5 Flash to extract structured claims from text."""
    import google.generativeai as genai
    genai.configure(api_key=api_key)

    # Use gemini-2.5-flash or fallback to gemini-1.5-flash
    for model_name in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]:
        try:
            model = genai.GenerativeModel(
                model_name=model_name,
                generation_config={"response_mime_type": "application/json"}
            )
            prompt = EXTRACT_PROMPT.replace("{input_text}", text)
            response = model.generate_content(prompt)
            data = json.loads(response.text)
            if isinstance(data, dict) and "claims" in data:
                return data["claims"]
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            if "not found" in str(e).lower() or "404" in str(e):
                continue
            print(f"Extraction error with {model_name}: {e}")
            break

    return []


# ============================================================
# NEURO-SYMBOLIC VERIFICATION LOGIC
# ============================================================

def verify_claims_against_duckdb(claims: List[Dict[str, Any]], duckdb_path: Path, tolerance: float = 0.5) -> List[Dict[str, Any]]:
    """
    Symbolically verify claims against DuckDB normalized_facts.
    Executes Python deterministic arithmetic.
    """
    import duckdb

    if not duckdb_path.exists():
        raise FileNotFoundError(f"DuckDB database not found at {duckdb_path}")

    con = duckdb.connect(str(duckdb_path), read_only=True)
    verified = []

    for c in claims:
        metric = c.get("metric", "")
        op = c.get("operation", "value_equality")
        stated_raw = c.get("stated_result", 0.0)
        try:
            stated = float(str(stated_raw).replace(",", "").replace("%", "").strip())
        except ValueError:
            stated = 0.0

        unit = c.get("unit", "")
        p_curr = c.get("period_current", "FY22")
        p_comp = c.get("period_compare", "FY21")
        quote = c.get("original_quote", "")

        # Multi-metric handling (e.g. Scope 1 and 2 sum)
        if "scope1_and_scope2" in metric.lower() or "scope_1_and_2" in metric.lower():
            f1_curr = query_duckdb_fact(con, "Scope1Emissions", p_curr)
            f2_curr = query_duckdb_fact(con, "Scope2Emissions", p_curr)
            f1_comp = query_duckdb_fact(con, "Scope1Emissions", p_comp) if p_comp else None
            f2_comp = query_duckdb_fact(con, "Scope2Emissions", p_comp) if p_comp else None

            if f1_curr and f2_curr:
                val_curr = f1_curr["value"] + f2_curr["value"]
                val_comp = (f1_comp["value"] + f2_comp["value"]) if (f1_comp and f2_comp) else None
                fact_curr = {"canonical_name": "Scope1+Scope2", "value": val_curr, "unit": "tCO2e"}
                fact_comp = {"canonical_name": "Scope1+Scope2", "value": val_comp, "unit": "tCO2e"} if val_comp else None
            else:
                fact_curr = None
                fact_comp = None
        else:
            fact_curr = query_duckdb_fact(con, metric, p_curr)
            fact_comp = query_duckdb_fact(con, metric, p_comp) if p_comp else None

        # Case 1: Insufficient Evidence / Missing DB Facts
        if not fact_curr:
            verified.append({
                "metric": metric,
                "original_quote": quote,
                "stated_result": f"{stated} {unit}".strip(),
                "verdict": "INSUFFICIENT_EVIDENCE",
                "ground_truth_current": "N/A",
                "ground_truth_prior": "N/A",
                "math_trace": f"[{op.upper()}] No matching concept in DuckDB for metric '{metric}' in {p_curr}",
                "reason": f"Ground-truth metric '{metric}' for period {p_curr} is not mapped in DuckDB normalized_facts."
            })
            continue

        # Case 2: Percentage Change (YoY)
        if op == "percentage_change":
            if not fact_comp:
                verified.append({
                    "metric": metric,
                    "original_quote": quote,
                    "stated_result": f"{stated}%",
                    "verdict": "INSUFFICIENT_EVIDENCE",
                    "ground_truth_current": f"{fact_curr['value']} {fact_curr['unit']}",
                    "ground_truth_prior": "N/A",
                    "math_trace": f"[{op.upper()}] Prior period {p_comp} missing in DuckDB",
                    "reason": f"Cannot compute YoY percentage change: prior period '{p_comp}' facts missing in DuckDB."
                })
                continue

            v_curr = fact_curr["value"]
            v_prev = fact_comp["value"]

            # Calculate YoY percentage change
            calculated_pct = ((v_curr - v_prev) / v_prev) * 100.0
            
            # Check magnitude or sign agreement (authors often state reductions as positive numbers e.g. "16% reduction")
            diff_abs = abs(abs(calculated_pct) - abs(stated))
            diff_signed = abs(calculated_pct - stated)
            diff = min(diff_abs, diff_signed)

            is_supported = diff <= tolerance

            verified.append({
                "metric": metric,
                "original_quote": quote,
                "stated_result": f"{stated}%",
                "verdict": "SUPPORTED" if is_supported else "INCONSISTENT",
                "ground_truth_current": f"{v_curr} {fact_curr['unit']}",
                "ground_truth_prior": f"{v_prev} {fact_comp['unit']}",
                "math_trace": f"(({v_curr} - {v_prev}) / {v_prev}) * 100 = {calculated_pct:.2f}% (diff: {diff:.2f}%)",
                "reason": (
                    f"Calculated {calculated_pct:.2f}% matches stated {stated}% within {tolerance}% tolerance."
                    if is_supported else
                    f"Discrepancy: Calculated {calculated_pct:.2f}% differs from stated {stated}% by {diff:.2f}% (exceeds {tolerance}%)."
                )
            })

        # Case 3: Absolute Value / Equality
        else:
            v_curr = fact_curr["value"]
            diff = abs(v_curr - stated)
            is_supported = diff <= (tolerance if stated > 10 else 0.1)

            verified.append({
                "metric": metric,
                "original_quote": quote,
                "stated_result": f"{stated} {unit}".strip(),
                "verdict": "SUPPORTED" if is_supported else "INCONSISTENT",
                "ground_truth_current": f"{v_curr} {fact_curr['unit']}",
                "ground_truth_prior": "N/A",
                "math_trace": f"DB value = {v_curr} vs Stated = {stated} (diff: {diff})",
                "reason": (
                    f"Direct value equality verified against DuckDB ({v_curr} {fact_curr['unit']})."
                    if is_supported else
                    f"Value mismatch: DuckDB reports {v_curr} {fact_curr['unit']} but text states {stated}."
                )
            })

    con.close()
    return verified


# ============================================================
# CLI INTERACTION & PRETTY REPORTING
# ============================================================

def print_verification_report(results: List[Dict[str, Any]]):
    """Prints a clear, formatted terminal report."""
    print("\n" + "=" * 80)
    print(" VeriBRSR - Neuro-Symbolic Verification Engine Report")
    print("=" * 80)

    for i, r in enumerate(results, 1):
        v = r["verdict"]
        symbol = "[OK] SUPPORTED" if v == "SUPPORTED" else "[X] INCONSISTENT" if v == "INCONSISTENT" else "[?] INSUFFICIENT_EVIDENCE"

        print(f"\nClaim #{i}: {symbol}")
        print(f"  Metric:       {r['metric']}")
        print(f"  Quote:        \"{r['original_quote']}\"")
        print(f"  Stated Value: {r['stated_result']}")
        print(f"  DuckDB Fact:  Current: {r['ground_truth_current']} | Prior: {r['ground_truth_prior']}")
        print(f"  Math Trace:   {r['math_trace']}")
        print(f"  Reason:       {r['reason']}")
        print("-" * 80)

    # Summary
    sup = sum(1 for r in results if r["verdict"] == "SUPPORTED")
    inc = sum(1 for r in results if r["verdict"] == "INCONSISTENT")
    ins = sum(1 for r in results if r["verdict"] == "INSUFFICIENT_EVIDENCE")
    print(f"\nSummary: {sup} Supported, {inc} Inconsistent, {ins} Insufficient Evidence (Total: {len(results)})")
    print("=" * 80 + "\n")


def main():
    parser = argparse.ArgumentParser(description="VeriBRSR: Verify custom ESG text against DuckDB XBRL facts.")
    parser.add_argument("--text", type=str, help="Prose text to verify")
    parser.add_argument("--file", type=str, help="Path to text file containing prose to verify")
    parser.add_argument("--output", type=str, default="data/claims/custom_verified_claims.json", help="Path to save output JSON")
    args = parser.parse_args()

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("[!] ERROR: GEMINI_API_KEY not found in environment or .env file.")
        sys.exit(1)

    # Read text from args, file, or default demo text
    if args.text:
        input_text = args.text
    elif args.file and os.path.exists(args.file):
        with open(args.file, "r", encoding="utf-8") as f:
            input_text = f.read()
    else:
        # Default sample text for instant demo
        print("\n[*] No custom text provided. Using default sample ESG text from Infosys FY22:")
        input_text = (
            "During Fiscal 2022, our total energy consumption was 650,476 GJ, representing a 3.15% reduction "
            "compared to 671,660 GJ in Fiscal 2021. Our renewable energy consumption accounted for 266,119 GJ. "
            "Our Scope 1 direct greenhouse gas emissions were 8,965 tCO2e, while Scope 2 emissions stood at 51,717 tCO2e. "
            "We also achieved a 25% reduction in municipal water withdrawal."
        )
        print(f"\nInput Text:\n\"{input_text}\"\n")

    print("[1/3] Extracting quantitative claims via Gemini 2.5 Flash...")
    claims = extract_claims_with_gemini(input_text, api_key)
    print(f"      Found {len(claims)} candidate claims.")

    print(f"[2/3] Querying DuckDB ({DUCKDB_PATH}) and executing math verification...")
    results = verify_claims_against_duckdb(claims, DUCKDB_PATH)

    print("[3/3] Generating report and saving results...")
    print_verification_report(results)

    output_path = Path(__file__).parent / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"[*] Results saved to {output_path}")


if __name__ == "__main__":
    main()
