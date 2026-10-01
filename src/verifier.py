"""Pure deterministic verdicts. This module has no LLM or network dependency."""
from decimal import Decimal

from .matcher import retrieve
from .units import normalize, number

LABELS = ("SUPPORTED", "INCONSISTENT", "INSUFFICIENT_EVIDENCE")
OPERATIONS = ("value_equality", "direction_of_change", "absolute_change", "percentage_change")


def verify(claim, facts, config=None):
    config = config or {}
    tolerances = config.get("verification", {})
    relative = number(tolerances.get("relative_tolerance", "0.01"))
    percentage = number(tolerances.get("percentage_points_tolerance", "0.5"))
    epsilon = number(tolerances.get("epsilon", "1e-12"))
    evidence = retrieve(claim, facts, config.get("matching"))
    trace = {
        "claim_id": claim.get("claim_id"), "source_sentence": claim.get("source_sentence"),
        "pdf_page": claim.get("page_number", claim.get("page")), "claimed_value": claim.get("asserted_value"),
        "claimed_unit": claim.get("unit"), "current_period": claim.get("current_period"),
        "previous_period": claim.get("previous_period"), "boundary": claim.get("boundary"),
        "operation": claim.get("operation"), "evidence": evidence, "normalized_values": {},
        "calculation": None, "calculated_value": None, "tolerance": None,
        "verdict": "INSUFFICIENT_EVIDENCE", "abstention_reason": evidence["reason"],
    }

    def abstain(reason):
        trace["abstention_reason"] = reason
        return trace

    if claim.get("is_target") is True:
        return abstain("FUTURE_TARGET")
    if claim.get("operation") not in OPERATIONS:
        return abstain("UNSUPPORTED_OPERATION")
    if evidence["reason"]:
        return trace
    try:
        current, unit = normalize(evidence["current"]["value"], evidence["current"]["unit"])
        previous = None
        if evidence["previous"]:
            previous, previous_unit = normalize(evidence["previous"]["value"], evidence["previous"]["unit"])
            if previous_unit != unit:
                return abstain("UNIT_INCOMPATIBLE")
        trace["normalized_values"] = {"current": str(current), "previous": str(previous) if previous is not None else None,
                                       "unit": unit}
        operation = claim["operation"]
        if operation == "percentage_change":
            if claim.get("unit") not in {"%", "percent", "percentage"}:
                return abstain("UNIT_INCOMPATIBLE")
            if previous == 0:
                return abstain("ZERO_DENOMINATOR")
            calculated = (current - previous) / previous * 100
            claimed = number(claim.get("asserted_value"))
            trace["calculation"] = f"(({current} - {previous}) / {previous}) * 100"
            trace["tolerance"] = {"percentage_points": str(percentage)}
            supported = abs(calculated - claimed) <= percentage
        elif operation == "direction_of_change":
            delta = current - previous
            calculated = Decimal(1 if delta > 0 else -1 if delta < 0 else 0)
            directions = {"increase": 1, "decrease": -1, "unchanged": 0}
            asserted = claim.get("direction", claim.get("asserted_value"))
            claimed = number(directions.get(asserted, asserted))
            if claimed not in {-1, 0, 1}:
                return abstain("MISSING_OPERAND")
            trace["calculation"] = f"sign({current} - {previous})"
            trace["tolerance"] = {"exact_direction": True}
            supported = calculated == claimed
        else:
            claimed, claim_unit = normalize(claim.get("asserted_value"), claim.get("unit"))
            if claim_unit != unit:
                return abstain("UNIT_INCOMPATIBLE")
            calculated = current if operation == "value_equality" else current - previous
            trace["calculation"] = str(current) if operation == "value_equality" else f"{current} - {previous}"
            if unit == "count" and claim.get("rounding_explicit") is not True:
                supported = calculated == claimed
                trace["tolerance"] = {"exact_integer_count": True}
            else:
                error = abs(calculated - claimed) / max(abs(calculated), epsilon)
                supported = error <= relative
                trace["tolerance"] = {"relative_tolerance": str(relative), "relative_error": str(error),
                                       "epsilon": str(epsilon), "denominator": "max(abs(calculated), epsilon)"}
        trace["normalized_values"]["claimed"] = str(claimed)
        trace["normalized_values"]["claimed_unit"] = ("%" if operation == "percentage_change" else
                                                         "direction" if operation == "direction_of_change" else unit)
        trace["calculated_value"] = str(calculated)
        trace["verdict"] = "SUPPORTED" if supported else "INCONSISTENT"
        trace["abstention_reason"] = None
    except (ValueError, TypeError, KeyError):
        return abstain("MISSING_OPERAND")
    return trace
