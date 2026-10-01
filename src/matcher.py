"""Transparent alias/fuzzy ranking after period, unit and boundary filtering."""
import json
import re
from difflib import SequenceMatcher

from .units import compatible, canonical_unit, TABLE
from .xbrl_parser import boundary_name

ALIASES = {
    "total_water_consumption": ["water consumption", "total water consumption", "TotalVolumeOfWaterConsumption"],
    "scope_1_emissions": ["scope 1 emissions", "total scope 1 emissions", "TotalScope1Emissions"],
    "scope_2_emissions": ["scope 2 emissions", "total scope 2 emissions", "TotalScope2Emissions"],
    "total_energy_consumption": ["energy consumption", "total energy consumption", "TotalEnergyConsumption",
                                 "TotalEnergyConsumedFromRenewableAndNonRenewableSources"],
    "total_waste": ["total waste", "total waste generated", "TotalWasteGenerated"],
    "total_employees": ["total employees", "NumberOfEmployeesOrWorkersIncludingDifferentlyAbled"],
    "female_employees_percentage": ["female employees percentage", "PercentageOfFemaleEmployees"],
}
ALIASES["water_consumption"] = ALIASES["total_water_consumption"]


def words(text):
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", str(text or ""))
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def metric_key(metric):
    target = words(metric)
    for key, aliases in ALIASES.items():
        if target in {words(key), *(words(a) for a in aliases)}:
            return "total_water_consumption" if key == "water_consumption" else key
    return None


def metric_score(metric, fact):
    key = metric_key(metric)
    if key is None:
        return 0.0
    names = [words(fact["concept"]), words(fact.get("label"))]
    aliases = [words(key), *(words(a) for a in ALIASES[key])]
    # Do not confuse a total with an intensity, Scope 1 with Scope 2, or a
    # consumption total with withdrawal/discharge. Exact aliases score highest.
    concept_key = metric_key(fact["concept"])
    if concept_key and concept_key != key:
        return 0.0
    if any(a == n for a in aliases for n in names if n):
        return 1.0
    if "renewable" in names[0] or "non renewable" in names[0]:
        return 0.0  # a component cannot replace a missing energy total
    if key in {"scope_1_emissions", "scope_2_emissions"}:
        scopes = set(re.findall(r"scope\s*(\d)", names[0]))
        if scopes != {"1" if key == "scope_1_emissions" else "2"}:
            return 0.0
    if any(t in names[0].split() for t in ("intensity", "area", "withdrawal", "discharged", "scope3")):
        return 0.0
    return max(SequenceMatcher(None, a, n).ratio() for a in aliases for n in names if n)


def period_matches(period, fact):
    if isinstance(period, dict):
        return all(fact.get("period_" + k) == period.get(k) for k in ("start", "end", "type") if k in period) and bool(period.get("end"))
    text = str(period or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return fact.get("period_type") == "instant" and fact.get("period_end") == text
    match = re.fullmatch(r"(?:FY\s*)?(\d{4})[-–](\d{2}|\d{4})", text, re.I)
    if not match:
        return False
    start_year = int(match[1])
    end_year = int(match[2]) if len(match[2]) == 4 else (start_year // 100) * 100 + int(match[2])
    if end_year != start_year + 1:
        return False
    return (fact.get("period_type") == "duration" and
            fact.get("period_start") == f"{start_year}-04-01" and
            fact.get("period_end") == f"{end_year}-03-31")


def scope_dimensions(fact):
    dims = json.loads(fact.get("dimensions_json") or "{}")
    return {k: v for k, v in dims.items() if not any(w in k.casefold() for w in ("boundary", "consolidat"))}


def retrieve(claim, facts, settings=None):
    settings = settings or {}
    threshold = float(settings.get("minimum_similarity", 0.82))
    margin = float(settings.get("ambiguity_margin", 0.04))
    result = {"current": None, "previous": None, "candidates": {}, "reason": None}
    if not claim.get("current_period") or (claim.get("operation") != "value_equality" and not claim.get("previous_period")):
        result["reason"] = "MISSING_PERIOD"
        return result
    for key in ["current_period"] + (["previous_period"] if claim.get("operation") != "value_equality" else []):
        period = claim[key]
        if not isinstance(period, dict) and not re.fullmatch(r"(?:FY\s*)?\d{4}[-–](?:\d{2}|\d{4})|\d{4}-\d{2}-\d{2}", str(period), re.I):
            result["reason"] = "MISSING_PERIOD"
            return result
    scoped = [f for f in facts if f.get("company") == claim.get("company") and
              f.get("filing_id") == claim.get("filing_id")]
    required = ["current"] + (["previous"] if claim.get("operation") != "value_equality" else [])
    for operand in required:
        period = claim.get(operand + "_period")
        # Filter dates/units first, then rank using concept names, never values.
        dated = [f for f in scoped if period_matches(period, f)]
        target_unit = claim.get("unit") if claim.get("operation") in {"value_equality", "absolute_change"} else claim.get("metric_unit")
        united = [f for f in dated if (compatible(f.get("unit"), target_unit) if target_unit else
                                       canonical_unit(f.get("unit")) in TABLE)]
        # Missing units on scalar value/change claims must not be filled from facts.
        if claim.get("operation") in {"value_equality", "absolute_change"} and not target_unit:
            result["reason"] = "UNIT_INCOMPATIBLE"
            return result
        def ranked(items):
            return sorted([{"score": metric_score(claim.get("metric"), f), "fact": f} for f in items
                           if metric_score(claim.get("metric"), f) >= threshold],
                          key=lambda item: (-item["score"], item["fact"]["fact_id"]))
        candidates = ranked(united)
        result["candidates"][operand] = candidates
        if not candidates:
            result["reason"] = ("NO_MATCHING_FACT" if not ranked(scoped) else
                                "MISSING_OPERAND" if not ranked(dated) else "UNIT_INCOMPATIBLE")
            return result
        boundary = boundary_name(claim.get("boundary"))
        if not boundary:
            result["reason"] = "BOUNDARY_AMBIGUOUS"
            return result
        candidates = [c for c in candidates if c["fact"].get("boundary") == boundary]
        if not candidates:
            result["reason"] = "BOUNDARY_AMBIGUOUS"
            return result
        wanted_dims = claim.get("dimensions") or {}
        candidates = [c for c in candidates if scope_dimensions(c["fact"]) == wanted_dims]
        if not candidates:
            result["reason"] = "MULTIPLE_PLAUSIBLE_FACTS"
            return result
        if len(candidates) > 1 and candidates[0]["score"] - candidates[1]["score"] <= margin:
            result["reason"] = "MULTIPLE_PLAUSIBLE_FACTS"
            return result
        result[operand] = candidates[0]["fact"]
    if result["previous"]:
        cur, prev = result["current"], result["previous"]
        if (cur["concept_qname"] != prev["concept_qname"] or scope_dimensions(cur) != scope_dimensions(prev)
                or cur.get("boundary") != prev.get("boundary") or not compatible(cur.get("unit"), prev.get("unit"))):
            result["reason"] = "MISSING_OPERAND"
        elif cur["period_end"] <= prev["period_end"] or cur["period_type"] != prev["period_type"]:
            result["reason"] = "MISSING_PERIOD"
    return result
