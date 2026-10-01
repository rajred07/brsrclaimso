"""Calculate research scores from saved predictions, with no reference scores."""
import argparse
import csv
import json
import hashlib
from collections import Counter
from pathlib import Path
import sys

# Support both python -m experiments.evaluate and python experiments/evaluate.py.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.dataset import examples, require_reference_reviews, dataset_fingerprint, require_complete_dataset
from src.llm import ROOT, load_config
from src.verifier import LABELS


def compute_metrics(rows, gold_facts=None):
    if not rows:
        return {"n": 0, "metrics": None, "reason": "NO_EXAMPLES"}
    if any(r["gold_label"] not in LABELS or r["predicted_label"] not in LABELS for r in rows):
        raise ValueError("Every scored row needs a valid real gold label and prediction")
    matrix = {g: {p: 0 for p in LABELS} for g in LABELS}
    for row in rows:
        matrix[row["gold_label"]][row["predicted_label"]] += 1
    f1s, precision_i, recall_i, f1_i = [], 0.0, 0.0, 0.0
    for label in LABELS:
        tp = matrix[label][label]
        fp = sum(matrix[g][label] for g in LABELS if g != label)
        fn = sum(matrix[label][p] for p in LABELS if p != label)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        f1s.append(f1)
        if label == "INCONSISTENT":
            precision_i, recall_i, f1_i = precision, recall, f1
    negatives = sum(r["gold_label"] != "INCONSISTENT" for r in rows)
    false_positives = sum(r["gold_label"] != "INCONSISTENT" and r["predicted_label"] == "INCONSISTENT" for r in rows)
    supported = sum(r["gold_label"] == "SUPPORTED" for r in rows)
    supported_false_positives = matrix["SUPPORTED"]["INCONSISTENT"]
    grounding = []
    for row in rows:
        expected = (gold_facts or {}).get(row["claim_id"])
        if expected:  # no artificial credit for two empty ID sets
            grounding.append(set(json.loads(row["matched_fact_ids"])) == set(expected))
    return {"n": len(rows), "precision_inconsistent": precision_i, "recall_inconsistent": recall_i,
            "f1_inconsistent": f1_i, "macro_f1": sum(f1s) / 3,
            "false_positive_rate": false_positives / negatives if negatives else None,
            "false_positive_rate_supported": supported_false_positives / supported if supported else None,
            "coverage": sum(r["predicted_label"] != "INSUFFICIENT_EVIDENCE" for r in rows) / len(rows),
            "grounding_accuracy": sum(grounding) / len(grounding) if grounding else None,
            "grounding_n": len(grounding), "confusion_matrix": matrix,
            "zero_division_policy": "Class precision/recall/F1 = 0 when undefined; FPR/grounding = null when no denominator"}


def evaluate(path, config, require_complete=True):
    from experiments.run import SYSTEMS, implementation_fingerprint
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        all_rows = list(csv.DictReader(handle))
    rows = [r for r in all_rows if r["split"] == "test"]
    if not rows:
        raise ValueError("No real held-out predictions. No performance scores can be reported.")
    claims = examples(config, "test")
    require_reference_reviews(claims, config)
    metadata_path = Path(str(path) + ".run.json")
    if not metadata_path.exists():
        raise ValueError("Evaluation requires recorded run provenance")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    fingerprints = {"dataset_sha256": dataset_fingerprint(config),
                    "implementation_sha256": implementation_fingerprint(),
                    "predictions_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}
    if metadata.get("split") != "test" or any(metadata.get(k) != v for k, v in fingerprints.items()):
        raise ValueError("Prediction provenance does not match the current dataset, implementation or CSV")
    if require_complete:
        require_complete_dataset(examples(config), config)
    gold = {c["claim_id"]: c for c in claims}
    seen = set()
    for row in rows:
        key = row["system"], row["claim_id"]
        if key in seen:
            raise ValueError("Duplicate system/example prediction")
        seen.add(key)
        c = gold.get(row["claim_id"])
        if (not c or row["gold_label"] != c["gold_label"] or
                row["natural_or_modified"] != c["natural_or_modified"] or row["system"] not in SYSTEMS):
            raise ValueError("Prediction differs from the annotated held-out dataset")
    systems = sorted({r["system"] for r in rows})
    if require_complete and set(systems) != set(SYSTEMS):
        raise ValueError("The final evaluation requires all three baselines and VeriBRSR")
    counts = Counter(r["system"] for r in rows)
    if any(counts[s] != len(gold) for s in systems):
        raise ValueError("Systems must predict the same complete held-out example set")
    groups = {s: {group: compute_metrics([r for r in rows if r["system"] == s and
                                        (group == "combined" or r["natural_or_modified"] == group)],
                                       {cid: c.get("gold_xbrl_fact_ids") for cid, c in gold.items()})
                  for group in ("natural", "modified", "combined")} for s in systems}
    return {"split": "test", "complete_four_system_evaluation": set(systems) == set(SYSTEMS),
            **fingerprints, "annotation_mode": config["annotation"]["mode"],
            "reference_label_status": "Agreement with automatic XBRL references; not independent ground-truth accuracy",
            "definitions": {"false_positive_rate": "gold != INCONSISTENT predicted INCONSISTENT / all gold != INCONSISTENT",
                            "coverage": "non-abstained predictions / all examples",
                            "grounding_accuracy": "exact set equality of predicted/gold fact IDs over examples with gold IDs",
                            "macro_f1": "mean F1 over the three fixed verdict classes"}, "results": groups}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", type=Path, default=ROOT / "experiments/predictions.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "experiments/metrics.json")
    parser.add_argument("--allow-partial-systems", action="store_true")
    args = parser.parse_args()
    result = evaluate(args.predictions, load_config(), not args.allow_partial_systems)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
