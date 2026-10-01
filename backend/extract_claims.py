"""
VeriBRSR - Generic PDF Claim Extraction Pipeline
================================================
Renders selected PDF pages as images, sends each page (image + text layer) to
Gemini, and collects structured, testable quantitative claims:

    c = (metric, operation, value, unit, current_period, prior_period, boundary, source)

Works on any sustainability / annual / financial report. Nothing in here is
specific to one company or one year.

USAGE
    python extract_claims.py                          # uses the defaults below
    python extract_claims.py --pdf other.pdf --pages "10-25,40" --out out.json
    python extract_claims.py --pages all --resume     # continue an interrupted run

SETUP
    pip install google-genai pymupdf python-dotenv pydantic
    .env file:  GEMINI_API_KEY=your_key

WHAT THE PIPELINE DOES BEYOND A SINGLE PROMPT
    1. Sends BOTH the page image and the PDF text layer (exact digits + layout).
    2. Forces JSON output with a response schema; salvages truncated JSON.
    3. If a dense page overflows the output limit, re-reads it as top/bottom halves.
    4. Cross-checks every value against the number printed in the passage
       (fixes Indian-format / lakh / crore slips) and against the text layer
       (flags numbers that cannot be found on the page = possible hallucination).
    5. Normalises operations, units, boundary, sign convention; removes duplicates.
    6. Throttles to your rate limit, retries transient errors, saves after every
       page (atomic write) and can resume.
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from typing import List, Optional

import pymupdf  # PyMuPDF
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

if sys.platform == "win32":  # keep Windows consoles from crashing on unicode
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ============================================================
# CONFIGURATION (all overridable from the command line)
# ============================================================

DEFAULT_PDF = r"c:\Users\jraj1\OneDrive\Desktop\xrbr\infosys2526.pdf"
DEFAULT_OUT = r"c:\Users\jraj1\OneDrive\Desktop\xrbr\backend\data\filings\2526\extracted_claims.json"

# Infosys Integrated Annual Report FY2025-26 (PDF page numbers, 1-based).
#   Narrative claims : 17, 26, 28, 30, 31, 70, 71, 79, 85
#   BRSR Section A   : 143-145   (workforce, boundary, exports, attrition)
#   BRSR training    : 160
#   BRSR Principle 6 : 173-181   (energy, water, GHG, waste, water stress, Scope 3)
DEFAULT_PAGES = "17,26,28,30,31,70,71,79,85,143-145,160,173-181"

GEMINI_MODEL = "gemini-2.5-flash"
REQUESTS_PER_MINUTE = 10        # free tier for 2.5-flash; raise it on a paid key
RENDER_SCALE = 2.5              # higher = sharper digits in dense tables
MAX_OUTPUT_TOKENS = 16384
THINKING_BUDGET = 0             # 0 = off (faster/cheaper). Try 1024 for messy pages.
MAX_TEXT_CHARS = 15000          # cap on text layer sent per call
MAX_RETRIES = 4

# Approximate paid-tier prices (USD per 1M tokens). Check current pricing.
PRICE_IN_PER_M = 0.30
PRICE_OUT_PER_M = 2.50

OPERATIONS = {"value_equality", "yoy_direction", "absolute_change", "percentage_change"}
COMPARATORS = {"exact", "approx", "at_least", "at_most"}
SOURCE_TYPES = {"prose", "table", "infographic"}
CONFIDENCES = ["low", "medium", "high"]

# ============================================================
# RESPONSE SCHEMAS (used only to constrain Gemini's JSON output)
# ============================================================


class ClaimSchema(BaseModel):
    metric: str
    metric_label: str
    qualifier: Optional[str]
    operation: str
    asserted_value: float
    value_as_printed: str
    unit: str
    comparator: str
    current_period: str
    prior_period: Optional[str]
    boundary: str
    is_target: bool
    source_passage: str
    source_type: str
    confidence: str


class PageSchema(BaseModel):
    page_has_claims: bool
    page_section: str
    claims: List[ClaimSchema]


class DocMetaSchema(BaseModel):
    company_name: str
    reporting_period: str
    period_convention: str


# ============================================================
# PROMPTS
# ============================================================

EXTRACTION_PROMPT = """You are a meticulous ESG, sustainability and financial-report analyst. You are given ONE page of a corporate report (as an image, plus its machine-readable text layer). Extract every TESTABLE QUANTITATIVE CLAIM on the page so it can later be checked, by other software, against structured filings (such as XBRL). You only READ and STRUCTURE. You never verify, compute, convert or correct anything.

