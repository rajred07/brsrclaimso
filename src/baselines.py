"""Exactly three baselines; only B and C ask an LLM for a verdict."""
import json
import re

from .extract_claims import interpret_statement
from .llm import ROOT
from .matcher import ALIASES, metric_score, retrieve, words
from .verifier import LABELS, verify


def keyword_interpret(claim, filing):
    text = claim["source_sentence"]
    normalized = words(text)
    metric = next((key for key, aliases in ALIASES.items()
                   if any(words(alias) in normalized for alias in aliases)), None)
    periods = re.findall(r"(?:FY\s*)?(\d{4}[-–]\d{2})", text, re.I)
    instant = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", text)
    dates = instant or periods
    direction = -1 if re.search(r"\b(decreased?|declined?|reduced?|fell)\b", text, re.I) else (
        1 if re.search(r"\b(increased?|rose|grew)\b", text, re.I) else
        0 if re.search(r"\b(unchanged|stable)\b", text, re.I) else None)
    numeric = re.search(r"([+-]?\d[\d,]*(?:\.\d+)?)\s*(%|kL|L|GJ|MWh|kWh|tCO2e|kgCO2e|tonnes?|count)(?!\w)", text, re.I)
    operation = "value_equality"
    asserted, unit = None, None
    if numeric:
        asserted, unit = numeric[1].replace(",", ""), numeric[2]
        if direction is not None:
            operation = "percentage_change" if unit == "%" else "absolute_change"
            asserted = str(direction * float(asserted))
    elif direction is not None:
        operation, asserted = "direction_of_change", direction
    # The rule baseline sees raw text/metadata, never LLM or gold interpretation fields.
    return {"claim_id": claim["claim_id"], "filing_id": filing["filing_id"], "company": filing["company"],
            "source_sentence": text, "page": claim.get("page", claim.get("page_number")),
            "metric": metric, "operation": operation, "asserted_value": asserted, "unit": unit,
            "current_period": dates[0] if dates else None, "previous_period": dates[1] if len(dates) > 1 else None,
            "boundary": "consolidated" if "consolidated" in text.casefold() else
                        "standalone" if "standalone" in text.casefold() else None}


def baseline_a(claim, filing, facts, config):
    return verify(keyword_interpret(claim, filing), facts, config)


def llm_verdict(claim, evidence, config, client, purpose):
    prompt = (ROOT / config["prompts"]["baseline"]).read_text(encoding="utf-8")
    # Only the raw statement/context and filing metadata are passed. Gold labels,
    # annotation notes and gold fact IDs never enter an LLM request.
    supplied = {k: claim.get(k) for k in ("source_sentence", "company", "reporting_year", "pdf_context",
                                        "metric", "operation", "asserted_value", "unit", "current_period", "previous_period", "boundary")}
    answer, run = client.generate(prompt + "\nCLAIM:\n" + json.dumps(supplied) +
                                  "\nEVIDENCE:\n" + json.dumps(evidence), purpose)
    if not isinstance(answer, dict) or answer.get("verdict") not in LABELS:
        raise ValueError("LLM baseline returned an invalid verdict")
    supplied_ids = {f["fact_id"] for f in evidence["facts"]}
    matched = answer.get("matched_fact_ids")
    if not isinstance(matched, list) or not set(matched).issubset(supplied_ids):
        raise ValueError("LLM baseline cited missing or invented fact IDs")
    if answer["verdict"] == "INSUFFICIENT_EVIDENCE" and not answer.get("abstention_reason"):
        raise ValueError("LLM abstention needs a reason")
    return {"claim_id": claim["claim_id"], "source_sentence": claim["source_sentence"],
            "pdf_page": claim.get("page", claim.get("page_number")), "verdict": answer["verdict"],
            "matched_fact_ids": matched, "calculated_value": answer.get("calculated_value"),
            "calculation": answer.get("explanation"), "abstention_reason": answer.get("abstention_reason"),
            "evidence": evidence, "llm_run": run, "decision_method": "LLM_BASELINE"}


def baseline_b(claim, filing, facts, config, client):
    # Same filing, all supported-family numeric facts; no claim-specific ranking,
    # period filtering or deterministic arithmetic. Evidence pool is saved in full.
    pool = [f for f in facts if any(metric_score(key, f) >= config["matching"]["minimum_similarity"]
                                  for key in ALIASES)]
    interpreted, _ = interpret_statement(claim, filing, config, client)
    return llm_verdict({**interpreted, "pdf_context": claim.get("pdf_context")}, {"facts": pool, "selection": "all scoped metric-family facts"},
                       config, client, "baseline_b")


def baseline_c(claim, filing, facts, config, client, interpreted=None):
    if interpreted is None:
        interpreted, _ = interpret_statement(claim, filing, config, client)
    retrieval = retrieve(interpreted, facts, config["matching"])
    # Give the same selected facts and ambiguity candidates as the main system.
    pool = {f["fact_id"]: f for f in (retrieval["current"], retrieval["previous"]) if f}
    for candidates in retrieval["candidates"].values():
        for candidate in candidates:
            pool[candidate["fact"]["fact_id"]] = candidate["fact"]
    return llm_verdict({**interpreted, "pdf_context": claim.get("pdf_context")}, {"facts": list(pool.values()), "retrieval": retrieval},
                       config, client, "baseline_c")
