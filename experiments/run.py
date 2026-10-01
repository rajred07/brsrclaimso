"""Run the same examples through the four specified research systems."""
import argparse
import csv
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from src.baselines import baseline_a, baseline_b, baseline_c
from src.batch_llm import interpret_modified_batch, verdict_batch
from src.dataset import dataset_fingerprint, examples, filings, read_json, require_reference_reviews
from src.extract_claims import interpret_statement
from src.llm import ROOT, JSONClient, environment_record, load_config
from src.verifier import verify
from src.xbrl_parser import load_facts

SYSTEMS = ("keyword_calculator", "llm_only", "retrieval_llm", "veribrsr")
COLUMNS = ["claim_id", "system", "gold_label", "predicted_label", "split", "natural_or_modified",
           "matched_fact_ids", "claimed_value", "calculated_value", "calculation_trace", "abstention_reason", "runtime_ms"]


def implementation_fingerprint():
    digest = hashlib.sha256()
    paths = [ROOT / "config.yaml", ROOT / "data/filings.csv", ROOT / "requirements.txt",
             *sorted((ROOT / "src").glob("*.py")), *sorted((ROOT / "prompts").glob("*.txt")),
             ROOT / "experiments/run.py", ROOT / "experiments/evaluate.py"]
    for path in paths:
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def write_csv(path, rows):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def matched_ids(trace):
    if "matched_fact_ids" in trace:
        return trace["matched_fact_ids"]
    evidence = trace.get("evidence", {})
    return [evidence[key]["fact_id"] for key in ("current", "previous") if evidence.get(key)]


def prepared_claims(claims, manifest, config, client, fact_cache, systems, batch_size):
    """Finish one bounded chunk before yielding rows for its checkpoint."""
    for offset in range(0, len(claims), batch_size):
        chunk = claims[offset:offset + batch_size]
        interpretations, batch_traces = {}, {}
        for claim in chunk:
            fid = claim["filing_id"]
            if fid not in fact_cache:
                fact_cache[fid] = load_facts(ROOT / config["data"]["facts_db"], fid)
        needs_interpretation = any(s != "keyword_calculator" for s in systems)
        if needs_interpretation:
            for claim in chunk:
                if claim["natural_or_modified"] == "natural":
                    interpretations[claim["claim_id"]] = interpret_statement(
                        claim, manifest[claim["filing_id"]], config, client)
            interpretations.update(interpret_modified_batch(
                [c for c in chunk if c["natural_or_modified"] == "modified"], manifest, config, client))
        for system in systems:
            if system in ("llm_only", "retrieval_llm"):
                batch_traces[system] = verdict_batch(system, chunk, interpretations, fact_cache, config, client)
        for claim in chunk:
            yield claim, interpretations, batch_traces


