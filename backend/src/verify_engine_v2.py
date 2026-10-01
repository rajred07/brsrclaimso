"""
VeriBRSR Verify Engine (v2)
===========================
Compares claims extracted from the PDF (extracted_claims.json) against
XBRL facts in DuckDB (normalized_facts) and produces verified_claims.json.

Fixes vs v1:
  - Metric names resolved to the REAL DB canonical names (exact -> rules -> fuzzy)
  - Signed comparison (a "decrease" claim no longer matches an increase)
  - yoy_direction supported; derived metrics (renewable share = renewable / total)
  - No double counting; dimensional (breakdown) facts are not picked over totals
  - Proper unit conversion (ML, kL, GJ/kWh/MWh, tonne/MT, INR lakh/crore)
  - Rounding-aware tolerance; parameterised SQL; period coverage pre-check
  - Every verdict carries a machine-readable reason_code

Usage:
  python verify_engine_v2.py [--claims PATH] [--db PATH] [--out PATH] [--filing-id ID]
"""

import argparse
import difflib
import json
import os
import re
import sys
from collections import Counter

import duckdb

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

REL_TOL = 0.01          # 1% relative tolerance
FLAT_PCT = 0.5          # |change| below this % counts as "flat" for yoy_direction

# ------------------------------------------------------------------
# Metric resolution  (claim metric -> DB canonical_name(s))
# ------------------------------------------------------------------
S1, S2, S3 = "Scope 1 GHG Emissions", "Scope 2 GHG Emissions", "Scope 3 GHG Emissions"
E_TOT = "Total Energy Consumption"
E_REN = "Renewable Energy Consumption"
E_NON = "Non-Renewable Energy Consumption"
EL_REN = "Renewable Electricity Consumption"
EL_GRID = "Grid Electricity Consumption"


def norm(k):
    return re.sub(r"[^a-z0-9]+", "_", str(k).lower()).strip("_")


# Exact aliases (normalised keys) -> list of DB names that are SUMMED
EXACT = {
    "scope1_emissions": [S1], "scope_1_emissions": [S1], "total_scope_1_emissions": [S1],
    "scope2_emissions": [S2], "scope_2_emissions": [S2], "total_scope_2_emissions": [S2],
    "scope3_emissions": [S3], "scope_3_emissions": [S3], "total_scope_3_emissions": [S3],
    "scope_1_and_2_emissions": [S1, S2], "scope1_and_scope2_emissions": [S1, S2],
    "ghg_emissions": [S1, S2],
    "energy_consumption": [E_TOT], "total_energy_consumption": [E_TOT],
    "power_consumption": [E_TOT], "reduction_in_global_power_consumption": [E_TOT],
    "renewable_energy_consumption": [E_REN],
    "non_renewable_energy_consumption": [E_NON],
    "total_energy_consumption_a_b_c": [E_REN],          # BRSR (a)+(b)+(c) = renewable
    "total_energy_consumed_from_non_renewable_sources_d_e_f": [E_NON],
    "total_energy_consumed_a_b_c_d_e_f": [E_TOT],       # total only (no double counting)
    "total_electricity_consumption_a": ["Renewable Electricity Consumption"],
    "total_fuel_consumption_b": ["Renewable Fuel Consumption"],
    "total_electricity_consumption_d": [EL_GRID],
    "total_fuel_consumption_e": ["Non-Renewable Fuel Consumption"],
    "water_consumption": ["Total Water Consumption"],
    "total_water_consumption": ["Total Water Consumption"],
    "surface_water": ["Surface Water Withdrawal"],
    "groundwater": ["Groundwater Withdrawal"],
    "third_party_water": ["Third-Party / Municipal Water"],
    "employee_headcount": ["Workforce Count"], "total_employees": ["Workforce Count"],
    "csr_spends": ["CSR Expenditure"],
    "revenue_from_operations": ["Revenue From Operations"],
    "profit_after_tax": ["Net Profit / (Loss)"],
    "nox": ["NOx Air Emissions"], "sox": ["SOx Air Emissions"],
    "what_we_dispose_stays_out_of_landfills": ["Waste Diverted from Landfill"],

    # --- AI-discovered HIGH confidence mappings (Gemini semantic matching) ---
    # Solar / Renewable
    "solar_photovoltaic_capacity": ["Installed solar PV capacity"],
    "total_installed_solar_capacity_across_campuses": ["Installed solar PV capacity"],
    "installed_solar_pv_capacity": ["Installed solar PV capacity"],
    "captive_solar_plant_in_karnataka": ["Installed solar PV capacity"],
    "electricity_in_india_operations_met_through_renewables": ["Renewable Electricity Consumption"],
    "electricity_consumption_through_renewable_sources": ["Renewable Electricity Consumption"],
    "share_of_renewables_in_our_india_operations": ["Renewable Electricity Consumption"],
    # Water
    "_i__surface_water": ["Surface Water Withdrawal"],
    "_ii__groundwater": ["Groundwater Withdrawal"],
    "_iii__third_party_water": ["Third-Party / Municipal Water"],
    "sent_to_third_parties___no_treatment": ["Untreated Water Discharge to Third Parties"],
    "water_intensity_in_terms_of_physical_output__kilolitres___fte_": ["Water Intensity (Physical Output)"],
    # Emissions
    "others___carbon_monoxide__co__": ["Other Emissions (Carbon Monoxide (CO))"],
    # Workforce
    "professionals_involved_in_service_delivery_to_clients__including_trainees": ["Workforce Count"],
    "permanent__d_": ["Workforce Count (Permanent Employees)"],
    "other_than_permanent__e_": ["Workforce Count (Other Than Permanent)"],
    "total__a_": ["Workforce Count"],
    # Financial
    "total": ["Total Turnover"],
    "turnover__in___crore_": ["Total Turnover"],
    "export_revenues": ["Export Contribution to Total Turnover"],
    "what_is_the_contribution_of_exports_as_a_percentage_of_the_total_turnover_of_the_entity_": ["Export Contribution to Total Turnover"],
    # CSR
    "global_csr_spends": ["Amount Spent on CSR Projects"],
    "rural_families_benefited_through_carbon_offset_programs": ["Number of Beneficiaries from CSR Projects"],
    "rural_families_continue_to_benefit_from_our_carbon_offset_projects": ["Number of Beneficiaries from CSR Projects"],
    "rural_families_benefited": ["Number of Beneficiaries from CSR Projects"],
}

