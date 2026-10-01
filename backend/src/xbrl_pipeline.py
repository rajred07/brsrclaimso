"""
VeriBRSR Intelligent Universal XML Pipeline (Gemini-Powered)
===========================================================
Extracts, semantically maps, and normalizes XBRL facts from any BRSR XML instance.
Uses a hybrid approach:
1. High-precision canonical rules for core SEBI / BSE taxonomy metrics.
2. Gemini 2.5 Flash API for zero-shot intelligent semantic mapping of any custom,
   extended, or new taxonomy tags with persistent local caching.
3. Automatically populates DuckDB and generates structured JSON for UI display.
"""

import os
import sys
import re
import json
from pathlib import Path
from bs4 import BeautifulSoup
import duckdb
from dotenv import load_dotenv

load_dotenv()

# Pre-defined base canonical rules
BASE_CANONICAL_RULES = {
    # Energy
    "TotalEnergyConsumedFromRenewableAndNonRenewableSources": ("Total Energy Consumption", "Energy", "GJ"),
    "TotalEnergyConsumption": ("Total Energy Consumption", "Energy", "GJ"),
    "TotalEnergyConsumedFromRenewableSources": ("Renewable Energy Consumption", "Energy", "GJ"),
    "TotalEnergyConsumedFromNonRenewableSources": ("Non-Renewable Energy Consumption", "Energy", "GJ"),
    "TotalElectricityConsumptionFromRenewableSources": ("Renewable Electricity Consumption", "Energy", "GJ"),
    "TotalElectricityConsumptionFromNonRenewableSources": ("Grid Electricity Consumption", "Energy", "GJ"),
    "TotalFuelConsumptionFromRenewableSources": ("Renewable Fuel Consumption", "Energy", "GJ"),
    "TotalFuelConsumptionFromNonRenewableSources": ("Non-Renewable Fuel Consumption", "Energy", "GJ"),
    "EnergyIntensityPerRupeeOfTurnover": ("Energy Intensity (per Turnover)", "Energy", "GJ/INR"),
    "EnergyIntensityInTermOfPhysicalOutput": ("Energy Intensity (Physical Output)", "Energy", "GJ/Unit"),

    # Water
    "TotalVolumeOfWaterWithdrawal": ("Total Water Withdrawal", "Water", "kL"),
    "TotalVolumeOfWaterConsumption": ("Total Water Consumption", "Water", "kL"),
    "WaterWithdrawalBySurfaceWater": ("Surface Water Withdrawal", "Water", "kL"),
    "WaterWithdrawalByGroundwater": ("Groundwater Withdrawal", "Water", "kL"),
    "WaterWithdrawalByThirdPartyWater": ("Third-Party / Municipal Water", "Water", "kL"),
    "TotalWaterDischargedInKilolitres": ("Total Water Discharged", "Water", "kL"),
    "WaterIntensityPerRupeeOfTurnover": ("Water Intensity (per Turnover)", "Water", "kL/INR"),
    "WaterIntensityInTermOfPhysicalOutput": ("Water Intensity (Physical Output)", "Water", "kL/Unit"),

    # Emissions
    "TotalScope1Emissions": ("Scope 1 GHG Emissions", "Emissions", "tCO2e"),
    "TotalScope2Emissions": ("Scope 2 GHG Emissions", "Emissions", "tCO2e"),
    "TotalScope3Emissions": ("Scope 3 GHG Emissions", "Emissions", "tCO2e"),
    "TotalScope1AndScope2EmissionsIntensityPerRupeeOfTurnover": ("Scope 1+2 Intensity (Turnover)", "Emissions", "tCO2e/INR"),
    "TotalScope1AndScope2EmissionsIntensityInTermOfPhysicalOutput": ("Scope 1+2 Intensity (Physical)", "Emissions", "tCO2e/Unit"),
    "NOx": ("NOx Air Emissions", "Emissions", "kg"),
    "SOx": ("SOx Air Emissions", "Emissions", "kg"),
    "ParticulateMatter": ("Particulate Matter (PM)", "Emissions", "kg"),

    # Waste
    "TotalWasteGenerated": ("Total Waste Generated", "Waste", "Tonne"),
    "TotalWasteRecovered": ("Total Waste Recovered / Recycled", "Waste", "Tonne"),
    "TotalWasteDisposed": ("Total Waste Disposed", "Waste", "Tonne"),
    "PlasticWaste": ("Plastic Waste Generated", "Waste", "Tonne"),
    "EWaste": ("E-Waste Generated", "Waste", "Tonne"),
    "BioMedicalWaste": ("Biomedical Waste", "Waste", "Tonne"),
    "BatteryWaste": ("Battery Waste", "Waste", "Tonne"),
    "ConstructionAndDemolitionWaste": ("Construction & Demolition Waste", "Waste", "Tonne"),
    "OtherHazardousWaste": ("Hazardous Waste", "Waste", "Tonne"),
    "OtherNonHazardousWasteGenerated": ("Non-Hazardous Waste", "Waste", "Tonne"),

    # Workforce & Governance
    "NumberOfEmployeesOrWorkersIncludingDifferentlyAbled": ("Workforce Count", "Workforce", "count"),
    "TurnoverRate": ("Voluntary Turnover Rate", "Workforce", "%"),
    "ValueOfSharesPaidUp": ("Paid-Up Share Capital", "Financial", "INR"),
    "RevenueFromOperations": ("Revenue From Operations", "Financial", "INR"),
    "ProfitLossForPeriod": ("Net Profit / (Loss)", "Financial", "INR"),
    "AmountSpentOnCSR": ("CSR Expenditure", "Social", "INR")
}


