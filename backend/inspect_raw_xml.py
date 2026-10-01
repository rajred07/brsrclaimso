import os
import sys
from bs4 import BeautifulSoup
import json

def inspect_xml(xml_path):
    print(f"Reading: {xml_path}")
    with open(xml_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print(f"File size: {len(content):,} characters")
    soup = BeautifulSoup(content, 'xml')

    # 1. Namespaces and Schema
    schema_refs = [s.get('xlink:href') for s in soup.find_all('schemaRef')]
    print(f"Schema References: {schema_refs}")

    # 2. Contexts and Periods
    contexts = {}
    periods = set()
    for ctx in soup.find_all('context'):
        ctx_id = ctx.get('id')
        p = "unknown"
        if ctx.find('instant'):
            p = f"Instant: {ctx.find('instant').text}"
        elif ctx.find('startDate') and ctx.find('endDate'):
            p = f"Duration: {ctx.find('startDate').text} to {ctx.find('endDate').text}"
        contexts[ctx_id] = p
        periods.add(p)
    print(f"\nTotal Contexts: {len(contexts)}")
    print(f"Unique Periods: {periods}")

    # 3. Units
    units = {}
    for u in soup.find_all('unit'):
        uid = u.get('id')
        measure = u.find('measure')
        units[uid] = measure.text if measure else "unknown"
    print(f"\nUnits declared: {units}")

    # 4. Find all tags that have contextRef (these are actual XBRL Facts!)
    facts = []
    text_disclosures = []
    numeric_facts = []

    for tag in soup.find_all(True):
        if tag.has_attr('contextRef'):
            tag_name = tag.name
            ctx_id = tag.get('contextRef')
            unit_ref = tag.get('unitRef', '')
            val = tag.text.strip()
            
            # Check if numeric
            is_num = False
            clean_num = None
            try:
                clean_num = float(val.replace(',', ''))
                is_num = True
            except ValueError:
                pass

            fact_info = {
                "tag": tag_name,
                "context": ctx_id,
                "period": contexts.get(ctx_id, "unknown"),
                "unit": units.get(unit_ref, unit_ref),
                "value": clean_num if is_num else val,
                "is_numeric": is_num
            }

            facts.append(fact_info)
            if is_num:
                numeric_facts.append(fact_info)
            else:
                text_disclosures.append(fact_info)

    print(f"\nTotal XBRL Facts in file: {len(facts)}")
    print(f"Numeric quantitative facts: {len(numeric_facts)}")
    print(f"Textual disclosures & booleans: {len(text_disclosures)}")

    # 5. Look specifically for core ESG keywords in tag names
    esg_keywords = ['energy', 'emission', 'ghg', 'scope', 'water', 'waste', 'electricity', 'fuel', 'renewable', 'carbon', 'effluent', 'turnover', 'employee']
    found_esg = {}
    for nf in numeric_facts:
        tag_lower = nf['tag'].lower()
        for kw in esg_keywords:
            if kw in tag_lower:
                if kw not in found_esg:
                    found_esg[kw] = []
                found_esg[kw].append({
                    "tag": nf['tag'],
                    "period": nf['period'],
                    "value": nf['value'],
                    "unit": nf['unit']
                })
                break

    print("\n================== CORE ESG METRICS FOUND ==================")
    for kw, items in found_esg.items():
        print(f"\n[{kw.upper()}] ({len(items)} facts):")
        # Print top 6 representative items
        for it in items[:6]:
            print(f"  • {it['tag']}: {it['value']} {it['unit']} ({it['period']})")

if __name__ == "__main__":
    xml_path = sys.argv[1] if len(sys.argv) > 1 else r"data\filings\infosys--202425-7178\brsr_BRSR_1477079_03072025095250_WEB.xml"
    inspect_xml(xml_path)
