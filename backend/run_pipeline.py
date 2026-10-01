import os
import subprocess
import sys

def run_script(script_args):
    # script_args can be a string (just the path) or a list (path + args)
    if isinstance(script_args, str):
        args_list = [script_args]
    else:
        args_list = script_args
        
    script_path = args_list[0]
    
    print(f"\n{'='*60}\n-> Running Phase: {script_path}\n{'='*60}")
    
    # We use sys.executable to ensure it runs in the same virtual environment
    cmd = [sys.executable] + args_list
    result = subprocess.run(cmd)
    
    if result.returncode != 0:
        print(f"\n[!] Pipeline halted: {script_path} failed with exit code {result.returncode}.")
        sys.exit(result.returncode)

if __name__ == "__main__":
    print("Starting VeriBRSR Multi-Phase Backend Pipeline...\n")
    
    # Run Phase 7 (PDF Ingestion)
    pdf_path = "data/raw/uploaded.pdf"
    fallback_pdf = "../infosys-esg-report-2021-22.pdf"
    
    if os.path.exists(pdf_path):
        print(f"Using dynamically uploaded PDF: {pdf_path}")
        run_script(["src/ingest.py", pdf_path])
    elif os.path.exists(fallback_pdf):
        print(f"Using fallback PDF: {fallback_pdf}")
        run_script(["src/ingest.py", fallback_pdf])
    else:
        # Let ingest.py use its own internal fallback (target pages)
        run_script("src/ingest.py")
    
    # Run Phase 8
    run_script("src/extract_claims.py")
    
    # Run Phase 4 (XBRL Parsing)
    xml_path = "data/raw/uploaded.xml"
    fallback_xml = "data/raw/infosys_brsr_2022.xml"
    
    if os.path.exists(xml_path):
        print(f"Using dynamically uploaded XML: {xml_path}")
        run_script(["src/xbrl_parse.py", xml_path])
    elif os.path.exists(fallback_xml):
        print(f"Using fallback XML: {fallback_xml}")
        run_script(["src/xbrl_parse.py", fallback_xml])
    else:
        print(f"\n[!] Skipping XBRL Parsing: Could not find any XML")
        
    # Run Phase 5a (Normalization)
    run_script("src/normalize.py")
    
    # Run Phase 5b (Verification Engine)
    run_script("src/verify_engine.py")
    
    print("\n" + "="*60)
    print("PIPELINE COMPLETE!")
    print("Artifacts saved to:")
    print("  - Batched text: data/processed/batches.json")
    print("  - Extracted Claims: data/claims/extracted_claims.json")
    print("  - Raw XML Facts: data/parsed/")
    print("  - Normalized Database: data/parsed/brsr_facts.duckdb")
    print("  - Final Verified Output: data/claims/verified_claims.json")
    print("="*60 + "\n")