def load_cached_mappings(cache_file: Path) -> dict:
    mappings = dict(BASE_CANONICAL_RULES)
    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cached = json.load(f)
                for k, v in cached.items():
                    mappings[k] = (v.get("canonical_name", k), v.get("category", "General"), v.get("standard_unit", ""))
        except Exception as e:
            print(f"[!] Warning: Could not read concept cache: {e}")
    return mappings


def save_cached_mappings(cache_file: Path, new_mappings: dict):
    existing = {}
    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    existing = loaded
        except Exception:
            existing = {}
    
    if isinstance(new_mappings, dict):
        existing.update(new_mappings)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)


def map_unknown_concepts_with_gemini(unknown_concepts: list, api_key: str) -> dict:
    """Uses Gemini 2.5 Flash to generate canonical names and categories for raw tags."""
    if not unknown_concepts or not api_key:
        return {}

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")

        # Process in batches of 40
        batch = unknown_concepts[:40]
        prompt = f"""You are an expert ESG and SEBI BRSR financial XBRL ontologist.
Map the following raw XBRL concepts to clean, professional metrics for an ESG audit system:
{json.dumps(batch, indent=2)}

Return a JSON object where each key is the raw concept name, and each value is an object:
{{
  "canonical_name": "Clear, human-readable ESG metric title (e.g. 'Renewable Electricity Consumption', 'Voluntary Turnover Rate')",
  "category": "One of: ['Energy', 'Emissions', 'Water', 'Waste', 'Workforce', 'Governance', 'Social', 'Financial']",
  "standard_unit": "Standard unit ('GJ', 'tCO2e', 'kL', 'Tonne', 'count', '%', 'INR', 'ratio')"
}}

Return ONLY valid JSON.
"""
        response = model.generate_content(prompt)
        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        parsed = json.loads(text)
        normalized_dict = {}

        if isinstance(parsed, dict):
            for k, v in parsed.items():
                if isinstance(v, dict):
                    normalized_dict[k] = {
                        "canonical_name": v.get("canonical_name", k),
                        "category": v.get("category", "General"),
                        "standard_unit": v.get("standard_unit", "")
                    }
        elif isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict):
                    cname = item.get("concept") or item.get("concept_name") or item.get("tag") or item.get("name")
                    if cname:
                        normalized_dict[cname] = {
                            "canonical_name": item.get("canonical_name", cname),
                            "category": item.get("category", "General"),
                            "standard_unit": item.get("standard_unit", "")
                        }

        print(f"[Gemini] Successfully mapped {len(normalized_dict)} concepts with Gemini Flash.")
        return normalized_dict
    except Exception as e:
        print(f"[!] Gemini mapping exception: {e}")
        return {}


