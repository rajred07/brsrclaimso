import fitz
import json
import os
import sys

def chunk_pdf(pdf_path, target_pages=None):
    print(f"Reading PDF: {pdf_path}...")
    doc = fitz.open(pdf_path)
    
    batches = []
    
    # If target pages are provided, only extract those specific pages
    if target_pages:
        print(f"Targeting specific pages: {target_pages}")
        for page_num in target_pages:
            # PyMuPDF is 0-indexed, so page 41 is doc[40]
            actual_index = page_num - 1
            if actual_index < 0 or actual_index >= len(doc):
                continue
            
            page = doc[actual_index]
            text = f"--- Page {page_num} ---\n{page.get_text()}"
            
            batches.append({
                "batch_id": len(batches) + 1,
                "start_page": page_num,
                "end_page": page_num,
                "text": text
            })
    else:
        # Fallback to chunking the whole PDF if no targets provided
        current_batch_text = ""
        start_page = 1
        batch_size = 5
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            current_batch_text += f"\n--- Page {page_num + 1} ---\n{text}"
            
            if (page_num + 1) % batch_size == 0 or page_num == len(doc) - 1:
                batches.append({
                    "batch_id": len(batches) + 1,
                    "start_page": start_page,
                    "end_page": page_num + 1,
                    "text": current_batch_text
                })
                current_batch_text = ""
                start_page = page_num + 2
                
    print(f"Created {len(batches)} target batches.")
    return batches

if __name__ == "__main__":
    # If user provides a PDF path via CLI, use it. Otherwise default.
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else "infosys_target_pages.pdf"
    
    if not os.path.exists(pdf_path):
        print(f"[!] Error: Could not find {pdf_path}.")
        print("Please place the PDF in the correct location or pass the path as an argument.")
        sys.exit(1)
            
    # Phase 7: Extract text from the small PDF
    batches = chunk_pdf(pdf_path, target_pages=None)
    
    # Save the output of this phase
    os.makedirs("data/processed", exist_ok=True)
    out_path = "data/processed/batches.json"
    
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(batches, f, indent=2)
        
    print(f"Successfully saved batched text artifacts to '{out_path}'")