=== WHAT IS A CLAIM ===
A claim is a statement that a specific measurable quantity has a specific value, or changed by a specific amount or direction, for a period. Extract claims from ALL of these places:
- Prose sentences ("Water consumption decreased by 4% to 3.79 lakh kL").
- Table cells (each row x each period column).
- Infographics, callout boxes, badges, icons and "performance highlights" (pair the big number with its label).
- Chart labels, footnotes and captions that state numbers.

=== WHAT IS NOT A CLAIM (skip) ===
Page numbers, headers/footers, dates, phone numbers, addresses, registration/identity numbers (CIN, ISIN, PAN), URLs, list numbering, footnote markers, section/question numbers, names of standards or frameworks (ISO 14001, GRI 303-3, UN SDG 13, Principle 6), and years used only as labels. Also skip qualitative statements with no number, and table cells that are NA, "-" or blank, and template rows whose every value is Nil/NA/blank. Keep explicit zeros ("Nil", 0) only when the row is a real metric with other non-zero values or a meaningful statement (e.g. "zero incidents").
Forward-looking goals and targets ("net zero by 2040", "100 million sq.ft by 2030") ARE extracted, but with is_target = true.

=== FIELDS ===
- metric: snake_case name of WHAT is measured, normalised and consistent across the document. Keep distinct things distinct: totals vs intensities vs shares; withdrawal vs consumption vs discharge; Scope 1 vs 2 vs 3; headcount vs percentage. Examples (not a closed list; invent clear names when needed): energy_consumption_total, energy_consumption_renewable, electricity_consumption, energy_intensity_per_revenue, water_withdrawal_total, water_consumption_total, water_discharge_total, water_intensity_per_fte, scope1_emissions, scope2_emissions, scope3_emissions, ghg_intensity_per_revenue, renewable_energy_share, waste_generated_total, waste_recycled, waste_landfilled, waste_diversion_rate, employee_headcount, female_representation_share, employee_turnover_rate, training_hours_per_employee, safety_incident_count, csr_spend, revenue, profit_after_tax, board_female_share, and so on.
- metric_label: the label exactly as printed near the number.
- qualifier: population / segment / source / location / dimension that narrows the metric, as short free text, or null. Examples: "female; permanent employees", "from renewable sources", "water-stressed areas", "India operations", "per FTE", "market-based", "Category 1 only". Put it here, not in the metric name, whenever it distinguishes one reported row/column from another.
- operation (choose exactly one):
  * value_equality  - a level, amount, count, share or ratio stated for one period. Default for table cells, infographics and standalone quantities (savings, avoided emissions, capacity installed, spend, percentage of something).
  * percentage_change - the text states a RELATIVE change between two periods, or versus a baseline ("reduced by 20%", "71% reduction", "grew 11%"). asserted_value is the signed percentage.
  * absolute_change - the text states an AMOUNT of change between two periods or states ("increased by 4.3 bn litres", "added 12 MW"). Do NOT use this for standalone savings or avoided amounts that are not a difference between two reported periods; use value_equality.
  * yoy_direction - only the direction is stated, no magnitude ("higher than last year"). asserted_value = +1 (increase) or -1 (decrease).
- asserted_value: the number as a plain float. NEVER rescale: keep the magnitude printed and carry the scale word in unit (2.04 lakh kWh -> 2.04, unit "lakh kWh"; 3.1 billion -> 3.1, unit "billion" or "bn"). Remove thousands separators. Indian grouping is common: "3,28,594" = 328594; "1,36,592" = 136592.
- value_as_printed: the number exactly as printed, including separators and symbols ("3,28,594", "39.5%", "`92,852 cr"). Copy from the page; do not reformat.
- unit: the unit as printed or standard shorthand: %, GJ, MWh, kWh, kL, ML, tCO2e, MT, kg, count, INR, INR cr, INR lakh, USD mn, sq.ft., hours, per FTE, etc. Use "count" for people/items and "ratio" for pure ratios.
- comparator: exact | approx (~, about, around, nearly) | at_least (over, more than, 1,000+) | at_most (up to, less than).
- current_period: the period the value refers to, normalised (see PERIODS).
- prior_period: the comparison period or baseline for change claims, else null.
- boundary: standalone | consolidated | unspecified, or a short scope phrase when the scope is narrower ("India operations", "owned campuses", "global", "permanent employees"). Use whatever the page, table title, footnote or section heading says; use "unspecified" only if nothing indicates it.
- is_target: true for goals, commitments, ambitions and plans; false for reported results.
- source_passage: the exact text or label + value from the page that supports the claim (copy, keep it short: one sentence or one table row including its label).
- source_type: prose | table | infographic.
- confidence: high (clear, unambiguous, exact digits legible), medium (some ambiguity in label/period/boundary), low (blurry, partly hidden, or you are inferring context).

