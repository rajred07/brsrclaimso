"""PyMuPDF page selection and LLM extraction; no numerical verification here."""
import json
import re
from pathlib import Path

import pymupdf

from .llm import ROOT, JSONClient
from .matcher import metric_key
from .verifier import OPERATIONS
from .units import number

FIELDS = {"claim_id", "company", "reporting_year", "page_number", "source_sentence", "metric",
          "operation", "asserted_value", "unit", "current_period", "previous_period", "boundary",
          "is_target", "extraction_confidence"}


def page_numbers(spec, total):
    if not spec:
        raise ValueError("An explicit BRSR page range is required")
    pages = set()
    for part in str(spec).split(","):
        if not re.fullmatch(r"\s*\d+(?:\s*-\s*\d+)?\s*", part):
            raise ValueError(f"Invalid page range: {part}")
        ends = [int(n.strip()) for n in part.split("-")]
        first, last = ends[0], ends[-1]
        if first < 1 or last > total or first > last:
            raise ValueError("Page ranges must be ascending, 1-based PDF page numbers")
        pages.update(range(first, last + 1))
    return sorted(pages)


def compact(text):
    return " ".join(str(text).split())


def extract_batch(filing, ranges, config, output, context_pages=None):
    """One bounded request per filing, with per-page source validation."""
    client = JSONClient(config)
    with pymupdf.open(ROOT / filing['pdf_path_or_url']) as pdf:
        pages = {n: pdf[n-1].get_text() for n in page_numbers(ranges, len(pdf))}
        context = '\n'.join(f'[PDF page {n}]\n{pdf[n-1].get_text()}'
                            for n in page_numbers(context_pages, len(pdf))) if context_pages else ''
    instruction = (ROOT / config['prompts']['extraction']).read_text(encoding='utf-8')
    instruction += ('\nExtract approximately SIX claims for this filing. Prefer current-year whole-company '
                    'water, energy, Scope 1, Scope 2, waste totals, then one explicitly printed employee total '
                    'or previous-year water total. Do not sum waste components or energy components. '
                    'Copy exact contiguous rows containing the numbers; no ellipses or rewritten sentences. '
                    'The metadata page_number is selected from the supplied PDF page markers. '
                    'Use fiscal table headers together with the explicit financial-year context. '
                    'Do not extract intensity, subtotal, targets, or derive changes from tables.')
    prompt = instruction + '\nMETADATA:\n' + json.dumps({k: filing[k] for k in ('filing_id','company','reporting_year')})
    prompt += '\nEXPLICIT PDF CONTEXT:\n' + context
    prompt += '\nSELECTED PAGES:\n' + '\n'.join(f'[PDF page {n}]\n{text}' for n,text in pages.items())
    items, run = client.generate(prompt, 'filing_batch_extraction')
    if not isinstance(items, list):
        raise ValueError('Batch extraction must return an array')
    records, rejected = [], []
    for index, item in enumerate(items):
        page = item.get('page_number')
        try:
            if page not in pages:
                raise ValueError('Source page was not selected')
            claim = validate_claim(item, filing, page, pages[page])
        except (ValueError, TypeError) as error:
            rejected.append({'item_index': index, 'error': str(error), 'item': item})
            continue  # archive rejection; never repair source text by inventing it
        claim.update(claim_id=f"{filing['filing_id']}-p{page:04d}-{len(records)+1:03d}",
                     page=page, extraction_run_id=run['run_id'], extraction_item_index=index,
                     pdf_context=context+'\n'+pages[page])
        records.append(claim)
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding='utf-8')
    Path(str(output)+'.runs.json').write_text(json.dumps({'run':run,'rejected':rejected},indent=2),encoding='utf-8')
    return records


def validate_claim(claim, filing, page_number=None, page_text=None):
    if not isinstance(claim, dict) or not FIELDS.issubset(claim):
        raise ValueError("LLM claim is missing required fields")
    if claim["company"] != filing["company"] or claim["reporting_year"] != filing["reporting_year"]:
        raise ValueError("LLM changed filing metadata")
    if page_number is not None and claim["page_number"] != page_number:
        raise ValueError("LLM changed PDF page provenance")
    if not claim.get("source_sentence") or (page_text is not None and compact(claim["source_sentence"]) not in compact(page_text)):
        raise ValueError("Source sentence is not a contiguous passage from the PDF page")
    if metric_key(claim["metric"]) is None or claim["operation"] not in OPERATIONS:
        raise ValueError("Metric or operation is outside the research scope")
    if claim["asserted_value"] is not None:
        asserted = number(claim["asserted_value"])
        if claim["operation"] != "direction_of_change":
            printed = [number(m[0]) for m in re.finditer(r"(?<![\w.])[+-]?\d[\d,]*(?:\.\d+)?(?![\w.])", claim["source_sentence"])]
            if abs(asserted) not in {abs(n) for n in printed}:
                raise ValueError("Asserted magnitude does not occur in the source; extraction must not calculate it")
    if claim["is_target"] is not None and not isinstance(claim["is_target"], bool):
        raise ValueError("is_target must be boolean or null")
    confidence = claim["extraction_confidence"]
    if confidence is not None and (isinstance(confidence, bool) or not 0 <= float(confidence) <= 1):
        raise ValueError("extraction_confidence must be in [0,1] or null")
    return {**claim, "filing_id": filing["filing_id"]}