def clean_unit_name(unit_ref: str) -> str:
    if not unit_ref:
        return ""
    u = unit_ref.lower()
    if "gigajoule" in u or "gj" in u:
        return "GJ"
    if "kiloliter" in u or "kl" in u:
        return "kL"
    if "tco2e" in u or "mtco2e" in u:
        return "tCO2e"
    if "tonne" in u or u.endswith(":t"):
        return "Tonne"
    if "kg" in u:
        return "kg"
    if "inr" in u:
        return "INR"
    if "pure" in u:
        return "count"
    return unit_ref.split(":")[-1]


def clean_period_label(cid: str, raw_period: str, cy_period: str = "", py_period: str = "") -> str:
    # 1. Derive fiscal year label from dates
    fy_str = ""
    m_years = re.findall(r"\b(\d{4})\b", raw_period or "")
    if len(m_years) >= 2:
        y1, y2 = int(m_years[0]), int(m_years[1])
        if y1 == y2 - 1:
            fy_str = f"FY {y1}-{str(y2)[2:]}"
        elif y1 == y2:
            fy_str = f"FY {y1}"
    elif len(m_years) == 1:
        fy_str = f"As of {m_years[0]}"

    # 2. Determine relative role from dates matching DCYMain/DPYMain or context ID
    cid_u = (cid or "").upper()
    role = ""
    if any(k in cid_u for k in ["2PY", "PY2", "P2Y", "PPY", "BASELINE", "PREVIOUS2"]):
        role = "Baseline Year"
    elif (cy_period and raw_period == cy_period) or any(k in cid_u for k in ["DCY", "ICY"]) or "_CY" in cid_u or "CURRENT" in cid_u:
        role = "Current Year"
    elif (py_period and raw_period == py_period) or any(k in cid_u for k in ["DPY", "IPY"]) or "_PY" in cid_u or "PRIOR" in cid_u or "PREVIOUS" in cid_u:
        role = "Prior Year"

    if fy_str and role:
        return f"{fy_str} ({role})"
    elif fy_str:
        return fy_str
    elif role:
        return role
    return raw_period