# Derived ratios: (numerator names, denominator names) -> value = num/den*100 (%)
DERIVED = {
    "renewable_energy_share": ([E_REN], [E_TOT]),
    "renewable_electricity_share": ([EL_REN], [EL_REN, EL_GRID]),
    # Energy intensity as derived ratio
    "energy_intensity_per_rupee_of_turnover": ([E_TOT], ["Revenue From Operations"]),
    "energy_performance_index__epi_": ([E_TOT], ["Total Turnover"]),
}

# Ordered regex rules on the normalised key (first hit wins)
RULES = [
    (r"scope_?1.*scope_?2|scope_?1_and_2", [S1, S2]),
    (r"scope_?1", [S1]),
    (r"scope_?2", [S2]),
    (r"scope_?3", [S3]),
    (r"water.*withdraw", ["Total Water Withdrawal"]),
    (r"water.*discharg", ["Total Water Discharged"]),
    (r"water.*consum", ["Total Water Consumption"]),
    (r"non_?renewable.*energy|energy.*non_?renewable", [E_NON]),
    (r"renewable.*energy|energy.*renewable", [E_REN]),
    (r"energy.*(consum|use)", [E_TOT]),
    (r"particulate", ["Particulate Matter (PM)"]),
    (r"total_waste_generated|waste_generated", ["Total Waste Generated"]),
    (r"employee|headcount|workforce", ["Workforce Count"]),
]


def resolve_metric(raw, db_names):
    """Return (kind, spec, how). kind in {'sum','derived',None}."""
    if not raw:
        return None, None, None
    lowered = {n.lower(): n for n in db_names}
    if str(raw).lower() in lowered:                       # already a DB canonical name
        return "sum", [lowered[str(raw).lower()]], "db_name"
    k = norm(raw)
    if k in DERIVED:
        return "derived", DERIVED[k], "derived"
    if k in EXACT:
        return "sum", EXACT[k], "exact"
    for pat, names in RULES:
        if re.search(pat, k):
            return "sum", names, "rule"
    hit = difflib.get_close_matches(k.replace("_", " "), list(lowered), n=1, cutoff=0.75)
    if hit:
        return "sum", [lowered[hit[0]]], "fuzzy"
    return None, None, None


