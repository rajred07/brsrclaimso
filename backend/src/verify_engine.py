import json
import os
import sys
import duckdb
import pandas as pd

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def load_claims(filepath):
    if not os.path.exists(filepath):
        print(f"Error: Could not find {filepath}")
        return []
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
        if isinstance(data, dict) and "claims" in data:
            return data["claims"]
        return data

def save_verified_claims(claims, filepath):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(claims, f, indent=2, ensure_ascii=False)

def get_fact_value(con, metric, period):
    # Retrieve the first matching fact for the given period using LIKE
    query = f"SELECT value, unit FROM normalized_facts WHERE canonical_name = '{metric}' AND period LIKE '%{period}%' LIMIT 1"
    result = con.execute(query).fetchone()
    return (result[0], result[1]) if result else (None, None)

def map_metric(llm_metric):
    if not llm_metric:
        return []
    mapping = {
        # Emissions
        "Scope 1 and 2 Emissions": ["Scope1Emissions", "Scope2Emissions"],
        "scope1_and_scope2_emissions": ["Scope1Emissions", "Scope2Emissions"],
        "scope1_emissions": ["Scope1Emissions"],
        "Scope 1 Emissions": ["Scope1Emissions"],
        "scope2_emissions": ["Scope2Emissions"],
        "Scope 2 Emissions": ["Scope2Emissions"],
        "ghg_emissions": ["Scope1Emissions", "Scope2Emissions"],
        # Energy
        "EnergyConsumptionTotal": ["EnergyConsumptionTotal"],
        "energy_consumption": ["EnergyConsumptionTotal"],
        "total_energy_consumption": ["EnergyConsumptionTotal"],
        "Reduction in Global Power Consumption": ["EnergyConsumptionTotal"],
        "power_consumption": ["EnergyConsumptionTotal"],
        "EnergyConsumptionRenewable": ["EnergyConsumptionRenewable"],
        "Renewable Energy Consumption": ["EnergyConsumptionRenewable"],
        "renewable_energy_consumption": ["EnergyConsumptionRenewable"],
        "renewable_energy_share": ["EnergyConsumptionRenewable"],
        "EnergyConsumptionNonRenewable": ["EnergyConsumptionNonRenewable"],
        "non_renewable_energy_consumption": ["EnergyConsumptionNonRenewable"],
        # Water
        "water_consumption": ["WaterConsumptionTotal"],
        "total_water_consumption": ["WaterConsumptionTotal"],
        "WaterConsumptionTotal": ["WaterConsumptionTotal"],
        # Headcount
        "employee_headcount": ["TotalEmployees"],
        "total_employees": ["TotalEmployees"],
        "TotalEmployees": ["TotalEmployees"],
        # Specific mappings for the Infosys 2025-26 claims
        "surface_water": ["Surface Water Withdrawal"],
        "groundwater": ["Groundwater Withdrawal"],
        "third_party_water": ["Third-Party / Municipal Water"],
        "total_volume_of_water_withdrawal": ["Total Water Withdrawal"],
        "total_volume_of_water_withdrawal__i___ii___iii___iv___v_": ["Total Water Withdrawal"],
        "total_volume_of_water_consumption__in_kilolitres_": ["Total Water Consumption"],
        "total_water_discharged": ["Total Water Discharged"],
        "total_water_discharged__in_kilolitres_": ["Total Water Discharged"],
        "sent_to_third_parties___no_treatment": ["Water Discharged to Third Parties"],
        "total_scope_1_emissions__break_up_of_the_ghg_into_co2__ch4__n2o__hfcs__pfcs__sf6__nf3__if_available_": ["Scope 1 GHG Emissions"],
        "total_scope_1_emissions": ["Scope 1 GHG Emissions"],
        "total_scope_2_emissions__break_up_of_the_ghg_into_co2__ch4__n2o__hfcs__pfcs__sf6__nf3__if_available_": ["Scope 2 GHG Emissions"],
        "total_scope_2_emissions": ["Scope 2 GHG Emissions"],
        "total_scope_3_emissions__break_up_of_the_ghg_into_co2__ch4__n2o__hfcs__pfcs__sf6__nf3__if_available_": ["Scope 3 GHG Emissions"],
        "nox": ["NOx Air Emissions"],
        "sox": ["SOx Air Emissions"],
        "particulate_matter__pm_": ["Particulate Matter (PM)"],
        "total_electricity_consumption__a_": ["Renewable Electricity Consumption"],
        "total_fuel_consumption__b_": ["Renewable Fuel Consumption"],
        "total_energy_consumption__a___b___c_": ["Renewable Energy Consumption"],
        "total_electricity_consumption__d_": ["Non-Renewable Electricity Consumption"],
        "total_fuel_consumption__e_": ["Non-Renewable Fuel Consumption"],
        "total_energy_consumed_from_non_renewable_sources__d___e___f_": ["Non-Renewable Energy Consumption"],
        "total_energy_consumed__a___b___c___d___e___f_": ["Total Energy Consumption", "Renewable Energy Consumption", "Non-Renewable Energy Consumption"],
        "what_we_dispose_stays_out_of_landfills": ["Waste Diverted from Landfill"],
    }

    # Try exact match first
    if llm_metric in mapping:
        return mapping[llm_metric]
        
    # Then fuzzy match on keys
    cleaned = llm_metric.replace(" ", "").replace("_", "")
    for k, v in mapping.items():
        if k.replace(" ", "").replace("_", "").lower() == cleaned.lower():
            return v
            
    # Try substring match
    if "surface_water" in llm_metric: return ["Surface Water Withdrawal"]
    if "groundwater" in llm_metric: return ["Groundwater Withdrawal"]
    if "third_party_water" in llm_metric: return ["Third-Party / Municipal Water"]
    if "water_withdrawal" in llm_metric: return ["Total Water Withdrawal"]
    if "water_consumption" in llm_metric: return ["Total Water Consumption"]
    if "water_discharged" in llm_metric: return ["Total Water Discharged"]
    if "scope_1" in llm_metric: return ["Scope 1 GHG Emissions"]
    if "scope_2" in llm_metric: return ["Scope 2 GHG Emissions"]
    if "scope_3" in llm_metric: return ["Scope 3 GHG Emissions"]
    if "nox" in llm_metric: return ["NOx Air Emissions"]
    if "sox" in llm_metric: return ["SOx Air Emissions"]
    if "particulate_matter" in llm_metric: return ["Particulate Matter (PM)"]
    if "energy_consumed" in llm_metric: return ["Total Energy Consumption"]
    
    return [cleaned]