def run_xbrl_pipeline(xml_path: str, filing_id: str, duckdb_path: str, output_json: str):
    print(f"[*] Starting Universal XBRL Pipeline for: {xml_path}")
    if not os.path.exists(xml_path):
        raise FileNotFoundError(f"XML file not found: {xml_path}")

    # Set up cache
    base_dir = Path(__file__).resolve().parent.parent
    cache_file = base_dir / "configs" / "gemini_concept_cache.json"
    concept_map = load_cached_mappings(cache_file)

    with open(xml_path, "r", encoding="utf-8") as f:
        content = f.read()

    soup = BeautifulSoup(content, "xml")

    # 1. Discover explanatory / name tags for typed members (e.g. NameOfOtherEmissions -> "Carbon Monoxide (CO)")
    context_text_labels = {}
    main_contexts = {"DCYMAIN", "DPYMAIN", "ICYMAIN", "IPYMAIN", "D_MAIN", "I_MAIN"}
    for tag in soup.find_all(True):
        if not tag.has_attr("contextRef"):
            continue
        c_ref = tag["contextRef"]
        if c_ref.upper() in main_contexts or "EXPLANATORYTEXTBLOCK" in tag.name.upper():
            continue
        t_name = tag.name.split(":")[-1]
        val_text = tag.text.strip()
        if (t_name.startswith("NameOf") or t_name.endswith("Name") or "Description" in t_name) and 0 < len(val_text) < 100:
            context_text_labels[c_ref] = val_text

    # 2. Parse Contexts
    raw_contexts = {}
    for ctx in soup.find_all("context"):
        cid = ctx.get("id")
        p = "Unknown Period"
        if ctx.find("instant"):
            p = ctx.find("instant").text
        elif ctx.find("startDate") and ctx.find("endDate"):
            p = f"{ctx.find('startDate').text} to {ctx.find('endDate').text}"

        dims = {}
        for em in ctx.find_all("explicitMember"):
            dim = em.get("dimension", "").split(":")[-1]
            val = em.text.split(":")[-1]
            dims[dim] = val

        for tm in ctx.find_all("typedMember"):
            dim = tm.get("dimension", "").split(":")[-1]
            val = tm.text.strip()
            dims[dim] = val

        raw_contexts[cid] = {"period": p, "dims": dims}

    # Find benchmark dates for Current Year (DCYMain) and Prior Year (DPYMain)
    cy_period_date = raw_contexts.get("DCYMain", {}).get("period", "")
    py_period_date = raw_contexts.get("DPYMain", {}).get("period", "")

    contexts = {}
    for cid, cdata in raw_contexts.items():
        contexts[cid] = {
            "period": cdata["period"],
            "period_label": clean_period_label(cid, cdata["period"], cy_period_date, py_period_date),
            "dims": cdata["dims"]
        }

    # 3. Parse Units
    units = {}
    for u in soup.find_all("unit"):
        uid = u.get("id")
        m = u.find("measure")
        units[uid] = m.text if m else uid

    # 4. Discover all numerical tags and identify unmapped ones
    all_numerical_tags = []
    unmapped_candidates = set()
    keywords = ["energy", "water", "emission", "scope", "waste", "employee", "worker", "turnover", "revenue", "profit", "csr", "injury", "safety"]

    for tag in soup.find_all(True):
        if not tag.has_attr("contextRef"):
            continue

        raw_val = tag.text.strip().replace(",", "")
        try:
            val_float = float(raw_val)
        except ValueError:
            continue

        concept = tag.name.split(":")[-1]
        all_numerical_tags.append((concept, tag, val_float))

        if concept not in concept_map:
            # Check if relevant to ESG
            if any(k in concept.lower() for k in keywords):
                unmapped_candidates.add(concept)

    # 5. Use Gemini if there are unmapped candidates
    api_key = os.getenv("GEMINI_API_KEY")
    if unmapped_candidates and api_key:
        print(f"[*] Querying Gemini 2.5 Flash to map {len(unmapped_candidates)} new ESG concepts...")
        gemini_mapped = map_unknown_concepts_with_gemini(list(unmapped_candidates), api_key)
        if gemini_mapped:
            save_cached_mappings(cache_file, gemini_mapped)
            # Reload mappings
            concept_map = load_cached_mappings(cache_file)

    # 6. Extract and normalize all facts
    normalized_facts = []
    seen_keys = set()

    for concept, tag, val_float in all_numerical_tags:
        if concept not in concept_map:
            continue

        canonical_name, category, default_unit = concept_map[concept]
        ctx_id = tag.get("contextRef")
        ctx_info = contexts.get(ctx_id, {"period": "Unknown", "period_label": "Unknown", "dims": {}})
        dims = dict(ctx_info["dims"])

        # Check if there is a specific text label for this context (e.g. Carbon Monoxide (CO))
        named_item = context_text_labels.get(ctx_id, "")
        if named_item:
            dims["item_name"] = named_item

        # Unit resolution: Always trust actual XML unitRef first (kg, kL, GJ, INR, Tonne, tCO2e)
        unit_ref = tag.get("unitRef", "")
        extracted_unit = clean_unit_name(units.get(unit_ref, unit_ref))
        if extracted_unit and extracted_unit != "count":
            final_unit = extracted_unit
        elif default_unit:
            final_unit = default_unit
        else:
            final_unit = extracted_unit or "count"

        # Friendly naming for dimension breakdowns
        display_name = canonical_name
        is_breakdown = False

        if named_item:
            display_name = f"{canonical_name} ({named_item})"
            is_breakdown = True
        elif dims:
            dim_values = list(dims.values())
            # Check if this is a gender breakdown
            if "MaleMember" in dim_values:
                display_name = f"{canonical_name} (Male)"
                is_breakdown = True
            elif "FemaleMember" in dim_values:
                display_name = f"{canonical_name} (Female)"
                is_breakdown = True
            elif "PermanentEmployeesMember" in dim_values:
                display_name = f"{canonical_name} (Permanent Employees)"
                is_breakdown = False
            elif "OtherThanPermanentEmployeesMember" in dim_values:
                display_name = f"{canonical_name} (Other Than Permanent)"
                is_breakdown = True
            elif any("Workers" in d for d in dim_values):
                display_name = f"{canonical_name} (Workers)"
                is_breakdown = True
            elif not any("Total" in d or "All" in d for d in dim_values):
                is_breakdown = True

        # Percentage adjustment for pure decimals (e.g. 0.141 -> 14.1%)
        final_val = val_float
        if final_unit == "%" and 0.0 < final_val <= 1.0:
            final_val = round(final_val * 100.0, 2)

        unique_key = (display_name, ctx_info["period"], tuple(sorted(dims.items())))
        if unique_key not in seen_keys:
            seen_keys.add(unique_key)
            normalized_facts.append({
                "filing_id": filing_id,
                "canonical_name": display_name,
                "base_concept": concept,
                "category": category,
                "period": ctx_info["period_label"],
                "raw_period": ctx_info["period"],
                "value": final_val,
                "unit": final_unit,
                "dimensions": json.dumps(dims) if dims else "",
                "is_breakdown": is_breakdown,
                "source_file": os.path.basename(xml_path)
            })

    # Sort facts cleanly: Category -> Canonical Name -> Period
    normalized_facts.sort(key=lambda x: (x["category"], x["canonical_name"], x["period"]))

    print(f"[OK] Successfully normalized {len(normalized_facts)} facts with Gemini & Canonical Rules.")

    # 6. Save JSON output
    out_path = Path(output_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(normalized_facts, f, indent=2)
    print(f"[OK] Saved facts JSON to: {out_path}")

    # 7. Upsert into DuckDB
    if duckdb_path:
        db_path = Path(duckdb_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        con = duckdb.connect(str(db_path))

        con.execute("""
        CREATE TABLE IF NOT EXISTS normalized_facts (
            filing_id VARCHAR,
            company VARCHAR,
            canonical_name VARCHAR,
            category VARCHAR,
            period VARCHAR,
            raw_period VARCHAR,
            value DOUBLE,
            unit VARCHAR,
            source_concept VARCHAR,
            dimensions VARCHAR,
            source_file VARCHAR
        );
        """)

        # Clear existing facts for this file
        source_name = os.path.basename(xml_path)
        con.execute("DELETE FROM normalized_facts WHERE source_file = ? OR filing_id = ?", [source_name, filing_id])

        # Batch insert
        for f in normalized_facts:
            con.execute("""
            INSERT INTO normalized_facts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                f["filing_id"],
                "Infosys Ltd.",
                f["canonical_name"],
                f["category"],
                f["period"],
                f["raw_period"],
                f["value"],
                f["unit"],
                f["base_concept"],
                f["dimensions"],
                f["source_file"]
            ])

        con.close()
        print(f"[OK] Synchronized into DuckDB at: {db_path}")

    return normalized_facts


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python xbrl_pipeline.py <xml_path> <filing_id> [output_json] [duckdb_path]")
        sys.exit(1)

    xml_p = sys.argv[1]
    f_id = sys.argv[2]
    out_j = sys.argv[3] if len(sys.argv) > 3 else f"data/filings/{f_id}/facts.json"
    d_path = sys.argv[4] if len(sys.argv) > 4 else "data/parsed/brsr_facts.duckdb"

    facts = run_xbrl_pipeline(xml_p, f_id, d_path, out_j)
    print(f"PIPELINE_COMPLETE: {len(facts)} facts processed.")
