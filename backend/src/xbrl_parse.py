import os
import sys
import json
import duckdb
import pandas as pd
from bs4 import BeautifulSoup

def parse_xbrl_bs4(instance_path, output_csv, duckdb_path, dictionary_path):
    print(f"Loading XBRL Instance: {instance_path}...")
    
    try:
        with open(instance_path, 'r', encoding='utf-8') as f:
            content = f.read()
        soup = BeautifulSoup(content, 'xml')
    except Exception as e:
        print(f"Error reading file: {e}")
        return []

    # Load Concept Dictionary
    concept_map = {}
    if os.path.exists(dictionary_path):
        df_map = pd.read_csv(dictionary_path)
        for _, row in df_map.iterrows():
            concept_map[row['taxonomy_concept']] = row['canonical_metric_name']
            
    # Parse contexts first to resolve period and entity
    contexts = {}
    for ctx in soup.find_all('context'):
        ctx_id = ctx.get('id')
        
        # Period
        period = "unknown"
        if ctx.find('instant'):
            period = ctx.find('instant').text
        elif ctx.find('startDate') and ctx.find('endDate'):
            period = f"{ctx.find('startDate').text} to {ctx.find('endDate').text}"
            
        # Entity
        entity = "Unknown"
        identifier = ctx.find('identifier')
        if identifier:
            entity = identifier.text
            
        # Dimensions
        dims = {}
        for explicit in ctx.find_all('explicitMember'):
            dim = explicit.get('dimension', '').split(':')[-1]
            member = explicit.text.split(':')[-1]
            dims[dim] = member
            
        for typed in ctx.find_all('typedMember'):
            dim = typed.get('dimension', '').split(':')[-1]
            member = typed.text
            dims[dim] = member

        contexts[ctx_id] = {
            'entity': entity,
            'period': period,
            'dimensions': json.dumps(dims)
        }

    # Parse facts
    print("Extracting facts...")
    facts_list = []
    
    # We look for all tags that have a 'contextRef' attribute (which identifies them as facts)
    for tag in soup.find_all(True):
        ctx_ref = tag.get('contextRef')
        if ctx_ref and ctx_ref in contexts:
            # tag.name gives the concept name
            concept_qname = tag.name
            
            # Skip pure XBRL technical concepts or empty values
            if not tag.text.strip():
                continue
                
            canonical_name = concept_map.get(concept_qname, concept_qname)
            value = tag.text.strip()
            unit = tag.get('unitRef', None)
            decimals = tag.get('decimals', None)
            
            ctx_data = contexts[ctx_ref]
            
            facts_list.append({
                "company": ctx_data['entity'],
                "fy": ctx_data['period'], 
                "concept_qname": concept_qname,
                "canonical_name": canonical_name,
                "value": value,
                "unit": unit,
                "decimals": decimals,
                "period": ctx_data['period'],
                "dimensions": ctx_data['dimensions'],
                "source_file": os.path.basename(instance_path)
            })

    print(f"Extracted {len(facts_list)} facts.")
    
    if not facts_list:
        return []

    # Export to CSV
    os.makedirs(os.path.dirname(output_csv), exist_ok=True)
    df_facts = pd.DataFrame(facts_list)
    df_facts.to_csv(output_csv, index=False)
    print(f"Saved to CSV: {output_csv}")
    
    # Export to DuckDB
    os.makedirs(os.path.dirname(duckdb_path), exist_ok=True)
    con = duckdb.connect(duckdb_path)
    
    tables = con.execute("SHOW TABLES").fetchall()
    table_names = [t[0] for t in tables]
    
    if 'brsr_facts' in table_names:
        con.execute("INSERT INTO brsr_facts SELECT * FROM df_facts")
    else:
        con.execute("CREATE TABLE brsr_facts AS SELECT * FROM df_facts")
        
    print(f"Appended to DuckDB: {duckdb_path}")
    con.close()
    
    return facts_list

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python xbrl_parse.py <path_to_xbrl_file.xml>")
        sys.exit(1)
        
    instance_path = sys.argv[1]
    symbol = os.path.basename(instance_path).split('.')[0]
    output_csv = f"../data/parsed/{symbol}_facts.csv"
    duckdb_path = f"../data/parsed/brsr_facts.duckdb"
    dictionary_path = "../configs/concept_dictionary.csv"
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    instance_path = os.path.abspath(instance_path)
    output_csv = os.path.abspath(os.path.join(script_dir, output_csv))
    duckdb_path = os.path.abspath(os.path.join(script_dir, duckdb_path))
    dictionary_path = os.path.abspath(os.path.join(script_dir, dictionary_path))
    
    parse_xbrl_bs4(instance_path, output_csv, duckdb_path, dictionary_path)
