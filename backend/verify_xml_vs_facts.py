import json
from pathlib import Path
from bs4 import BeautifulSoup

xml_file = Path("data/filings/infosys--202425-7178/brsr_BRSR_1477079_03072025095250_WEB.xml")
facts_file = Path("data/filings/infosys--202425-7178/facts.json")

print(f"Reading XML: {xml_file}")
print(f"Reading Facts JSON: {facts_file}")

with open(xml_file, "r", encoding="utf-8") as f:
    soup = BeautifulSoup(f.read(), "xml")

with open(facts_file, "r", encoding="utf-8") as f:
    facts = json.load(f)

# Resolve XML Contexts
contexts = {}
for ctx in soup.find_all("context"):
    cid = ctx.get("id")
    p = "Unknown"
    if ctx.find("instant"):
        p = ctx.find("instant").text
    elif ctx.find("startDate") and ctx.find("endDate"):
        p = f"{ctx.find('startDate').text} to {ctx.find('endDate').text}"
    dims = {}
    for em in ctx.find_all("explicitMember"):
        dim = em.get("dimension", "").split(":")[-1]
        val = em.text.split(":")[-1]
        dims[dim] = val
    contexts[cid] = {"period": p, "dims": dims}

# Key core ESG facts to spot-check & verify 1-to-1
test_concepts = [
    "TotalEnergyConsumedFromRenewableAndNonRenewableSources",
    "TotalEnergyConsumedFromRenewableSources",
    "TotalEnergyConsumedFromNonRenewableSources",
    "TotalElectricityConsumptionFromRenewableSources",
    "TotalElectricityConsumptionFromNonRenewableSources",
    "TotalFuelConsumptionFromNonRenewableSources",
    "TotalVolumeOfWaterWithdrawal",
    "TotalVolumeOfWaterConsumption",
    "TotalScope1Emissions",
    "TotalScope2Emissions",
    "TotalScope3Emissions",
    "TotalWasteGenerated",
    "TotalWasteRecovered",
    "TotalWasteDisposed",
    "PlasticWaste",
    "EWaste",
    "RevenueFromOperations",
    "TurnoverRate"
]

print("=" * 80)
print(f"1-TO-1 CROSS-VERIFICATION: RAW XML vs FACTS.JSON ({len(facts)} total facts)")
print("=" * 80)

verified_count = 0
discrepancies = 0

for concept in test_concepts:
    matching_facts = [f for f in facts if f.get("base_concept") == concept]
    matching_xml = [t for t in soup.find_all(True) if t.name and (t.name == concept or t.name.split(":")[-1] == concept)]

    print(f"\n--- Checking Concept: {concept} ---")
    print(f"    Found {len(matching_xml)} XML tags, {len(matching_facts)} facts.json entries")

    for f_item in matching_facts:
        f_val = f_item["value"]
        f_period = f_item["raw_period"]
        f_dims = json.loads(f_item["dimensions"]) if f_item["dimensions"] else {}

        # Find corresponding XML tag
        matched_xml_tag = None
        for tag in matching_xml:
            c_info = contexts.get(tag.get("contextRef"), {})
            if c_info.get("period") == f_period and c_info.get("dims") == f_dims:
                matched_xml_tag = tag
                break

        if matched_xml_tag:
            raw_xml_text = matched_xml_tag.text.strip().replace(",", "")
            raw_float = float(raw_xml_text)
            
            # Unit check (if percentage e.g. 0.141 -> 14.1)
            expected_val = f_val
            if f_item["unit"] == "%" and 0.0 < raw_float <= 1.0:
                raw_float = round(raw_float * 100.0, 2)

            is_match = abs(raw_float - expected_val) < 1e-4
            if is_match:
                verified_count += 1
                print(f"    [MATCH OK] {f_item['canonical_name']} ({f_item['period']}):")
                print(f"               XML Raw: {matched_xml_tag.text.strip()} | facts.json: {f_val} {f_item['unit']}")
            else:
                discrepancies += 1
                print(f"    [MISMATCH!] XML: {raw_float} != facts.json: {f_val}")
        else:
            print(f"    [!] Context not strictly aligned for: {f_item['canonical_name']}")

print("\n" + "=" * 80)
print(f"CROSS-VERIFICATION SUMMARY:")
print(f"  Total Checked Core Concepts: {len(test_concepts)}")
print(f"  Exact Value Matches:         {verified_count}")
print(f"  Discrepancies / Errors:      {discrepancies}")
print("=" * 80)
