"""Generate reviewable sentence mutations, never automatic human gold labels."""
import json
import random
import re
from datetime import date

from .llm import ROOT
from .units import number, canonical_unit
from .verifier import verify
from .xbrl_parser import load_facts


def mutations(claim):
    sentence, operation = claim["source_sentence"], claim["operation"]
    asserted = claim.get("asserted_value")
    candidates = []
    if operation in {"value_equality", "absolute_change", "percentage_change"} and asserted is not None:
        for match in re.finditer(r"(?<![\w.])[+-]?\d[\d,]*(?:\.\d+)?(?![\w.])", sentence):
            if abs(number(match[0])) != abs(number(asserted)):
                continue
            changed = abs(number(asserted)) + 5 if operation == "percentage_change" else abs(number(asserted)) * number("1.25") + 1
            replacement = str(changed)
            if match[0].startswith("-"):
                replacement = "-" + replacement
            modified = sentence[:match.start()] + replacement + sentence[match.end():]
            value = -changed if number(asserted) < 0 else changed
            candidates.append(("percentage_alteration" if operation == "percentage_change" else "magnitude_alteration",
                               modified, {"asserted_value": str(value)}))
            break  # skip claims without an unambiguous asserted number span
    if operation in {"direction_of_change", "absolute_change", "percentage_change"}:
        pairs = {"decreased": "increased", "increased": "decreased", "decrease": "increase",
                 "increase": "decrease", "reduced": "increased", "fell": "rose", "rose": "fell"}
        match = re.search(r"\b(" + "|".join(pairs) + r")\b", sentence, re.I)
        if match and asserted is not None:
            replacement = pairs[match[0].casefold()]
            if match[0][0].isupper():
                replacement = replacement.capitalize()
            candidates.append(("direction_reversal", sentence[:match.start()] + replacement + sentence[match.end():],
                               {"asserted_value": str(-number(asserted))}))
    previous = claim.get("previous_period")
    if isinstance(previous, dict) and previous.get("start") and previous.get("end"):
        original_year = previous["start"][:4] + "-" + previous["end"][2:4]
    else:
        original_year = str(previous or "").removeprefix("FY ")
    if original_year in sentence and re.fullmatch(r"\d{4}-\d{2}", original_year):
        start = int(original_year[:4]) - 1
        altered = f"{start}-{str(start+1)[2:]}"
        if isinstance(previous, dict):
            try:
                altered_period = {**previous, **{k: date.fromisoformat(previous[k]).replace(
                    year=date.fromisoformat(previous[k]).year - 1).isoformat() for k in ("start", "end")}}
            except ValueError:
                altered_period = None
        else:
            altered_period = altered
        if altered_period:
            candidates.append(("base_year_alteration", sentence.replace(original_year, altered, 1), {"previous_period": altered_period}))
    unit_map = {"kL": "L", "L": "kL", "GJ": "MWh", "MWh": "kWh", "kWh": "MWh",
                "tCO2e": "kgCO2e", "kgCO2e": "tCO2e"}
    unit = claim.get("unit")
    normalized_unit = canonical_unit(unit)
    unit_pattern = r"(?<!\w)" + r"\s+".join(re.escape(w) for w in str(unit or "").split()) + r"(?!\w)"
    if normalized_unit in unit_map and re.search(unit_pattern, sentence):
        changed_sentence = re.sub(unit_pattern, unit_map[normalized_unit], sentence, count=1)
        candidates.append(("unit_alteration", changed_sentence, {"unit": unit_map[normalized_unit]}))
    return candidates


def generate(claims, config, count=40):
    if count > 40 or count < 1:
        raise ValueError("Use at most 40 perturbations for the current experiment")
    draft = []
    for claim in claims:
        if claim.get("gold_label") != "SUPPORTED" or not claim.get("annotation_notes"):
            continue
        facts = load_facts(ROOT / config["data"]["facts_db"], claim["filing_id"])
        if verify(claim, facts, config)["verdict"] != "SUPPORTED":
            continue  # do not perturb a parent that the current evidence cannot support
        for kind, sentence, changed in mutations(claim):
            record = {**claim, **changed, "source_sentence": sentence}
            trace = verify(record, facts, config)
            draft.append({**record, "perturbation_id": f"{claim['claim_id']}-mod-{kind}",
                          "original_claim_id": claim["claim_id"], "mutation_type": kind,
                          "original_sentence": claim["source_sentence"], "modified_sentence": sentence,
                          "gold_label": None, "gold_xbrl_fact_ids": [], "annotation_notes": None,
                          "proposed_label_requires_manual_review": trace["verdict"],
                          "mutation_check_trace": trace})
    random.Random(config["random_seed"]).shuffle(draft)
    return draft[:count]
