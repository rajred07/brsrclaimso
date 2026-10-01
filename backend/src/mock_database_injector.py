import os
import duckdb
import xml.etree.ElementTree as ET

def inject_mock_data():
    base_dir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    xml_path = os.path.join(base_dir, "data", "demo", "ecocorp_brsr.xml")
    db_path = os.path.join(base_dir, "data", "parsed", "brsr_facts.duckdb")
    
    print(f"Injecting mock data from {xml_path} into {db_path}...")
    
    # Ensure DuckDB table exists
    con = duckdb.connect(db_path)
    con.execute("""
        CREATE TABLE IF NOT EXISTS normalized_facts (
            company VARCHAR,
            period VARCHAR,
            canonical_name VARCHAR,
            value DOUBLE,
            unit VARCHAR,
            source_file VARCHAR
        )
    """)
    
    # Clear out any old EcoCorp data to prevent duplicates
    con.execute("DELETE FROM normalized_facts WHERE company = 'ECOCORP'")
    
    tree = ET.parse(xml_path)
    root = tree.getroot()
    
    # namespaces
    ns = {
        'xbrli': 'http://www.xbrl.org/2003/instance',
        'in-brsr': 'https://www.sebi.gov.in/xbrl/2022-03-31/in-brsr'
    }
    
    for child in root:
        # Ignore contexts and units for the simple injector
        if 'in-brsr' in child.tag:
            canonical_name = child.tag.split('}')[-1]
            value = float(child.text)
            context = child.get('contextRef')
            unit = child.get('unitRef')
            
            con.execute(
                "INSERT INTO normalized_facts VALUES (?, ?, ?, ?, ?, ?)", 
                ('ECOCORP', context, canonical_name, value, unit, 'ecocorp_brsr.xml')
            )
            print(f"Inserted: {canonical_name} ({context}) = {value} {unit}")

    print("\nMock data successfully injected into Database!")
    con.close()

if __name__ == "__main__":
    inject_mock_data()