def run(config, split="test", systems=SYSTEMS, candidate_path=None, output=None, batch=False, batch_size=6):
    if not isinstance(batch_size, int) or isinstance(batch_size, bool) or not 1 <= batch_size <= 8:
        raise ValueError("Batch size must be between 1 and 8 claims")
    manifest = {f["filing_id"]: f for f in filings(config, require_ready=split == "test")}
    if candidate_path:
        if split == "test":
            raise ValueError("Unannotated candidate smoke runs are development-only")
        claims = read_json(candidate_path)
        for claim in claims:
            filing = manifest[claim["filing_id"]]
            if filing["split"] != "development":
                raise ValueError("Candidate smoke runs cannot include held-out companies")
            claim["split"], claim["natural_or_modified"] = "development", "natural"
        output = output or ROOT / "experiments/development_smoke_predictions.csv"
    else:
        claims = examples(config, split)
        output = output or ROOT / config["data"]["predictions"]
    if not claims:
        raise ValueError("No eligible claims; no experiment results will be created")
    if split == "test":
        require_reference_reviews(claims, config)
        frozen = ROOT / "experiments/frozen_config.json"
        if not frozen.exists() or json.loads(frozen.read_text())["implementation_sha256"] != implementation_fingerprint():
            raise ValueError("Freeze the development configuration before the held-out test run")
    client, rows, traces = JSONClient(config), [], []
    fact_cache = {}
    partial = Path(str(output) + ".partial.csv")
    prepared = prepared_claims(claims, manifest, config, client, fact_cache, systems, batch_size) if batch else (
        (c, {}, {}) for c in claims)
    for claim, interpretations, batch_traces in prepared:
        filing = manifest[claim["filing_id"]]
        if filing["filing_id"] not in fact_cache:
            fact_cache[filing["filing_id"]] = load_facts(ROOT / config["data"]["facts_db"], filing["filing_id"])
        facts = fact_cache[filing["filing_id"]]
        for system in systems:
            started = time.perf_counter()
            interpreted = None
            if system == "keyword_calculator":
                trace = baseline_a(claim, filing, facts, config)
            elif batch and system in batch_traces:
                interpreted = interpretations[claim["claim_id"]][0]
                trace = batch_traces[system][claim['claim_id']]
            elif system == "llm_only":
                trace = baseline_b(claim, filing, facts, config, client)
            elif system == "retrieval_llm":
                trace = baseline_c(claim, filing, facts, config, client)
            elif system == "veribrsr":
                interpreted, llm_run = interpretations[claim['claim_id']] if batch else interpret_statement(claim, filing, config, client)
                trace = verify(interpreted, facts, config)
                trace["interpretation_run"] = llm_run
            else:
                raise ValueError(f"Unknown system: {system}")
            runtime = (time.perf_counter() - started) * 1000
            if batch and system in batch_traces:
                runtime = None
            trace.update({"system": system, "runtime_ms": runtime, "claim_id": claim["claim_id"]})
            trace["input_claim"] = {k: claim.get(k) for k in (
                "claim_id", "filing_id", "company", "page", "page_number", "source_sentence", "metric", "operation",
                "asserted_value", "unit", "current_period", "previous_period", "boundary")}
            traces.append(trace)
            rows.append({"claim_id": claim["claim_id"], "system": system, "gold_label": claim.get("gold_label") or "",
                         "predicted_label": trace["verdict"], "split": claim["split"],
                         "natural_or_modified": claim["natural_or_modified"],
                         "matched_fact_ids": json.dumps(matched_ids(trace)),
                         "claimed_value": (interpreted or claim).get("asserted_value"),
                         "calculated_value": trace.get("calculated_value"),
                         "calculation_trace": json.dumps(trace, ensure_ascii=False),
                         "abstention_reason": trace.get("abstention_reason") or "", "runtime_ms": runtime})
            write_csv(partial, rows)
            print(f"{claim['claim_id']} {system}: {trace['verdict']}", flush=True)
    partial.replace(output)
    traces_path = Path(str(output) + ".traces.jsonl")
    if not traces_path.is_absolute():
        traces_path = ROOT / traces_path
    traces_path.write_text("".join(json.dumps(t, ensure_ascii=False) + "\n" for t in traces), encoding="utf-8")
    metadata = {"run_date": datetime.now(timezone.utc).isoformat(), "config": config,
                "environment": environment_record(), "dataset_sha256": dataset_fingerprint(config),
                "implementation_sha256": implementation_fingerprint(), "systems": list(systems),
                "split": split, "n_claims": len(claims), "unannotated_smoke_run": bool(candidate_path),
                "batch_size": batch_size if batch else None,
                "predictions_sha256": hashlib.sha256(Path(output).read_bytes()).hexdigest(),
                "reference_label_status": "AUTOMATED REFERENCES: consistency scores, not independent ground-truth accuracy",
                "runtime_note": "Measured wall time, including cache hits and pacing. See each trace for cache status."}
    Path(str(output) + ".run.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["development", "test"], default="test")
    parser.add_argument("--systems", nargs="+", choices=SYSTEMS, default=list(SYSTEMS))
    parser.add_argument("--candidates", type=Path, help="Development smoke run without gold labels")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--batch", action="store_true", help="Use shared evidence pools and bounded free-tier request batches")
    parser.add_argument("--batch-size", type=int, default=6, help="Claims per request (1-8, default 6)")
    args = parser.parse_args()
    run(load_config(), args.split, args.systems, args.candidates, args.output, args.batch, args.batch_size)


if __name__ == "__main__":
    main()