def extract_pdf(filing, ranges, config, output, context_pages=None):
    client = JSONClient(config)
    prompt = (ROOT / config["prompts"]["extraction"]).read_text(encoding="utf-8")
    claims, runs = [], []
    with pymupdf.open(ROOT / filing["pdf_path_or_url"]) as document:
        selected = page_numbers(ranges, len(document))
        context = "\n".join(f"[PDF page {n}]\n{document[n-1].get_text()}"
                            for n in page_numbers(context_pages, len(document))) if context_pages else ""
        for page in selected:
            text = document[page - 1].get_text()
            if not text.strip():
                raise ValueError(f"PDF page {page} has no text layer; OCR/manual extraction is required")
            metadata = {k: filing[k] for k in ("filing_id", "company", "reporting_year")}
            metadata["page_number"] = page
            page_prompt = prompt + "\nMETADATA:\n" + json.dumps(metadata) + "\nEXPLICIT PDF CONTEXT:\n" + context + "\nPAGE TEXT:\n" + text
            result, run = client.generate(page_prompt, "extraction")
            if not isinstance(result, list):
                raise ValueError("Extraction response must be a JSON array")
            try:
                for item in result:
                    validate_claim(item, filing, page, text)
            except ValueError as error:
                # One bounded provenance/schema repair using only the same PDF.
                # Invalid responses remain in the raw run archive for audit.
                repair = ("\nVALIDATION ERROR: " + str(error) +
                          "\nRetry this page once. Copy a single contiguous row/passage containing the asserted number. "
                          "Do not join separate spans, insert ellipses, rewrite rows into sentences, or add unit/header text "
                          "inside the source_sentence. Metric/unit/year may come from explicit table headers. "
                          "If no faithful passage is available, omit the claim. Return the complete valid JSON array.")
                result, run = client.generate(page_prompt + repair, "extraction_repair")
                if not isinstance(result, list):
                    raise ValueError("Repair response must be a JSON array")
                for item in result:
                    validate_claim(item, filing, page, text)
            for item_index, item in enumerate(result):
                record = validate_claim(item, filing, page, text)
                record["claim_id"] = f"{filing['filing_id']}-p{page:04d}-{len(claims)+1:03d}"
                record["extraction_run_id"] = run["run_id"]
                record["extraction_item_index"] = item_index
                record["pdf_context"] = context + "\n" + text
                claims.append(record)
            runs.append({"page": page, **run})
            # Checkpoint validated claims so a later quota failure loses no successful pages.
            Path(output).parent.mkdir(parents=True, exist_ok=True)
            Path(output).write_text(json.dumps(claims, indent=2, ensure_ascii=False), encoding="utf-8")
    Path(str(output) + ".runs.json").write_text(json.dumps(runs, indent=2), encoding="utf-8")
    return claims


def interpret_statement(claim, filing, config, client=None):
    client = client or JSONClient(config)
    # Natural claims already extracted by this LLM need no second interpretation.
    # Reconstruct the exact item from the recorded raw response, not manual/gold
    # interpretation fields. Perturbations always need fresh interpretation.
    run_id, item_index = claim.get("extraction_run_id"), claim.get("extraction_item_index")
    if run_id and item_index is not None and not claim.get("perturbation_id"):
        path = ROOT / config["llm"]["cache_directory"] / f"{run_id}.json"
        if path.exists():
            record = json.loads(path.read_text(encoding="utf-8"))
            if record["settings"]["model"] == config["llm"]["model"]:
                item = json.loads(record["text"])[item_index]
                if compact(item["source_sentence"]) == compact(claim["source_sentence"]):
                    interpreted = validate_claim(item, filing, claim.get("page_number", claim.get("page")))
                    return {**interpreted, "claim_id": claim["claim_id"], "interpretation_run_id": run_id}, {
                        "cache_hit": True, "run_id": run_id, "runtime_ms": 0,
                        "model": record.get("resolved_model"), "reused_original_extraction": True}
    schema = (ROOT / config["prompts"]["extraction"]).read_text(encoding="utf-8")
    prompt = (ROOT / config["prompts"]["interpretation"]).read_text(encoding="utf-8")
    supplied = {"company": filing["company"], "reporting_year": filing["reporting_year"],
                "page_number": claim.get("page_number", claim.get("page")),
                "source_sentence": claim["source_sentence"], "pdf_context": claim.get("pdf_context")}
    item, run = client.generate(prompt + "\nSCHEMA/RULES:\n" + schema + "\nSTATEMENT:\n" + json.dumps(supplied), "interpretation")
    interpreted = validate_claim(item, filing, supplied["page_number"])
    if compact(interpreted["source_sentence"]) != compact(claim["source_sentence"]):
        raise ValueError("Interpretation altered the source sentence")
    return {**interpreted, "claim_id": claim["claim_id"], "interpretation_run_id": run["run_id"]}, run
