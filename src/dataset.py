"""Dataset limits, company split integrity and automated reference provenance."""
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from .llm import ROOT
from .verifier import LABELS


def read_json(path):
    records = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError(f"Expected an array: {path}")
    return records


def filings(config, require_ready=False):
    with (ROOT / config["data"]["filings"]).open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 10 or len({r["filing_id"] for r in rows}) != 10:
        raise ValueError("The manifest must contain exactly 10 distinct company-year slots")
    split_map = {}
    pairs = set()
    for row in rows:
        company = row["company"].strip().casefold()
        if not company or row["split"] not in {"development", "test"}:
            raise ValueError("Every filing needs a company and development/test split")
        if company in split_map and split_map[company] != row["split"]:
            raise ValueError("Company leakage across development/test")
        split_map[company] = row["split"]
        pair = (company, row["reporting_year"])
        if pair in pairs:
            raise ValueError("Duplicate company-year filing")
        pairs.add(pair)
        if require_ready:
            for key in ("pdf_path_or_url", "xbrl_path_or_url"):
                value = row.get(key)
                if not value or value.startswith("http") or not (ROOT / value).is_file():
                    raise ValueError(f"Filing not materialized: {row['filing_id']} {key}")
    if len(split_map) == 10 and Counter(split_map.values()) != {"development": 7, "test": 3}:
        raise ValueError("Ten different companies require a 7/3 company split")
    return rows


def examples(config, split=None, require_gold=True):
    manifest = {r["filing_id"]: r for r in filings(config)}
    natural = read_json(ROOT / config["data"]["natural_claims"])
    modified = read_json(ROOT / config["data"]["perturbations"])
    natural_map = {c["claim_id"]: c for c in natural}
    if len(natural_map) != len(natural):
        raise ValueError("Duplicate natural claim IDs")
    records = []
    for c in natural:
        records.append({**c, "natural_or_modified": "natural"})
    for p in modified:
        if p["original_claim_id"] not in natural_map:
            raise ValueError("Perturbation has no genuine parent claim")
        original = natural_map[p["original_claim_id"]]
        if p.get("filing_id", original["filing_id"]) != original["filing_id"]:
            raise ValueError("Perturbation changed its filing/split")
        if p.get("original_sentence") != original["source_sentence"]:
            raise ValueError("Perturbation original sentence disagrees with parent")
        if original.get("gold_label") != "SUPPORTED":
            raise ValueError("Perturbations require a source-referenced supported parent")
        records.append({**original, **p, "claim_id": p["perturbation_id"],
                        "filing_id": original["filing_id"], "source_sentence": p["modified_sentence"],
                        "gold_label": p.get("gold_label"), "gold_xbrl_fact_ids": p.get("gold_xbrl_fact_ids", []),
                        "natural_or_modified": "modified"})
    seen = set()
    for c in records:
        if c["claim_id"] in seen:
            raise ValueError("Duplicate evaluation example ID")
        seen.add(c["claim_id"])
        filing = manifest[c["filing_id"]]
        if c["company"] != filing["company"] or c.get("split", filing["split"]) != filing["split"]:
            raise ValueError("Claim metadata disagrees with filing")
        c["split"] = filing["split"]
    selected = [c for c in records if split is None or c["split"] == split]
    if require_gold and any(c.get("gold_label") not in LABELS or not c.get("annotation_notes") for c in selected):
        raise ValueError("Automated reference labels and annotation notes are required")
    return selected


def require_reference_reviews(claims, config):
    records = read_json(ROOT / config["data"]["reference_reviews"])
    reviews = {r["claim_id"]: r for r in records}
    if len(reviews) != len(records):
        raise ValueError("Duplicate automated source-reference IDs")
    manifest = {f["filing_id"]: f for f in filings(config)}
    hashes = {}
    for claim in claims:
        review = reviews.get(claim["claim_id"], {})
        if review.get("reference_label") != claim.get("gold_label") or not review.get("source_sha256"):
            raise ValueError("Missing or inconsistent automated source-reference record")
        if review.get("annotation_mode") != "automated_source_reference":
            raise ValueError("This experiment uses automated references, not independent human annotations")
        fid = claim["filing_id"]
        if fid not in hashes:
            hashes[fid] = {kind: hashlib.sha256((ROOT / manifest[fid][key]).read_bytes()).hexdigest()
                           for kind, key in (("source_sha256", "pdf_path_or_url"), ("xml_sha256", "xbrl_path_or_url"))}
        if any(review.get(key) != value for key, value in hashes[fid].items()):
            raise ValueError("Source documents changed since automatic reference generation")
        if (review.get("source_sentence") != claim["source_sentence"] or
                review.get("pdf_page") != claim.get("page", claim.get("page_number")) or
                {f["fact_id"] for f in review.get("evidence", [])} != set(claim.get("gold_xbrl_fact_ids", []))):
            raise ValueError("Claim provenance/evidence disagrees with its automatic reference")


def require_complete_dataset(claims, config):
    manifest = filings(config, require_ready=True)
    natural_counts = Counter(c["filing_id"] for c in claims if c["natural_or_modified"] == "natural")
    if any(not 5 <= natural_counts[f["filing_id"]] <= 8 for f in manifest):
        raise ValueError("Complete dataset requires 5-8 sourced natural claims for each of the ten filings")
    modified = [c for c in claims if c["natural_or_modified"] == "modified"]
    if len(modified) != config["scope"]["perturbations_target"] or {c["split"] for c in modified} != {"development", "test"}:
        raise ValueError("Complete dataset requires the planned mutations in both company splits")
    require_reference_reviews(claims, config)


def dataset_fingerprint(config):
    digest = hashlib.sha256()
    for key in ("filings", "natural_claims", "perturbations", "page_ranges", "reference_reviews"):
        digest.update((ROOT / config["data"][key]).read_bytes())
    return digest.hexdigest()