# ------------------------------------------------------------------
# Periods
# ------------------------------------------------------------------
def map_period(p):
    """'FY 2021-22' / 'FY22' / 'FY2022' / '2022' / 'Fiscal 2022' -> '2021-22'."""
    if not p:
        return None
    s = str(p).strip()
    m = re.search(r"(20\d{2})\s*[-/\u2013]\s*(\d{2,4})", s)
    if m:
        return f"{int(m.group(1))}-{m.group(2)[-2:]}"
    m = re.search(r"(?:FY|Fiscal(?:\s*Year)?)\s*'?(\d{4}|\d{2})\b", s, re.I) or re.fullmatch(r"(\d{4})", s)
    if m:
        y = int(m.group(1))
        y = y + 2000 if y < 100 else y
        return f"{y - 1}-{str(y)[2:]}"
    return None


def previous_period(key):
    y = int(key[:4]) - 1
    return f"{y}-{str(y + 1)[2:]}"


# ------------------------------------------------------------------
# Units
# ------------------------------------------------------------------
# key -> (dimension, factor to base unit). Bases: GJ, kL, tonne, INR
UNITS = {
    "gj": ("energy", 1.0), "tj": ("energy", 1000.0), "mj": ("energy", 0.001),
    "kwh": ("energy", 0.0036), "mwh": ("energy", 3.6),
    "kl": ("volume", 1.0), "kilolitre": ("volume", 1.0), "kilolitres": ("volume", 1.0),
    "l": ("volume", 0.001), "liters": ("volume", 0.001), "liter": ("volume", 0.001),
    "litres": ("volume", 0.001), "m3": ("volume", 1.0),
    "tonne": ("mass", 1.0), "tonnes": ("mass", 1.0), "t": ("mass", 1.0), "mt": ("mass", 1.0),
    "tco2e": ("mass", 1.0), "tco2": ("mass", 1.0), "ktco2e": ("mass", 1000.0),
    "kgco2e": ("mass", 0.001), "kg": ("mass", 0.001), "kt": ("mass", 1000.0),
    "inr": ("money", 1.0), "inrlakh": ("money", 1e5), "lakh": ("money", 1e5),
    "inrcr": ("money", 1e7), "inrcrore": ("money", 1e7), "cr": ("money", 1e7), "crore": ("money", 1e7),
    "%": ("pct", 1.0), "percent": ("pct", 1.0),
    "count": ("count", 1.0), "pure": ("count", 1.0), "number": ("count", 1.0),
}


def unit_info(u):
    if not u:
        return None
    s = str(u).strip()
    if s == "ML":                       # megalitre (case-sensitive)
        return ("volume", 1000.0)
    if s == "mL":
        return ("volume", 1e-6)
    return UNITS.get(re.sub(r"[\s\.\-_/]", "", s.lower()))


def convert_unit(value, db_unit, claim_unit):
    """Convert DB value into the claim's unit. Returns (value, note) or None if incompatible."""
    if not claim_unit:
        return value, ""
    a, b = unit_info(db_unit), unit_info(claim_unit)
    if not a or not b:
        same = norm(db_unit or "") == norm(claim_unit)
        return (value, "") if same else None
    if a[0] != b[0]:
        return None
    if a[1] == b[1]:
        return value, ""
    return value * a[1] / b[1], f" [converted {db_unit} -> {claim_unit}]"


# ------------------------------------------------------------------
# DB access
# ------------------------------------------------------------------
def period_clause(pkey, filing_id):
    y1 = pkey[:4]
    y2 = int(y1) + 1
    where = "(period LIKE ? OR raw_period LIKE ?)"
    params = [f"%{pkey}%", f"{y1}-% to {y2}-%"]
    if filing_id:
        where += " AND filing_id = ?"
        params.append(filing_id)
    return where, params


def fetch_fact(con, name, pkey, filing_id):
    where, params = period_clause(pkey, filing_id)
    rows = con.execute(
        f"SELECT value, unit, COALESCE(dimensions,'') FROM normalized_facts "
        f"WHERE lower(canonical_name) = lower(?) AND {where}",
        [name] + params,
    ).fetchall()
    if not rows:
        return None, None, f"'{name}' not found in XML for {pkey}"
    plain = [r for r in rows if r[2] == ""]
    if plain:
        return plain[0][0], plain[0][1], ""
    if len(rows) == 1:
        return rows[0][0], rows[0][1], " [used single dimensional fact]"
    return None, None, f"'{name}' has {len(rows)} dimensional facts and no total for {pkey}"