=== SIGN CONVENTION ===
Decreases, reductions, savings and declines are NEGATIVE for percentage_change and absolute_change: "decreased by 2%" -> -2.0; "reduction of 71.22%" -> -71.22; "reduced emissions by 145 tCO2e" -> -145. Increases are positive. Do not apply signs to value_equality (a level is not a change), except where the source itself prints a negative number.

=== PERIODS ===
Use the document context provided below. Normalise labels to one style:
- Indian/April-March fiscal years: "FY 2025-26". A label such as "Fiscal 2026", "FY26" or "FY 2025-26" all become "FY 2025-26" when the document's fiscal year ends in March 2026 (so "Fiscal 2025" = "FY 2024-25").
- Calendar years: "CY 2025". Other conventions: keep the source label.
- Table columns with headings like "Fiscal 2026 | Fiscal 2025" mean current_period = first, prior_period = the other; but for value_equality table claims set only current_period to that column's own period and leave prior_period null.
- Point-in-time values ("as on March 31, 2026") use the period that contains that date.
- If the page gives no period for a number, use the document's reporting period from the context and set confidence to medium.
- Baselines: "since FY 2019-20", "vs 2020 baseline" -> prior_period = that baseline.

=== TABLES ===
For every data row and every period column, output one value_equality claim with that row's label as metric_label and any row/column header that narrows it as qualifier (gender, category, source, location, scope). If a table has percent-of-total columns ("% (B/A)"), output those as separate value_equality claims with unit "%". If it has an explicit growth / % change / YoY column, output percentage_change too. Use the table title, section heading and footnotes for boundary and period. Keep sub-rows and total rows distinct (e.g. "Total" vs its components). Do not add rows that are not printed, and do not compute totals or differences yourself.

=== INFOGRAPHICS / CALLOUTS ===
Numbers in coloured boxes, badges, icons, gauges or highlight strips are claims. Pair each with its nearest label ("39.5% | Women in the workforce" -> female_representation_share, 39.5, "%").

=== PROSE ===
Split compound statements into separate claims: "Emissions fell 20%, from 100 to 78 tCO2e" -> percentage_change -20 (prior FY, current FY), plus value_equality 100 for the prior period and value_equality 78 for the current period. Capture ranges as two claims (low, high) or the most relevant bound with the right comparator. Repeated facts: if the same number appears in different places (e.g. a highlight box and a table), extract it once per place; do not repeat identical entries within the same place.

