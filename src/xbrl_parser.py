"""Parse instance facts without taxonomy guesses, network calls or LLMs."""
import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path
import xml.etree.ElementTree as ET

from .units import canonical_unit, normalize, number

X = "{http://www.xbrl.org/2003/instance}"
D = "{http://xbrl.org/2006/xbrldi}"
NIL = "{http://www.w3.org/2001/XMLSchema-instance}nil"


def local(tag):
    return tag.rsplit("}", 1)[-1].rsplit(":", 1)[-1]


def boundary_name(value):
    if not value:
        return None
    text = str(value).casefold()
    if "consolidated" in text:
        return "consolidated"
    if "standalone" in text:
        return "standalone"
    return str(value).strip()


def parse_xbrl(path, company=None, year=None, filing_id=None, labels=None):
    raw = Path(path).read_bytes()
    # Ordinary instances only; reject DTD/entity expansion and inline XBRL.
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("DTD/entity declarations are not supported")
    root = ET.fromstring(raw)
    if root.tag != X + "xbrl":
        raise ValueError("Expected a conventional XBRL instance")
    digest = hashlib.sha256(raw).hexdigest()
    labels = labels or {}
    metadata = {local(e.tag): (e.text or "").strip() for e in root
                if local(e.tag) in {"NameOfTheCompany", "DateOfStartOfFinancialYear",
                                    "DateOfEndOfFinancialYear", "ReportingBoundary"}}
    actual_company = metadata.get("NameOfTheCompany") or company
    if not actual_company:
        raise ValueError("Company must be provided or present in the instance")
    if company and company.strip().casefold() != actual_company.strip().casefold():
        raise ValueError(f"Company mismatch: {company!r} vs {actual_company!r}")
    start, end = metadata.get("DateOfStartOfFinancialYear"), metadata.get("DateOfEndOfFinancialYear")
    actual_year = f"{start[:4]}-{end[2:4]}" if start and end else year
    if year and actual_year != year:
        raise ValueError(f"Reporting-year mismatch: {year} vs {actual_year}")
    contexts = {}
    for ctx in root.findall(X + "context"):
        period = ctx.find(X + "period")
        instant = period.findtext(X + "instant") if period is not None else None
        dimensions = {}
        for member in ctx.iter():
            if member.tag == D + "explicitMember":
                dimensions[member.get("dimension")] = (member.text or "").strip()
            elif member.tag == D + "typedMember":
                dimensions[member.get("dimension")] = "".join(member.itertext()).strip()
        boundary_values = {boundary_name(v) for k, v in dimensions.items()
                           if "boundary" in k.casefold() or "consolidat" in k.casefold()}
        ctx_boundary = (next(iter(boundary_values)) if len(boundary_values) == 1 else
                        "ambiguous" if boundary_values else boundary_name(metadata.get("ReportingBoundary")))
        contexts[ctx.get("id")] = {
            "period_start": period.findtext(X + "startDate") if period is not None else None,
            "period_end": instant or (period.findtext(X + "endDate") if period is not None else None),
            "period_type": "instant" if instant else "duration",
            "dimensions_json": json.dumps(dimensions, sort_keys=True), "boundary": ctx_boundary,
        }
    units = {}
    for u in root.findall(X + "unit"):
        divide = u.find(X + "divide")
        if divide is None:
            measures = [m.text or "" for m in u.findall(X + "measure")]
            units[u.get("id")] = "*".join(measures) or None
        else:
            numerator = [m.text or "" for m in divide.findall(X + "unitNumerator/" + X + "measure")]
            denominator = [m.text or "" for m in divide.findall(X + "unitDenominator/" + X + "measure")]
            units[u.get("id")] = "*".join(numerator) + "/" + "*".join(denominator)
    # Some old filings use xbrli:pure with an explicit textual UnitOf... fact.
    # Such units may be resolved only from that fact in the identical context.
    declared = {(local(e.tag)[6:], e.get("contextRef")): (e.text or "").strip()
                for e in root if local(e.tag).startswith("UnitOf") and e.get("contextRef")}
    facts = []
    for index, element in enumerate(root):
        ref = element.get("contextRef")
        if not ref or element.get(NIL) in {"true", "1"}:
            continue
        text = (element.text or "").strip()
        # A numeric fact needs numeric metadata; telephone/text/year strings are excluded.
        if not any(key in element.attrib for key in ("unitRef", "decimals", "precision")):
            continue
        try:
            value = number(text)
        except ValueError:
            continue
        concept = local(element.tag)
        measure = units.get(element.get("unitRef"))
        unit = canonical_unit(measure)
        unit_source = "measure" if measure else "missing"
        if unit == "pure" and (concept, ref) in declared:
            unit = canonical_unit(declared[concept, ref])
            unit_source = f"UnitOf{concept}@{ref}"
        try:
            normalized_value, normalized_unit = normalize(value, unit)
        except ValueError:
            normalized_value, normalized_unit = None, None
        facts.append({
            "fact_id": f"{digest[:16]}:{index}", "filing_id": filing_id or digest[:16],
            "company": actual_company, "year": actual_year, "concept": concept,
            "concept_qname": element.tag, "label": labels.get(concept),
            "value": str(value), "unit": unit, "original_value": text,
            "unit_ref": element.get("unitRef"), "unit_measure": measure, "unit_source": unit_source,
            "normalized_value": str(normalized_value) if normalized_value is not None else None,
            "normalized_unit": normalized_unit, "context_ref": ref,
            "decimals": element.get("decimals"), "source_sha256": digest,
            **contexts.get(ref, {"period_start": None, "period_end": None, "period_type": None,
                                "boundary": None, "dimensions_json": "{}"}),
        })
    return facts


COLUMNS = ["fact_id", "filing_id", "company", "year", "concept", "concept_qname", "label",
           "value", "unit", "original_value", "unit_ref", "unit_measure", "unit_source",
           "normalized_value", "normalized_unit", "context_ref", "decimals", "source_sha256",
           "period_start", "period_end", "period_type", "boundary", "dimensions_json"]


def store_facts(facts, db_path):
    if not facts:
        raise ValueError("No numeric facts were parsed; an empty ingestion cannot replace existing evidence")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as con, con:
        con.execute("CREATE TABLE IF NOT EXISTS xbrl_facts (" +
                    ",".join(f"{column} TEXT" + (" PRIMARY KEY" if column == "fact_id" else "")
                             for column in COLUMNS) + ")")
        con.execute("CREATE INDEX IF NOT EXISTS filing_idx ON xbrl_facts(filing_id)")
        # Re-ingestion replaces only this filing, preventing stale or duplicated facts.
        for filing_id in {f["filing_id"] for f in facts}:
            con.execute("DELETE FROM xbrl_facts WHERE filing_id=?", (filing_id,))
        con.executemany("INSERT INTO xbrl_facts VALUES (" + ",".join("?" for _ in COLUMNS) + ")",
                        [[f.get(c) for c in COLUMNS] for f in facts])


def load_facts(db_path, filing_id):
    with closing(sqlite3.connect(f"file:{Path(db_path).resolve().as_posix()}?mode=ro", uri=True)) as con:
        con.row_factory = sqlite3.Row
        return [dict(row) for row in con.execute("SELECT * FROM xbrl_facts WHERE filing_id=? ORDER BY fact_id",
                                              (filing_id,))]
