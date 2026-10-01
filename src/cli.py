"""Small command-line workflow; run from the repository root."""
import argparse
import csv
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pymupdf
import yaml

from .dataset import examples, filings, read_json, require_complete_dataset
from .extract_claims import extract_pdf, compact
from .llm import ROOT, load_config
from .perturbations import generate
from .xbrl_parser import parse_xbrl, store_facts, load_facts


def candidate_status(config):
    manifest = filings(config)
    ready = [f["filing_id"] for f in manifest if all(f.get(k) and (ROOT / f[k]).is_file()
             for k in ("pdf_path_or_url", "xbrl_path_or_url"))]
    claims = examples(config, require_gold=False)
    complete = False
    metrics = ROOT / "experiments/metrics.json"
    if metrics.exists():
        from .dataset import dataset_fingerprint
        from experiments.run import implementation_fingerprint
        record = json.loads(metrics.read_text(encoding="utf-8"))
        predictions = ROOT / config["data"]["predictions"]
        complete = (record.get("complete_four_system_evaluation") is True and
                    record.get("dataset_sha256") == dataset_fingerprint(config) and
                    record.get("implementation_sha256") == implementation_fingerprint() and
                    predictions.is_file() and
                    record.get("predictions_sha256") == hashlib.sha256(predictions.read_bytes()).hexdigest())
    return {"required_filing_pairs": 10, "materialized_pairs": len(ready), "ready_filing_ids": ready,
            "natural_reference_records": sum(c["natural_or_modified"] == "natural" for c in claims),
            "perturbation_reference_records": sum(c["natural_or_modified"] == "modified" for c in claims),
            "examples_by_split": {s: sum(c["split"] == s for c in claims) for s in ("development", "test")},
            "annotation_mode": config["annotation"]["mode"], "manual_gold_labels_created": 0,
            "automatic_reference_experiment_complete": complete,
            "independent_ground_truth_evaluation_complete": False}


def validate_sources(claims, manifest):
    cache = {}
    for claim in claims:
        filing = manifest[claim["filing_id"]]
        if filing["filing_id"] not in cache:
            with pymupdf.open(ROOT / filing["pdf_path_or_url"]) as doc:
                cache[filing["filing_id"]] = [p.get_text() for p in doc]
        page = claim.get("page", claim.get("page_number"))
        if not isinstance(page, int) or not 1 <= page <= len(cache[filing["filing_id"]]):
            raise ValueError("Invalid PDF page provenance")
        sentence = claim.get("original_sentence", claim.get("source_sentence"))
        if not sentence or compact(sentence) not in compact(cache[filing["filing_id"]][page-1]):
            raise ValueError(f"Source passage does not occur in the PDF: {claim['claim_id']}")


def main():
    parser = argparse.ArgumentParser(description="VeriBRSR research workflow")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    validate = commands.add_parser("validate")
    validate.add_argument("--complete", action="store_true", help="Require all ten pairs, both splits and automatic references")
    ingest = commands.add_parser("ingest")
    ingest.add_argument("--filing", required=True)
    extraction = commands.add_parser("extract")
    extraction.add_argument("--filing", required=True)
    extraction.add_argument("--pages", help="1-based PDF page range override")
    extraction.add_argument("--context-pages", help="Explicit PDF boundary/year pages")
    extraction.add_argument("--output", type=Path)
    perturb = commands.add_parser("perturb")
    perturb.add_argument("--count", type=int, default=40)
    annotation = commands.add_parser("annotation-pack")
    annotation.add_argument("--split", choices=["development", "test"], default="test")

    commands.add_parser("freeze")
    args = parser.parse_args()
    config = load_config()
    manifest = {f["filing_id"]: f for f in filings(config)}
    if args.command == "status":
        print(json.dumps(candidate_status(config), indent=2))
    elif args.command == "validate":
        filings(config, require_ready=args.complete)
        if args.complete:
            claims = examples(config)
            validate_sources(claims, manifest)
            require_complete_dataset(claims, config)
        print(json.dumps(candidate_status(config), indent=2))
    elif args.command == "ingest":
        f = manifest[args.filing]
        if not f["xbrl_path_or_url"] or f["xbrl_path_or_url"].startswith("http"):
            raise ValueError("Materialize the real XBRL filing and update its local path first")
        facts = parse_xbrl(ROOT / f["xbrl_path_or_url"], f["company"], f["reporting_year"], f["filing_id"])
        store_facts(facts, ROOT / config["data"]["facts_db"])
        print(f"Stored {len(facts)} numeric facts for {args.filing}")
    elif args.command == "extract":
        f = manifest[args.filing]
        ranges = yaml.safe_load((ROOT / config["data"]["page_ranges"]).read_text()).get(args.filing, {})
        output = args.output or ROOT / f"data/candidates/{args.filing}.json"
        claims = extract_pdf(f, args.pages or ranges.get("pages"), config, output,
                             args.context_pages or ranges.get("context_pages"))
        print(f"Saved {len(claims)} unannotated candidates to {output}")
    elif args.command == "perturb":
        claims = examples(config)
        draft = generate([c for c in claims if c["natural_or_modified"] == "natural"], config, args.count)
        if not draft:
            raise ValueError("No human-verified supported parents; no perturbations were fabricated")
        path = ROOT / "data/perturbation_candidates.json"
        path.write_text(json.dumps(draft, indent=2), encoding="utf-8")
        print(f"Saved {len(draft)} draft mutations for manual review to {path}")
    elif args.command == "annotation-pack":
        claims = examples(config, args.split, require_gold=False)
        if not claims:
            raise ValueError("Add sourced natural claims before exporting the annotation pack")
        pack = []
        for c in claims:
            f = manifest[c["filing_id"]]
            pack.append({"claim_id": c["claim_id"], "company": c["company"], "page": c.get("page", c.get("page_number")),
                         "sentence": c["source_sentence"], "pdf": f["pdf_path_or_url"],
                         "xbrl": f["xbrl_path_or_url"],
                         "facts": load_facts(ROOT / config["data"]["facts_db"], c["filing_id"])})
        path = ROOT / f"data/annotations/{args.split}_blind_pack.json"
        path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
        print(f"Saved blind pack with no system predictions or gold labels: {path}")
    elif args.command == "kappa":
        raise ValueError("No independent annotations: kappa is not applicable")
    elif args.command == "freeze":
        from experiments.run import implementation_fingerprint
        path = ROOT / "experiments/frozen_config.json"
        path.write_text(json.dumps({"implementation_sha256": implementation_fingerprint(),
                                    "frozen_at": datetime.now(timezone.utc).isoformat()}, indent=2), encoding="utf-8")
        print("Development implementation frozen; changes invalidate the held-out run")


if __name__ == "__main__":
    main()
