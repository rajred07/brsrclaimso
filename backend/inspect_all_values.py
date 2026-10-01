import json
from pathlib import Path
from bs4 import BeautifulSoup

xml_file = Path("data/filings/infosys--202425-7178/brsr_BRSR_1477079_03072025095250_WEB.xml")
with open(xml_file, "r", encoding="utf-8") as f:
    soup = BeautifulSoup(f.read(), "xml")

contexts = {}
for ctx in soup.find_all("context"):
    cid = ctx.get("id")
    p = "Unknown"
    if ctx.find("instant"):
        p = ctx.find("instant").text
    elif ctx.find("startDate") and ctx.find("endDate"):
        p = f"{ctx.find('startDate').text} to {ctx.find('endDate').text}"
    dims = [em.text.split(":")[-1] for em in ctx.find_all("explicitMember")]
    contexts[cid] = {"p": p, "dims": dims}

units = {}
for u in soup.find_all("unit"):
    uid = u.get("id")
    m = u.find("measure")
    units[uid] = m.text if m else uid

key_tags = [
    # Energy
    ("Total Energy Consumed (Renewable + Non-Renewable)", "TotalEnergyConsumedFromRenewableAndNonRenewableSources"),
    ("Total Energy Consumed from Renewable Sources", "TotalEnergyConsumedFromRenewableSources"),
    ("Total Energy Consumed from Non-Renewable Sources", "TotalEnergyConsumedFromNonRenewableSources"),
    ("Renewable Electricity Consumption", "TotalElectricityConsumptionFromRenewableSources"),
    ("Grid Electricity Consumption", "TotalElectricityConsumptionFromNonRenewableSources"),
    ("Renewable Fuel Consumption", "TotalFuelConsumptionFromRenewableSources"),
    ("Non-Renewable Fuel Consumption", "TotalFuelConsumptionFromNonRenewableSources"),
    ("Energy Intensity per Rupee of Turnover", "EnergyIntensityPerRupeeOfTurnover"),
    # Water
    ("Total Volume of Water Withdrawal", "TotalVolumeOfWaterWithdrawal"),
    ("Total Volume of Water Consumption", "TotalVolumeOfWaterConsumption"),
    ("Water Intensity per Rupee of Turnover", "WaterIntensityPerRupeeOfTurnover"),
    # Emissions
    ("Total Scope 1 GHG Emissions", "TotalScope1Emissions"),
    ("Total Scope 2 GHG Emissions", "TotalScope2Emissions"),
    ("Total Scope 3 GHG Emissions", "TotalScope3Emissions"),
    ("Scope 1+2 Emissions Intensity per Turnover", "TotalScope1AndScope2EmissionsIntensityPerRupeeOfTurnover"),
    # Waste
    ("Total Waste Generated", "TotalWasteGenerated"),
    ("Total Waste Recovered", "TotalWasteRecovered"),
    ("Total Waste Disposed", "TotalWasteDisposed"),
    ("Plastic Waste", "PlasticWaste"),
    ("E-Waste", "EWaste"),
    # Workforce
    ("Total Workforce / Employees & Workers", "NumberOfEmployeesOrWorkersIncludingDifferentlyAbled"),
    ("Voluntary Attrition / Turnover Rate", "TurnoverRate"),
    # Financial & CSR
    ("Revenue / Turnover", "RevenueFromOperations"),
    ("Amount Spent on CSR", "AmountSpentOnCSR")
]

print("=" * 80)
print("EXTRACTED EVIDENCE FROM 2024-25 RAW XML (Infosys)")
print("=" * 80)

found_summary = {}
for label, tag_name in key_tags:
    matching = [t for t in soup.find_all(True) if t.name and (t.name.endswith(":" + tag_name) or t.name == tag_name)]
    items = []
    for m in matching:
        val = m.text.strip().replace(",", "")
        ctx = contexts.get(m.get("contextRef"), {})
        unit = units.get(m.get("unitRef", ""), m.get("unitRef", ""))
        dims = ctx.get("dims", [])
        items.append({
            "val": val,
            "unit": unit,
            "period": ctx.get("p", ""),
            "dims": dims
        })
    found_summary[label] = items

for label, items in found_summary.items():
    print(f"\n[METRIC] {label}:")
    if not items:
        print("   (Not found in XML)")
        continue
    for it in items:
        dim_str = f" | Breakdown: {', '.join(it['dims'])}" if it['dims'] else " | [TOTAL]"
        print(f"   -> Value: {it['val']} {it['unit']} | Period: {it['period']}{dim_str}")

with open("raw_xml_extracted_summary.json", "w", encoding="utf-8") as out_f:
    json.dump(found_summary, out_f, indent=2)
print("\n[OK] Saved to raw_xml_extracted_summary.json")