def sum_facts(con, names, pkey, filing_id):
    total, unit, notes = 0.0, None, []
    for n in names:
        v, u, msg = fetch_fact(con, n, pkey, filing_id)
        if v is None:
            return None, None, msg
        total += v
        unit = unit or u
        if msg:
            notes.append(msg)
    return total, unit, "".join(notes)


def compute_value(con, kind, spec, pkey, filing_id):
    if kind == "sum":
        return sum_facts(con, spec, pkey, filing_id)
    num_names, den_names = spec
    num, _, m1 = sum_facts(con, num_names, pkey, filing_id)
    if num is None:
        return None, None, m1
    den, _, m2 = sum_facts(con, den_names, pkey, filing_id)
    if den is None:
        return None, None, m2
    if den == 0:
        return None, None, "denominator is zero"
    return num / den * 100.0, "%", (m1 + m2)


# ------------------------------------------------------------------
# Comparison helpers
# ------------------------------------------------------------------
def decimals(x):
    s = f"{x:.10f}".rstrip("0")
    return len(s.split(".")[1]) if "." in s else 0


def tolerance(stated):
    return max(abs(stated) * REL_TOL, 0.5 * 10 ** (-decimals(stated)))


def direction(x):
    return "flat" if x == 0 else ("up" if x > 0 else "down")


