# VeriBRSR

A research prototype that checks quantitative statements in Indian sustainability
reports against the same company's XBRL filing. Gemini extracts or interprets the
claim; deterministic Python retrieves evidence, converts units and calculates
VeriBRSR's verdict. Agreement establishes consistency with a filing, not the truth
of a company's underlying disclosures.

## Current experiment

All ten real PDF/XBRL pairs are materialized: seven development companies and
three test companies, with source URLs, download dates and document hashes in
`data/provenance.json`. The research pipeline lives in `src/`, `data/`, `prompts/`
and `experiments/`; the older backend and Next.js interface remain exploratory.
Run `py -3.13 -m src.cli status` for current dataset and evaluation readiness.

The dataset contains 54 sourced claims and 40 mutations: 66 development examples
and 28 test examples. All 21 offline correctness tests pass. Four-system
development predictions are in `experiments/development_predictions.csv`.
The completed four-system test comparison contains 112 prediction rows. See
[pilot results](experiments/results.md), [metrics](experiments/metrics.json) and
[protocol history](experiments/protocol_notes.json).

The configured experiment uses **automated source references**, not independently
annotated human gold labels. Exact XBRL concepts supply reference evidence and
calculations in `data/reference_reviews.json`. Scores measure agreement with these
automatic references. Shared parsing, units, arithmetic and LLM-extracted claim
interpretations limit the independence of that comparison. No human agreement
score or independent accuracy claim is available.

The first frozen test attempt exposed six examples before a baseline emitted an
invalid label. A bounded response-format repair was then added, development was
rerun, and the revised code was frozen again. This is a company-separated pilot
comparison with disclosed test exposure, not an untouched confirmatory benchmark.
The original freeze and partial results are preserved in `experiments/`.

The configured model is `gemini-3.5-flash-lite`. The preferred
`gemini-3.5-flash` previously returned HTTP 503 after bounded retries; the switch
is explicit in `config.yaml`. Successful responses record requested/resolved
models, prompts, UTC timestamps, provider responses, runtime and library versions.
There is no silent fallback. Provider 502/503/504 errors receive at most two
retries; quota errors stop immediately.

## Setup

Python 3.13.0 and pinned dependencies are used. On this Windows workspace,
`py -3.13` selects the interpreter with the research dependencies; the existing
backend virtual environment is a separate environment.

```powershell
py -3.13 -m pip install -r requirements.txt
py -3.13 -m unittest discover -s tests -v
py -3.13 -m src.cli status
```

Set `GEMINI_API_KEY` in the shell or the ignored `backend/.env`. Keys never enter
configuration, request URLs or run logs. The optional `json_endpoint` provider
accepts `{model,prompt,temperature,max_output_tokens}` and returns `{text,model}`.

## Reproducible workflow

1. Register exactly ten company-year slots in `data/filings.csv`, preserving a
   7/3 company split. `py -3.13 -m src.acquire_filings` acquires missing NSE pairs,
   validates their XML identity and stores numeric facts idempotently in SQLite.
2. Select BRSR pages in `data/page_ranges.yaml`. Page numbers are 1-based PDF
   positions. `py -3.13 -m src.discover_pages` provides text-search selections;
   inspect their table headings and boundary context. Only text-layer PDFs are
   supported. Whole reports are never sent to Gemini.
3. Build development claims and source references:

```powershell
py -3.13 -m src.build_dataset --split development
py -3.13 -m experiments.run --split development --batch --output experiments/development_predictions.csv
```

The builder copies 5-8 exact PDF passages per filing. It selects up to 28
mutation sentences from automatically supported development parents, using seed
42. Mutations alter actual sentence spans and their structured fields. Unavailable
mutation types are skipped; modified examples are never automatically assumed to
be inconsistent. References are explicitly marked as automatic.

4. Freeze implementation/configuration before constructing test references or
   examining held-out system outcomes, then run the three test companies:

```powershell
py -3.13 -m src.cli freeze
py -3.13 -m src.build_dataset --split test
py -3.13 -m src.cli validate --complete
py -3.13 -m experiments.run --split test --batch
py -3.13 -m experiments.evaluate
```

The test builder selects up to 12 mutations. Complete validation requires all ten
pairs, 5-8 genuine natural passages per filing, 40 mutations across both splits,
and source-reference records matching document hashes, passages and evidence IDs.
A missing test split cannot count as a complete dataset.

Batch requests contain at most six claims by default (`--batch-size 1-8`).
Natural claims reuse their exact archived extraction response; altered sentences
receive fresh interpretation. Gold/reference labels and reference evidence IDs
never enter baseline prompts. Finished chunks checkpoint to `.partial.csv`,
including their full traces. Failed API calls never become predictions. An invalid baseline response gets one
format-repair request using the same claims/evidence; its raw response and
validation error are retained. A second invalid response stops the run. Reruns
reuse cached successful calls without repeating their API requests.

The completed experiment's `data/llm_runs/` responses are included in Git;
new cache files remain ignored until explicitly archived. `.gitattributes`
preserves experiment inputs and outputs byte-for-byte so saved hashes remain
valid after cloning on another platform. Custom
outputs have adjacent `.traces.jsonl` and `.run.json` files, preserving development
and test traces separately. Metadata records dataset, implementation and prediction
hashes. Evaluation rejects changed documents/references, mismatched predictions,
duplicate rows, missing examples and unequal example sets between systems.

## Numerical decisions and baselines

VeriBRSR's verifier has no network dependency. It supports value equality,
signed absolute/percentage changes and direction. Scalar values use
`abs(calculated-claimed)/max(abs(calculated),1e-12) <= 0.01`; percentage changes
use 0.5 percentage points. Integer counts are exact unless source rounding is
explicit. A zero percentage denominator yields `ZERO_DENOMINATOR`.

Supported explicit units include kL/L, GJ/MWh/kWh, tCO2e/kgCO2e, tonnes, counts
and percentages. XML unit measures determine units; an identical-context textual
unit fact can resolve older dimensionless declarations. Missing/unknown units
stay unknown; `MtCO2e` remains unresolved without documentary clarification.

Retrieval filters periods, units, boundaries and dimensions before alias/fuzzy
ranking. Close alternatives yield `MULTIPLE_PLAUSIBLE_FACTS`; missing boundaries
yield `BOUNDARY_AMBIGUOUS`. Arbitrary component sums, employee gender ratios,
intensity-to-total conversions and dates guessed from context IDs are unsupported.
Explicit fiscal ranges assume April-March; other calendars require date objects.

Exactly three baselines are compared on the same examples: raw-text keyword/fuzzy
retrieval plus calculator; LLM only with same-filing metric-family facts; and
retrieval plus LLM with VeriBRSR's evidence. Only the two LLM baselines ask a model
to decide the verdict. Raw keyword rules may abstain on complex table headings.

`experiments/metrics.json` reports natural, modified and combined test results:
INCONSISTENT precision/recall/F1, fixed three-class macro F1, false-positive rates,
coverage, confusion matrices and exact evidence-ID agreement where reference IDs
exist. Two empty evidence sets receive no grounding credit. Undefined class
P/R/F1 is zero; missing FPR/grounding denominators produce null. Batched LLM
per-example runtime is unmeasured; batch API wall time remains in run provenance.

## Independent annotation

`data/ANNOTATION_GUIDE.md` describes a future independent human annotation study.
The current JSON field names `gold_label` and `gold_xbrl_fact_ids` carry automatic
references for compatibility, not human gold. `annotation-pack` can export blind
source material; do not claim independent evaluation until real annotators have
reviewed it and the human-label validation/evaluation workflow is implemented.
No kappa result exists for this automated experiment.