=== FINAL CHECKS BEFORE YOU ANSWER ===
1. Every asserted_value matches a number visible on the page (except yoy_direction, +1/-1).
2. No number is rescaled, converted, rounded or calculated by you.
3. Signs follow the convention. Periods are normalised. Metric names are consistent.
4. If unsure whether something is a claim, include it with confidence "low" rather than omit it, unless it is clearly an identifier, page number or date.
5. If the page has no quantitative claims (cover, divider, purely qualitative), return page_has_claims = false and claims = [].
Return ONLY the JSON object that matches the required schema."""

META_PROMPT = """Below is text from the first pages of a corporate report. Identify:
- company_name: the reporting company (short common name).
- reporting_period: the main period the report covers, normalised (e.g. "FY 2025-26" for a fiscal year ending March 2026, or "CY 2024"). Do not guess beyond the text; if unclear, write "unknown".
- period_convention: one short sentence on how periods are labelled and when the fiscal year ends (e.g. "Fiscal year April-March; columns labelled 'Fiscal 2026' mean FY 2025-26"). Write "unknown" if not stated.
Return only JSON."""


# ============================================================
# PURE HELPERS (no API calls; easy to unit-test)
# ============================================================

_NUM_RE = re.compile(r"\d[\d,]*\.?\d*")
_SCALE_RE = re.compile(r"\d\s*(lakh|lakhs|lac|crore|crores|cr|million|mn|billion|bn|thousand|k)\b", re.I)
_DECREASE_RE = re.compile(r"\b(decreas\w*|reduc\w*|declin\w*|fell|fall\w*|drop\w*|lower\w*|cut|savings?|saved|avoided)\b", re.I)
_INCREASE_RE = re.compile(r"\b(increas\w*|grew|grow\w*|rose|rise\w*|higher|up|added|expanded|improv\w*)\b", re.I)

UNIT_MAP = {
    "tco2e": "tCO2e", "tco2": "tCO2e", "mtco2e": "tCO2e", "tonnes co2e": "tCO2e",
    "metric tonnes of co2 equivalent": "tCO2e", "metric tonnes co2e": "tCO2e",
    "kl": "kL", "kilolitre": "kL", "kilolitres": "kL", "kiloliter": "kL", "kiloliters": "kL",
    "percent": "%", "per cent": "%", "percentage": "%", "pct": "%",
    "gj": "GJ", "gigajoule": "GJ", "gigajoules": "GJ",
    "mwh": "MWh", "kwh": "kWh", "mt": "MT", "tonnes": "MT", "tonne": "MT", "tons": "MT",
    "number": "count", "no.": "count", "nos": "count", "headcount": "count",
    "rs": "INR", "inr": "INR", "rupees": "INR",
}


def parse_pages(spec: str, total: int) -> List[int]:
    """'10-12,40' -> [10, 11, 12, 40]; 'all' -> every page. Out-of-range pages are dropped."""
    if spec.strip().lower() == "all":
        return list(range(1, total + 1))
    pages = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            pages.extend(range(int(a), int(b) + 1))
        else:
            pages.append(int(part))
    seen, out = set(), []
    for p in pages:
        if 1 <= p <= total and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def parse_printed_number(s: str) -> Optional[float]:
    """Parse the single number in a printed string ('3,28,594' -> 328594.0).
    Returns None when ambiguous (several numbers) or when a scale word follows
    (lakh, crore, million ...), because the pipeline never rescales."""
    if not s:
        return None
    if _SCALE_RE.search(s):
        return None
    nums = _NUM_RE.findall(s)
    if len(nums) != 1:
        return None
    try:
        return float(nums[0].replace(",", "").rstrip("."))
    except ValueError:
        return None


def parse_json_lenient(text: str):
    """Parse model JSON. If it was cut off, salvage every complete claim object.
    Returns (data, salvaged_flag)."""
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t).strip()
    try:
        return json.loads(t), False
    except json.JSONDecodeError:
        pass
    m = re.search(r'"claims"\s*:\s*\[', t)
    if not m:
        raise ValueError("unparseable model output")
    body, objs, depth, start, in_str, esc = t[m.end():], [], 0, None, False, False
    for i, ch in enumerate(body):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    objs.append(json.loads(body[start:i + 1]))
                except json.JSONDecodeError:
                    pass
                start = None
    sec = re.search(r'"page_section"\s*:\s*"([^"]*)"', t)
    return {"page_has_claims": bool(objs), "page_section": sec.group(1) if sec else "Unknown",
            "claims": objs}, True


def _clean(s) -> str:
    return re.sub(r"\s+", " ", str(s)).strip() if s is not None else ""


def normalize_boundary(b: str) -> str:
    b = _clean(b).lower()
    if not b:
        return "unspecified"
    if "consolidat" in b:
        return "consolidated"
    if "standalone" in b:
        return "standalone"
    return b


def normalize_unit(u: str) -> str:
    u = _clean(u)
    return UNIT_MAP.get(u.lower(), u)


def is_number_on_page(printed: str, text_norm: str) -> Optional[bool]:
    nums = _NUM_RE.findall(printed or "")
    if not nums:
        return None
    target = nums[0].replace(",", "").rstrip(".")
    return re.search(r"(?<![\d.])" + re.escape(target) + r"(?!\d|\.\d)", text_norm) is not None


def normalize_claim(raw: dict, page_num: int, seq: int, doc_period: str,
                    text_norm: str, has_text: bool) -> Optional[dict]:
    """Validate, repair and enrich one raw claim. Returns None if unusable."""
    flags = []
    try:
        value = float(raw.get("asserted_value"))
    except (TypeError, ValueError):
        return None
    if value != value or value in (float("inf"), float("-inf")):
        return None

    passage = _clean(raw.get("source_passage"))
    if not passage:
        return None
    printed = _clean(raw.get("value_as_printed"))
    metric = re.sub(r"[^a-z0-9]+", "_", _clean(raw.get("metric")).lower()).strip("_") or "unknown_metric"

    op = _clean(raw.get("operation")).lower()
    if op not in OPERATIONS:
        flags.append("unknown_operation:" + (op or "empty"))
        op = "value_equality"

    if op == "yoy_direction":
        value = 1.0 if value > 0 else (-1.0 if value < 0 else 0.0)
    else:
        p = parse_printed_number(printed)
        if p is not None and abs(abs(value) - abs(p)) > 1e-12 + 0.005 * abs(p):
            flags.append("value_corrected_from_%g" % value)
            value = p if value >= 0 else -p

    # Sign convention (only when the wording is unambiguous)
    if op in ("percentage_change", "absolute_change") and value > 0:
        dec, inc = _DECREASE_RE.search(passage), _INCREASE_RE.search(passage)
        if dec and not inc:
            value = -value
            flags.append("sign_flipped_to_negative")
        elif dec and inc:
            flags.append("sign_ambiguous")

    comparator = _clean(raw.get("comparator")).lower()
    if comparator not in COMPARATORS:
        comparator = "exact"
    source_type = _clean(raw.get("source_type")).lower()
    if source_type not in SOURCE_TYPES:
        source_type = "prose"
    confidence = _clean(raw.get("confidence")).lower()
    if confidence not in CONFIDENCES:
        confidence = "medium"

    current = _clean(raw.get("current_period"))
    if not current or current.lower() in ("unknown", "null", "none"):
        current = doc_period
        flags.append("period_defaulted_to_document")
    prior = _clean(raw.get("prior_period")) or None
    if prior and prior.lower() in ("null", "none", "unknown", "n/a"):
        prior = None
    if op in ("percentage_change", "absolute_change", "yoy_direction") and not prior:
        flags.append("no_baseline_period")

    grounded = None
    if has_text and printed and op != "yoy_direction":
        grounded = is_number_on_page(printed, text_norm)
        if grounded is False:
            flags.append("number_not_in_text_layer")
            confidence = CONFIDENCES[max(0, CONFIDENCES.index(confidence) - 1)]

    return {
        "claim_id": "CLM-P%03d-%03d" % (page_num, seq),
        "page_number": page_num,
        "metric": metric,
        "metric_label": _clean(raw.get("metric_label")),
        "qualifier": _clean(raw.get("qualifier")) or None,
        "operation": op,
        "asserted_value": value,
        "value_as_printed": printed,
        "unit": normalize_unit(raw.get("unit")),
        "comparator": comparator,
        "current_period": current,
        "prior_period": prior,
        "boundary": normalize_boundary(raw.get("boundary")),
        "is_target": bool(raw.get("is_target", False)),
        "source_passage": passage,
        "source_type": source_type,
        "confidence": confidence,
        "grounded_in_text_layer": grounded,
        "flags": flags,
    }


def dedupe(claims: List[dict]) -> List[dict]:
    seen, out = set(), []
    for c in claims:
        key = (c["page_number"], c["metric"], c["qualifier"], c["operation"], round(c["asserted_value"], 9),
               c["unit"], c["current_period"], c["prior_period"], c["boundary"])
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


# ============================================================
# GEMINI CLIENT WRAPPER
# ============================================================


class Extractor:
    def __init__(self, api_key: str, model: str, rpm: int, scale: float, thinking: int):
        from google import genai
        from google.genai import types
        self.types = types
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.min_interval = 60.0 / max(1, rpm) + 0.5
        self.scale = scale
        self.thinking = thinking
        self.use_schema = True
        self.last_call = 0.0
        self.calls = 0
        self.tokens_in = 0
        self.tokens_out = 0

    def _throttle(self):
        wait = self.min_interval - (time.time() - self.last_call)
        if wait > 0:
            time.sleep(wait)
        self.last_call = time.time()

    def _call(self, contents, system_instruction: str, schema):
        types = self.types
        for attempt in range(MAX_RETRIES):
            self._throttle()
            try:
                kwargs = dict(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    temperature=0.0,
                    max_output_tokens=MAX_OUTPUT_TOKENS,
                )
                if self.use_schema:
                    kwargs["response_schema"] = schema
                if hasattr(types, "ThinkingConfig"):
                    kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=self.thinking)
                resp = self.client.models.generate_content(
                    model=self.model, contents=contents,
                    config=types.GenerateContentConfig(**kwargs))
                self.calls += 1
                u = getattr(resp, "usage_metadata", None)
                if u:
                    self.tokens_in += getattr(u, "prompt_token_count", 0) or 0
                    self.tokens_out += (getattr(u, "candidates_token_count", 0) or 0) + \
                                       (getattr(u, "thoughts_token_count", 0) or 0)
                finish = ""
                try:
                    finish = str(resp.candidates[0].finish_reason)
                except Exception:
                    pass
                return (resp.text or ""), ("MAX_TOKENS" in finish)
            except Exception as e:  # noqa: BLE001
                s = str(e)
                if self.use_schema and "INVALID_ARGUMENT" in s and "schema" in s.lower():
                    print("[WARN] schema rejected by API; continuing without response_schema", flush=True)
                    self.use_schema = False
                    continue
                transient = any(k in s for k in ("429", "RESOURCE_EXHAUSTED", "500", "503", "UNAVAILABLE", "DEADLINE"))
                if transient and attempt < MAX_RETRIES - 1:
                    backoff = min(90, 10 * (2 ** attempt))
                    print("[RETRY %d/%d] transient API error, waiting %ds" % (attempt + 1, MAX_RETRIES - 1, backoff), flush=True)
                    time.sleep(backoff)
                    continue
                raise
        raise RuntimeError("retries exhausted")

    # ---------- document metadata ----------
    def detect_metadata(self, doc) -> dict:
        try:
            chunks = []
            for i in range(min(3, doc.page_count)):
                chunks.append("--- page %d ---\n%s" % (i + 1, doc[i].get_text("text")[:2500]))
            text, _ = self._call([META_PROMPT + "\n\n" + "\n".join(chunks)], "You extract document metadata.", DocMetaSchema)
            data = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip()))
            return {"company_name": _clean(data.get("company_name")) or "Unknown",
                    "reporting_period": _clean(data.get("reporting_period")) or "unknown",
                    "period_convention": _clean(data.get("period_convention")) or "unknown"}
        except Exception as e:  # noqa: BLE001
            print("[WARN] metadata detection failed (%s); use --company/--year" % str(e)[:80], flush=True)
            return {"company_name": "Unknown", "reporting_period": "unknown", "period_convention": "unknown"}

    # ---------- one region of one page ----------
    def _read_region(self, page, page_num: int, meta: dict, clip=None, region_note: str = ""):
        pix = page.get_pixmap(matrix=pymupdf.Matrix(self.scale, self.scale), clip=clip)
        img = pix.tobytes("png")
        text = page.get_text("text", clip=clip).strip()[:MAX_TEXT_CHARS]
        ctx = (
            "DOCUMENT CONTEXT\n"
            "- Company: %s\n- Reporting period of this document: %s\n- Period labelling: %s\n"
            "- PDF page number: %d\n%s\n"
            "TEXT LAYER of this page (exact digits; may be out of order or garbled - the image is authoritative "
            "for layout, labels and column meaning):\n<<<\n%s\n>>>\n"
            "Now extract all claims from the page image."
        ) % (meta["company_name"], meta["reporting_period"], meta["period_convention"], page_num,
             region_note, text if text else "(no text layer - rely on the image)")
        contents = [self.types.Part.from_bytes(data=img, mime_type="image/png"), ctx]
        raw, truncated = self._call(contents, EXTRACTION_PROMPT, PageSchema)
        data, salvaged = parse_json_lenient(raw)
        return data, (truncated or salvaged)

    # ---------- one page ----------
    def process_page(self, doc, page_num: int, meta: dict):
        page = doc[page_num - 1]
        text = page.get_text("text")
        has_text = len(text.strip()) >= 20
        n_numbers = len(re.findall(r"\d+", text))
        if has_text and n_numbers < 2 and len(text.strip()) < 150:
            return [], {"page": page_num, "section": "Divider/Cover", "claims_found": 0,
                        "has_claims": False, "skipped": "non-quantitative"}

        raw_claims, section, split_used, still_truncated = [], "Unknown", False, False
        data, truncated = self._read_region(page, page_num, meta)
        section = data.get("page_section", section)
        raw_claims.extend(data.get("claims", []))

        if truncated:  # dense page: re-read as two overlapping halves
            split_used = True
            r = page.rect
            mid, ov = r.y0 + r.height / 2, r.height * 0.04
            halves = [(pymupdf.Rect(r.x0, r.y0, r.x1, mid + ov), "This image is the TOP part of the page only."),
                      (pymupdf.Rect(r.x0, mid - ov, r.x1, r.y1), "This image is the BOTTOM part of the page only.")]
            raw_claims = []
            for clip, note in halves:
                d, t = self._read_region(page, page_num, meta, clip=clip,
                                         region_note="- " + note + " Extract only claims fully visible here.")
                raw_claims.extend(d.get("claims", []))
                still_truncated = still_truncated or t

        text_norm = text.replace(",", "")
        claims = []
        for raw in raw_claims:
            c = normalize_claim(raw, page_num, len(claims) + 1, meta["reporting_period"], text_norm, has_text)
            if c:
                claims.append(c)
        before = len(claims)
        claims = dedupe(claims)
        for i, c in enumerate(claims, 1):  # re-number after dedupe
            c["claim_id"] = "CLM-P%03d-%03d" % (page_num, i)

        return claims, {"page": page_num, "section": section, "claims_found": len(claims),
                        "has_claims": bool(claims), "duplicates_removed": before - len(claims),
                        "split_into_halves": split_used, "possibly_truncated": still_truncated,
                        "has_text_layer": has_text}


# ============================================================
# OUTPUT
# ============================================================

CSV_FIELDS = ["claim_id", "page_number", "metric", "qualifier", "operation", "asserted_value", "value_as_printed",
              "unit", "comparator", "current_period", "prior_period", "boundary", "is_target", "source_type",
              "confidence", "grounded_in_text_layer", "flags", "metric_label", "source_passage"]


def save_results(path: str, meta: dict, pdf_path: str, total_pages: int, summaries: list,
                 claims: list, ex: Extractor, model: str, write_csv: bool = True):
    cost = ex.tokens_in * PRICE_IN_PER_M / 1e6 + ex.tokens_out * PRICE_OUT_PER_M / 1e6
    out = {
        "metadata": {
            "company": meta["company_name"], "reporting_period": meta["reporting_period"],
            "period_convention": meta["period_convention"], "pdf": os.path.basename(pdf_path),
            "total_pdf_pages": total_pages, "pages_processed": len(summaries),
            "total_claims": len(claims), "model": model, "api_calls_this_run": ex.calls,
            "input_tokens_this_run": ex.tokens_in, "output_tokens_this_run": ex.tokens_out,
            "estimated_paid_cost_usd_this_run": round(cost, 4),
        },
        "page_summaries": sorted(summaries, key=lambda s: s["page"]),
        "claims": claims,
    }
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)
    if write_csv:
        with open(os.path.splitext(path)[0] + ".csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
            w.writeheader()
            for c in claims:
                row = dict(c)
                row["flags"] = "; ".join(c.get("flags", []))
                w.writerow(row)


# ============================================================
# MAIN
# ============================================================


def main():
    ap = argparse.ArgumentParser(description="VeriBRSR generic PDF claim extraction")
    ap.add_argument("--pdf", default=DEFAULT_PDF)
    ap.add_argument("--pages", default=DEFAULT_PAGES, help='e.g. "10-25,40" or "all"')
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--company", default=None, help="override auto-detected company")
    ap.add_argument("--year", default=None, help='override auto-detected period, e.g. "FY 2025-26"')
    ap.add_argument("--model", default=GEMINI_MODEL)
    ap.add_argument("--rpm", type=int, default=REQUESTS_PER_MINUTE)
    ap.add_argument("--scale", type=float, default=RENDER_SCALE)
    ap.add_argument("--thinking", type=int, default=THINKING_BUDGET)
    ap.add_argument("--resume", action="store_true", help="skip pages already in the output file")
    ap.add_argument("--no-csv", action="store_true")
    args = ap.parse_args()

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: set GEMINI_API_KEY in your .env file")
        sys.exit(1)
    if not os.path.exists(args.pdf):
        print("ERROR: PDF not found: %s" % args.pdf)
        sys.exit(1)

    doc = pymupdf.open(args.pdf)
    pages = parse_pages(args.pages, doc.page_count)
    if not pages:
        print("ERROR: no valid pages in --pages for a %d-page PDF" % doc.page_count)
        sys.exit(1)

    ex = Extractor(api_key, args.model, args.rpm, args.scale, args.thinking)

    all_claims, summaries, done = [], [], set()
    if args.resume and os.path.exists(args.out):
        with open(args.out, encoding="utf-8") as f:
            prev = json.load(f)
        all_claims = prev.get("claims", [])
        summaries = prev.get("page_summaries", [])
        done = {s["page"] for s in summaries if not s.get("error")}
        print("[RESUME] %d pages already done" % len(done), flush=True)

    meta = ex.detect_metadata(doc)
    if args.company:
        meta["company_name"] = args.company
    if args.year:
        meta["reporting_period"] = args.year

    todo = [p for p in pages if p not in done]
    est = len(todo) * (ex.min_interval + 4)
    print("=" * 62)
    print("VeriBRSR claim extraction")
    print("PDF     : %s (%d pages)" % (os.path.basename(args.pdf), doc.page_count))
    print("Company : %s | Period: %s" % (meta["company_name"], meta["reporting_period"]))
    print("Pages   : %d to process %s" % (len(todo), todo))
    print("Model   : %s | %d RPM | est. time ~%.0f s" % (args.model, args.rpm, est))
    print("=" * 62, flush=True)

    for i, pn in enumerate(todo, 1):
        print("[%d/%d] page %d ... " % (i, len(todo), pn), end="", flush=True)
        try:
            claims, summ = ex.process_page(doc, pn, meta)
        except Exception as e:  # noqa: BLE001
            print("[ERROR] %s" % str(e)[:100], flush=True)
            summaries = [s for s in summaries if s["page"] != pn]
            summaries.append({"page": pn, "section": "Error", "claims_found": 0, "has_claims": False,
                              "error": str(e)[:300]})
            save_results(args.out, meta, args.pdf, doc.page_count, summaries, all_claims, ex, args.model, not args.no_csv)
            continue
        all_claims = [c for c in all_claims if c["page_number"] != pn] + claims
        summaries = [s for s in summaries if s["page"] != pn] + [summ]
        tag = "[SKIP]" if summ.get("skipped") else "[OK]"
        extra = " split" if summ.get("split_into_halves") else ""
        extra += " TRUNCATED" if summ.get("possibly_truncated") else ""
        print("%s %d claims [%s]%s" % (tag, len(claims), summ["section"], extra), flush=True)
        save_results(args.out, meta, args.pdf, doc.page_count, summaries, all_claims, ex, args.model, not args.no_csv)

    doc.close()

    # ---------- summary ----------
    print("\n" + "=" * 62)
    print("DONE  total claims: %d | API calls: %d | tokens in/out: %s/%s" % (
        len(all_claims), ex.calls, format(ex.tokens_in, ","), format(ex.tokens_out, ",")))
    by_op, by_conf = {}, {}
    for c in all_claims:
        by_op[c["operation"]] = by_op.get(c["operation"], 0) + 1
        by_conf[c["confidence"]] = by_conf.get(c["confidence"], 0) + 1
    print("By operation :", by_op)
    print("By confidence:", by_conf)
    ungrounded = [c for c in all_claims if c.get("grounded_in_text_layer") is False]
    corrected = [c for c in all_claims if any(f.startswith("value_corrected") for f in c.get("flags", []))]
    print("Numbers not found in text layer (review): %d | values auto-corrected: %d" % (len(ungrounded), len(corrected)))
    bad_pages = [s["page"] for s in summaries if s.get("error") or s.get("possibly_truncated")]
    if bad_pages:
        print("Pages needing a re-run or manual check:", sorted(bad_pages))
    print("Saved:", args.out)
    print("=" * 62)


if __name__ == "__main__":
    main()