# ------------------------------------------------------------------
# Verify one claim
# ------------------------------------------------------------------
def verify_one(con, claim, db_names, filing_id):
    out = dict(claim)

    def done(verdict, code, reason, trace=None):
        out.update(verdict=verdict, reason_code=code, reason=reason)
        if trace is not None:
            out["math_trace"] = trace
        return out

    op = claim.get("operation") or "value_equality"
    raw = claim.get("asserted_value", claim.get("stated_result"))
    if raw is None:
        return done("INCOMPARABLE", "NO_VALUE", "No numerical asserted value in claim.")
    try:
        stated = float(raw)
    except (TypeError, ValueError):
        return done("INCOMPARABLE", "BAD_VALUE", f"Could not parse asserted value: {raw}")

    kind, spec, how = resolve_metric(claim.get("metric", ""), db_names)
    if kind is None:
        return done("INCOMPARABLE", "METRIC_UNMAPPED",
                    f"Metric '{claim.get('metric')}' could not be mapped to any XML concept.")
    out["matched_metric"] = spec
    out["matched_via"] = how

    cur_key = map_period(claim.get("current_period") or claim.get("period_current"))
    if not cur_key:
        return done("INCOMPARABLE", "PERIOD_UNPARSED",
                    f"Could not parse period '{claim.get('current_period')}'.")

    cur, db_unit, msg = compute_value(con, kind, spec, cur_key, filing_id)
    if cur is None:
        return done("INCOMPARABLE", "FACT_MISSING", msg)
    notes = msg

    prior = None
    if op in ("absolute_change", "percentage_change", "yoy_direction"):
        prior_key = map_period(claim.get("prior_period") or claim.get("period_compare"))
        if not prior_key:
            prior_key = previous_period(cur_key)
            notes += f" [prior period inferred: {prior_key}]"
        prior, _, msg = compute_value(con, kind, spec, prior_key, filing_id)
        if prior is None:
            return done("INCOMPARABLE", "PRIOR_FACT_MISSING", msg)
        notes += msg

    trace = {"value_current": cur, "value_prior": prior, "db_unit": db_unit,
             "claim_unit": claim.get("unit")}

    # ---- compute ----
    if op in ("value_equality", "absolute_change"):
        calc = cur if op == "value_equality" else cur - prior
        conv = convert_unit(calc, db_unit, claim.get("unit"))
        if conv is None:
            return done("INCOMPARABLE", "UNIT_MISMATCH",
                        f"Cannot compare DB unit '{db_unit}' with claim unit '{claim.get('unit')}'.", trace)
        calc, note = conv
        notes += note
    elif op == "percentage_change":
        if prior == 0:
            return done("INCOMPARABLE", "DIV_ZERO", "Prior-period value is zero.", trace)
        calc = (cur - prior) / abs(prior) * 100.0
    elif op == "yoy_direction":
        pct = 0.0 if prior == cur else ((cur - prior) / abs(prior) * 100.0 if prior else (1e9 if cur > prior else -1e9))
        actual = "flat" if abs(pct) < FLAT_PCT else direction(pct)
        claimed = direction(stated)
        trace.update(calculated_pct_change=pct, actual_direction=actual, claimed_direction=claimed)
        if actual == claimed:
            return done("SUPPORTED", "MATCH",
                        f"Direction '{claimed}' confirmed (change {pct:+.2f}%).{notes}", trace)
        return done("INCONSISTENT", "MISMATCH",
                    f"Claimed '{claimed}' but XML shows '{actual}' ({pct:+.2f}%).{notes}", trace)
    else:
        return done("INCOMPARABLE", "BAD_OP", f"Unknown operation: {op}", trace)

    # ---- signed comparison ----
    tol = tolerance(stated)
    trace.update(calculated_result=calc, tolerance=tol)
    if abs(calc - stated) <= tol:
        return done("SUPPORTED", "MATCH",
                    f"Calculated {calc:.4f} matches claimed {stated} (tol {tol:.4g}).{notes}", trace)
    if abs(abs(calc) - abs(stated)) <= tol:
        return done("INCONSISTENT", "SIGN_MISMATCH",
                    f"Magnitude matches but sign differs: calculated {calc:.4f}, claimed {stated}.{notes}", trace)
    return done("INCONSISTENT", "MISMATCH",
                f"Calculated {calc:.4f} does not match claimed {stated} (tol {tol:.4g}).{notes}", trace)


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
def load_claims(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["claims"] if isinstance(data, dict) and "claims" in data else data


def verify_claims(claims_path, db_path, out_path, filing_id=None):
    if not os.path.exists(claims_path):
        print(f"Error: claims file not found: {claims_path}")
        return
    if not os.path.exists(db_path):
        print("Error: database not found. Run the XBRL pipeline first.")
        return

    con = duckdb.connect(db_path, read_only=True)
    claims = load_claims(claims_path)
    db_names = [r[0] for r in con.execute("SELECT DISTINCT canonical_name FROM normalized_facts").fetchall()]
    db_periods = [r[0] for r in con.execute("SELECT DISTINCT period FROM normalized_facts ORDER BY 1").fetchall()]

    print(f"Loaded {len(claims)} claims | {len(db_names)} distinct XML metrics")
    print(f"Periods available in XML: {db_periods}")
    claim_periods = Counter(map_period(c.get("current_period")) for c in claims)
    print(f"Periods referenced by claims: {dict(claim_periods)}")
    covered = {p for p in claim_periods if p and any(p in dp for dp in db_periods)}
    missing = [p for p in claim_periods if p not in covered]
    if missing:
        print(f"[WARNING] No XML facts for claim period(s) {missing}. "
              f"PDF and XML must be the same filing year (or overlap).")

    verified, verdicts, codes = [], Counter(), Counter()
    for claim in claims:
        res = verify_one(con, claim, db_names, filing_id)
        verified.append(res)
        verdicts[res["verdict"]] += 1
        codes[res["reason_code"]] += 1
        if res["verdict"] != "INCOMPARABLE":
            print(f"  [{res['verdict']}] [{claim.get('claim_id')}] {claim.get('metric')}: {res['reason'][:110]}")
    con.close()

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(verified, f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 60}\nVERIFICATION SUMMARY\n{'=' * 60}")
    print(f"Total claims:  {len(claims)}")
    for v in ("SUPPORTED", "INCONSISTENT", "INCOMPARABLE"):
        print(f"{v:<13}: {verdicts[v]}")
    print("\nBy reason code:")
    for code, n in codes.most_common():
        print(f"  {code:<20} {n}")
    unmapped = sorted({c.get("metric") for c, r in zip(claims, verified) if r["reason_code"] == "METRIC_UNMAPPED"})
    if unmapped:
        print(f"\nUnmapped metrics (add to EXACT/RULES): {unmapped}")
    print(f"\nSaved: {out_path}\n{'=' * 60}")


if __name__ == "__main__":
    base = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    ap = argparse.ArgumentParser()
    
    # Defaults configured for Infosys FY2025-26 as requested
    default_filing_id = "infosys-lts-202526-0434"
    ap.add_argument("--claims", default=os.path.join(base, "data", "filings", default_filing_id, "extracted_claims.json"))
    ap.add_argument("--db", default=os.path.join(base, "data", "parsed", "brsr_facts.duckdb"))
    ap.add_argument("--out", default=os.path.join(base, "data", "filings", default_filing_id, "verified_claims_v2.json"))
    ap.add_argument("--filing-id", default=default_filing_id, help="Restrict to one filing_id in normalized_facts")
    
    a = ap.parse_args()
    verify_claims(a.claims, a.db, a.out, a.filing_id)