def map_period(llm_period):
    if not llm_period:
        return None
    p = str(llm_period).strip()
    mapping = {
        "FY22": "2021-22",
        "FY 2021-22": "2021-22",
        "FY2022": "2021-22",
        "2022": "2021-22",
        "FY21": "2020-21",
        "FY 2020-21": "2020-21",
        "FY2021": "2020-21",
        "2021": "2020-21",
        "FY23": "2022-23",
        "FY 2022-23": "2022-23",
        "FY24": "2023-24",
        "FY 2023-24": "2023-24",
        "2024": "2023-24",
        "FY25": "2024-25",
        "FY 2024-25": "2024-25",
        "Fiscal 2025": "2024-25",
        "2025": "2024-25",
        "FY26": "2025-26",
        "FY 2025-26": "2025-26",
        "Fiscal 2026": "2025-26",
        "2026": "2025-26",
    }
    return mapping.get(p, p)

def verify_claims():
    base_dir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    claims_path = os.path.join(base_dir, "data", "claims", "extracted_claims.json")
    db_path = os.path.join(base_dir, "data", "parsed", "brsr_facts.duckdb")
    output_path = os.path.join(base_dir, "data", "claims", "verified_claims.json")
    
    print(f"Connecting to DuckDB: {db_path}")
    if not os.path.exists(db_path):
        print("Error: Database not found. Run normalization first.")
        return
         
    con = duckdb.connect(db_path)
    claims = load_claims(claims_path)
    print(f"Loaded {len(claims)} claims for verification.")
    
    verified = []
    supported_count = 0
    inconsistent_count = 0
    incomparable_count = 0
    
    for claim in claims:
        metric_name = claim.get('metric', '')
        claim_id = claim.get('claim_id', 'UNKNOWN')
        op = claim.get('operation', 'value_equality')
        
        stated_raw = claim.get('asserted_value') if claim.get('asserted_value') is not None else claim.get('stated_result')
        if stated_raw is None:
            claim['verdict'] = "INCOMPARABLE"
            claim['reason'] = "No numerical asserted value in claim."
            verified.append(claim)
            incomparable_count += 1
            continue
            
        try:
            stated_result = float(stated_raw)
        except (ValueError, TypeError):
            claim['verdict'] = "INCOMPARABLE"
            claim['reason'] = f"Could not parse asserted value: {stated_raw}"
            verified.append(claim)
            incomparable_count += 1
            continue
            
        db_metrics = map_metric(metric_name)
        if not db_metrics:
            claim['verdict'] = "INCOMPARABLE"
            claim['reason'] = "Metric not mapped to taxonomy."
            verified.append(claim)
            incomparable_count += 1
            continue
            
        period_current = map_period(claim.get('current_period') or claim.get('period_current'))
        period_compare = map_period(claim.get('prior_period') or claim.get('period_compare'))
        
        # Calculate sum of metrics for current period
        val_current = 0
        c_unit = None
        missing_current = False
        
        for m in db_metrics:
            val, unit = get_fact_value(con, m, period_current)
            if val is None:
                missing_current = True
                break
            val_current += val
            c_unit = unit
            
        if missing_current:
            claim['verdict'] = "INCOMPARABLE"
            claim['reason'] = f"Metric '{metric_name}' (period: {period_current}) not found in XML database."
            verified.append(claim)
            incomparable_count += 1
            continue
            
        # For comparative operations, calculate prior period
        val_compare = 0
        missing_compare = False
        if op in ["absolute_change", "percentage_change"]:
            if not period_compare:
                claim['verdict'] = "INCOMPARABLE"
                claim['reason'] = "Comparative operation missing prior period."
                verified.append(claim)
                incomparable_count += 1
                continue
            for m in db_metrics:
                val, _ = get_fact_value(con, m, period_compare)
                if val is None:
                    missing_compare = True
                    break
                val_compare += val
            if missing_compare:
                claim['verdict'] = "INCOMPARABLE"
                claim['reason'] = f"Prior period '{period_compare}' data missing from XML database."
                verified.append(claim)
                incomparable_count += 1
                continue
                
        # Math Engine
        calculated_result = None
        if op == "value_equality":
            calculated_result = val_current
        elif op == "absolute_change":
            calculated_result = val_current - val_compare
        elif op == "percentage_change":
            if val_compare == 0:
                claim['verdict'] = "INCOMPARABLE"
                claim['reason'] = "Division by zero in baseline comparison."
                verified.append(claim)
                incomparable_count += 1
                continue
            calculated_result = ((val_current - val_compare) / val_compare) * 100
        else:
            claim['verdict'] = "INCOMPARABLE"
            claim['reason'] = f"Unknown operation: {op}"
            verified.append(claim)
            incomparable_count += 1
            continue
            
        # Unit Conversion
        claim_unit = claim.get('unit', '')
        conversion_msg = ""
        db_unit = c_unit or ""
        
        if op in ["absolute_change", "value_equality"]:
            if db_unit == "kL" and claim_unit in ["Liters", "L"]:
                calculated_result *= 1000
                conversion_msg = " [Converted kL to Liters]"
            elif db_unit == "tCO2e" and claim_unit in ["kgCO2e", "kg CO2e"]:
                calculated_result *= 1000
                conversion_msg = " [Converted tCO2e to kgCO2e]"
            elif db_unit == "GJ" and claim_unit in ["kWh", "MWh"]:
                if claim_unit == "kWh":
                    calculated_result *= 277.778
                    conversion_msg = " [Converted GJ to kWh]"
                else:
                    calculated_result *= 0.277778
                    conversion_msg = " [Converted GJ to MWh]"

        # Compare using relative tolerance (1%) or absolute tolerance (0.5)
        abs_diff = abs(abs(calculated_result) - abs(stated_result))
        is_supported = False
        
        if abs_diff <= 0.5:
            is_supported = True
        elif stated_result != 0 and (abs_diff / abs(stated_result)) <= 0.01:
            is_supported = True
            
        if is_supported:
            claim['verdict'] = "SUPPORTED"
            claim['reason'] = f"Calculated {calculated_result:.2f} matches claimed {stated_result} (Tolerance: 0.5/1%).{conversion_msg}"
            supported_count += 1
            print(f"  [SUPPORTED] [{claim_id}] {metric_name}: Calc={calculated_result:.2f} Stated={stated_result}")
        else:
            claim['verdict'] = "INCONSISTENT"
            claim['reason'] = f"Calculated {calculated_result:.2f} does not match claimed {stated_result}.{conversion_msg}"
            inconsistent_count += 1
            print(f"  [INCONSISTENT] [{claim_id}] {metric_name}: Calc={calculated_result:.2f} Stated={stated_result}")
            
        claim['math_trace'] = {
            'value_current': val_current,
            'value_compare': val_compare if op != "value_equality" else None,
            'calculated_result': calculated_result
        }
        verified.append(claim)
        
    save_verified_claims(verified, output_path)
    print(f"\n{'=' * 60}")
    print("VERIFICATION SUMMARY")
    print(f"{'=' * 60}")
    print(f"Total Claims Analyzed: {len(claims)}")
    print(f"SUPPORTED (Verified Fact): {supported_count}")
    print(f"INCONSISTENT (Discrepancy/Dispute): {inconsistent_count}")
    print(f"INCOMPARABLE / UNMAPPED: {incomparable_count}")
    print(f"Saved verified claims to: {output_path}")
    print(f"{'=' * 60}\n")

if __name__ == "__main__":
    verify_claims()

