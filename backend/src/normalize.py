import duckdb
import pandas as pd
import os
import re

def normalize_facts(db_path, dictionary_path):
    print("Connecting to database...")
    con = duckdb.connect(db_path)
    
    # Load raw facts
    raw_facts = con.execute("SELECT * FROM brsr_facts").df()
    
    # Load concept dictionary
    concept_map = pd.read_csv(dictionary_path)
    # Filter out empty canonical names
    concept_map = concept_map[concept_map['canonical_metric_name'].notna()]
    
    # Create mapping dictionaries
    qname_to_canonical = dict(zip(concept_map['taxonomy_concept'], concept_map['canonical_metric_name']))
    canonical_to_standard_unit = dict(zip(concept_map['canonical_metric_name'], concept_map['unit_type']))
    
    normalized_list = []
    
    for _, row in raw_facts.iterrows():
        qname = row['concept_qname']
        
        # Only process facts that are in our dictionary!
        if qname in qname_to_canonical:
            canonical = qname_to_canonical[qname]
            standard_unit = canonical_to_standard_unit[canonical]
            
            val = str(row['value']).replace(',', '').strip()
            
            # Remove parentheses for negatives (e.g., "(500)" -> "-500")
            if val.startswith('(') and val.endswith(')'):
                val = "-" + val[1:-1]
                
            try:
                numeric_val = float(val)
            except ValueError:
                # If we can't parse it as float, skip or keep as string
                continue
                
            # Here we would stitch units, but for now we just use the standard unit 
            # defined in our dictionary because SEBI's unit separation is too messy.
            # E.g. we KNOW Scope1 is tCO2e.
            
            normalized_list.append({
                "company": row['company'],
                "period": row['period'],
                "canonical_name": canonical,
                "value": numeric_val,
                "unit": standard_unit,
                "source_file": row['source_file']
            })

    if not normalized_list:
        print("No facts normalized. Did you add concepts to the dictionary?")
        return
        
    df_normalized = pd.DataFrame(normalized_list)
    
    # Save back to DuckDB
    con.execute("DROP TABLE IF EXISTS normalized_facts")
    con.execute("CREATE TABLE normalized_facts AS SELECT * FROM df_normalized")
    print(f"Successfully normalized {len(df_normalized)} core ESG facts!")
    
    # Also save to CSV for human review
    out_csv = os.path.join(os.path.dirname(db_path), "normalized_facts.csv")
    df_normalized.to_csv(out_csv, index=False)
    print(f"Saved normalized CSV to {out_csv}")
    
    con.close()

if __name__ == "__main__":
    db = os.path.abspath(os.path.join(os.path.dirname(__file__), "../data/parsed/brsr_facts.duckdb"))
    dict_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../configs/concept_dictionary.csv"))
    normalize_facts(db, dict_path)
