# VeriBRSR — Complete Implementation Roadmap

> **What this is:** the ordered, do-it-literally build plan for the project defined in `BRSR_Claim_Verification_v2.md`. Every phase, manual and technical, with the exact actions, the artifact it produces, and the exit criterion that tells you it's done. Follow top to bottom.
> **No timelines.** Phases are sequenced by dependency, not dates. Where a phase can run in parallel, it says so.
> **Modifiable:** anything here can change during implementation — but the *order of dependencies* (engine before LLM, definitions before annotation, split-by-company before evaluation) must not.
> **The prime directive (never violate):** verify **derived** claims (%, direction, YoY, absolute change), never trivial raw value-equality. LLM extracts language; the deterministic engine does all math and renders every verdict.

---

## How to read this

Each phase has:
- **Type** — 🖐 manual / ⚙️ technical / 🔀 both
- **Goal** — one sentence
- **Do exactly this** — numbered actions
- **Produces** — the artifact(s) that must exist when the phase ends
- **Exit criterion** — the measurable check that lets you move on
- **⛔ Go/No-Go** — appears only on phases that can kill or reshape the project

**Dependency map (the spine):**
```
P0 Setup
  └─ P1 Feasibility probe ⛔  ── decides go/no-go ──┐
       └─ P2 Freeze definitions                     │
            ├─ P3 Data acquisition ──┐              │
            │                        ├─ P4 XBRL parse + concept dict
            │                        │      └─ P5 Deterministic engine (BUILD FIRST)
            │                        │             └─ P7 Candidate filter
            │                        │                    └─ P8 LLM extraction
            │                        │                           └─ P9 Grounding/retrieval
            └─ P6 Annotation manual + pilot ⛔ (κ)         └─ P10 Integrate pipeline + abstention
                        └──────────── P11 Build BRSR-Claim (natural + perturbations) + splits
                                             └─ P12 Baselines
                                                    └─ P13 Freeze + final eval + ablations ⛔
                                                           └─ P14 Error analysis
                                                                  └─ P15 PAPER-READY ✅
                                                                         └─ P16 Repro bundle + demo
```
**Paper writing runs in parallel** from P2 onward (Intro/Related Work/Method draftable early; Results only after P13). See §"When exactly are we ready to write the paper".

---

## Phase 0 — Project & environment setup
**Type:** ⚙️ **Goal:** a clean, reproducible workspace before any data touches disk.

**Do exactly this:**
1. Install Python 3.11+, Git, and a virtual env: `python -m venv .venv` → activate.
2. `pip install` the core stack: `arelle-release lxml pandas numpy pydantic duckdb pymupdf pdfplumber beautifulsoup4 spacy sentence-transformers scikit-learn pint python-decimal-is-builtin pytest ruff mypy dvc matplotlib fastapi uvicorn streamlit`. (`decimal` is stdlib — no install.)
3. `python -m spacy download en_core_web_sm`.
4. `git init`; add `.gitignore` (ignore `data/raw/`, `.venv/`, API keys, caches).
5. Create the folder skeleton from `BRSR_Claim_Verification_v2.md` §13.9 (`data/raw`, `data/taxonomy`, `data/parsed`, `data/claims`, plus `src/`, `tests/`, `configs/`, `results/`, `paper/`).
6. Create `configs/config.yaml` with: metric set, tolerance defaults (±0.5 pp for %, ±1% relative for values), match-score weights, LLM model name (leave blank for now), random seed.
7. Set up secret handling: API key in an env var, never in the repo. Add a hard spend cap note.

**Produces:** working repo, pinned `requirements.txt`, folder skeleton, config file.
**Exit criterion:** `pytest` runs (0 tests, no import errors) and `arelle` imports cleanly.

---

## Phase 1 — Feasibility probe ⛔ (5 filings, mostly manual)
**Type:** 🔀 **Goal:** prove the project is real *before* investing in it. This is the single most important gate.

**Do exactly this:**
1. Manually download **5 filing pairs** from BSE (per v2 §13.4): pick 5 companies across different sectors (e.g. a manufacturer, an IT firm, a bank, a power/energy firm, an FMCG). For each: the Annual Report PDF + the BRSR XBRL `.xml`.
2. Download the BRSR **taxonomy** once (v2 §13.6).
3. **Manual claim hunt (the critical test):** in each PDF, read the BRSR + surrounding prose (Chairman/MD&A/ESG chapters) and by hand write down every *derived* quantitative claim you find about water/energy/Scope 1&2 — the "reduced by X%", "increased YoY", "down from A to B" statements. Tally them.
4. **Manual grounding test:** for ~10 of those claims, find the matching raw numbers in the XBRL (open in Arelle or even a text editor) and hand-recompute the relationship. Note any that *disagree* with the prose (a real inconsistency) or nearly do.
5. **Parse test:** confirm Arelle loads each instance + taxonomy and exposes water/energy/Scope 1&2 facts with unit + period + entity.

**Produces:** `results/feasibility_probe.md` — a table: per filing, #derived claims found, #groundable, #natural mismatches, parse success (Y/N), narrative source (BRSR body vs MD&A vs integrated report).

**⛔ Go/No-Go:**
- **GO** if: XBRL parses for ≥4/5; you find on average **≥3–5 derived claims per report**; ≥80% of sampled claims are groundable to an XBRL fact; and you find *at least a couple* of natural mismatches or near-misses across the 5.
- **RESHAPE** if derived claims are sparse: widen the narrative source (add MD&A/integrated report), or widen the metric set slightly, then re-probe. Do NOT proceed to build on a data source that has nothing to verify.
- **STOP** only if, after widening, derived claims genuinely don't exist in prose — then the task must be redefined (unlikely, but be honest).

---

## Phase 2 — Freeze the task definition
**Type:** 🖐 **Goal:** lock what you're labeling before you label anything. Prevents rework.

**Do exactly this:**
1. Write `configs/schema.md` fixing the claim tuple: `metric, operation, stated_result, unit, period_current, period_compare, boundary, source_span`.
2. Freeze `operation ∈ {value_equality, yoy_direction, absolute_change, percentage_change}` (value_equality only as a minority; derived ops are the focus).
3. Freeze the **label definitions** with 2–3 worked examples each:
   - **SUPPORTED** — recomputed relationship matches the prose within tolerance.
   - **INCONSISTENT** — recomputed relationship contradicts the prose beyond tolerance (include the canonical "100→78 ML but prose says 20%" example).
   - **INSUFFICIENT_EVIDENCE** — can't ground to a confident fact, or boundary/unit/period incompatible → abstain.
4. Freeze the **metric set** (recommend: water, energy, Scope 1, Scope 2 for v1).
5. Freeze the **tolerance policy** (from config; note it will be *calibrated on dev only*, never on test).

**Produces:** `configs/schema.md`, `configs/labels.md`, `configs/metrics.md`.
**Exit criterion:** all three docs written, with worked examples, and agreed by all annotators. Nothing downstream changes these without a version bump.

---

## Phase 3 — Data acquisition at scale (inventory)
**Type:** 🔀 **Goal:** collect 30–60 filing pairs with full provenance. (Parallel with P4–P6.)

**Do exactly this:**
1. Choose 30–60 company-years (mix sectors; include some with obvious prose claims from the probe).
2. Download each pair manually (BSE first, NSE for missing XBRL) per v2 §13. **Do not scrape** at this scale.
3. For every file write `source.json`: URL, retrieval date, SHA-256 checksum, exchange, scrip code/NSE symbol, format, parse-status.
4. Build `data/inventory.csv`: one row per company-year (company, symbol, FY, has_pdf, has_xbrl, sector, notes).

**Produces:** `data/raw/<symbol>_<FY>/` populated; `data/inventory.csv`.
**Exit criterion:** ≥30 complete pairs (PDF + XBRL both present, checksummed) with ≥80% parseable.

---

## Phase 4 — XBRL parsing + fact index + BRSR concept dictionary
**Type:** ⚙️ **Goal:** turn every XBRL instance into a clean fact table, and know what each tag means.

**Do exactly this:**
1. Write `src/xbrl_parse.py` using Arelle: load instance + taxonomy → iterate facts → emit `(company, fy, concept_qname, label, value, unit, decimals, period, entity, dimensions, source_file)`.
2. Export to `data/parsed/<symbol>_<FY>_facts.csv` (and a combined DuckDB table).
3. Build the **concept dictionary** `configs/concept_dictionary.csv`: map taxonomy concept labels + known textual aliases → your canonical metric names (e.g. `WaterConsumptionTotal`, `EnergyConsumptionTotal`, `Scope1Emissions`, `Scope2Emissions`). Fill it by reading the taxonomy + NSE sector guides.
4. **Manual validation:** for a sample spanning every metric, open the PDF and confirm the parsed fact value/unit/period matches the displayed filing. Log mismatches.
5. Leave unknown concepts *visible* (flag them) — never silently coerce.

**Produces:** fact tables, combined DuckDB, `concept_dictionary.csv`, `tests/test_xbrl_parse.py`.
**Exit criterion:** parsed facts match the PDF for the validation sample across all metrics; unit tests green.

---

## Phase 5 — Deterministic normalization + verification engine (BUILD THIS BEFORE THE LLM)
**Type:** ⚙️ **Goal:** the reproducible core — the calculator that will be your ground truth for the LLM later.

**Do exactly this:**
1. `src/normalize.py` using `decimal` + Pint: unit conversions (kL↔L, tonnes↔kg, GJ↔MJ), Indian scales (lakh/crore), comma stripping, parenthetical negatives, fiscal-year alias resolution, intensity denominators. Refuse to compare incompatible boundaries/denominators (return "incomparable").
2. `src/verify_engine.py`: given normalized `(P prior, C current)` and an operation, compute:
   - `yoy_direction = sign(C − P)`
   - `absolute_change = C − P`
   - `percentage_change = ((C − P)/|P|)×100` (guard `P ≠ 0`)
   - `value_equality = normalized_claim_value vs fact`
   Compare vs claim using **precision-derived tolerance**; return `SUPPORTED / INCONSISTENT` + a full arithmetic trace.
3. `tests/test_engine.py`: hand-write ~30 cases with known answers, including the 100→78=−22% case, rounding edges, zero-base, unit-mismatch, boundary-mismatch (→ abstain).

**Produces:** `normalize.py`, `verify_engine.py`, strong test suite, `results/engine_selftest.md`.
**Exit criterion:** **≥0.98 correctness on the hand-written cases** (target is really 100% on your own gold math — anything less is a bug). This number becomes the "calculation accuracy given gold facts" metric in the paper.

---

## Phase 6 — Annotation manual + pilot ⛔ (κ gate)
**Type:** 🖐 **Goal:** make labeling reproducible across people. (Can run parallel with P3–P5.)

**Do exactly this:**
1. Write `docs/annotation_manual.md` with examples for every tricky case: positive, negative, ambiguous, target/future ("we aim to..."), rounded, restated, intensity, consolidated-vs-standalone, missing-evidence.
2. Set up Label Studio or Doccano with the claim schema.
3. **Pilot:** all annotators independently label the **same 30–50 claims** drawn from Phase-1/3 filings.
4. Compute pairwise agreement (**Cohen's κ**) on the label; discuss disagreements; revise the manual; repeat if needed.

**Produces:** `annotation_manual.md`, labeling tool project, `results/pilot_kappa.md`.
**⛔ Go/No-Go:** decision-label **κ ≥ 0.80** → proceed. If κ < 0.80, the task definition is unstable: sharpen label boundaries in P2 and re-pilot **before** mass annotation. Do not annotate the full set on a shaky definition.

---

## Phase 7 — High-recall claim-candidate detection
**Type:** ⚙️ **Goal:** cheaply surface sentences that *might* be claims, so the LLM only sees candidates.

**Do exactly this:**
1. `src/ingest.py`: PDF→text with PyMuPDF/pdfplumber, preserving page, section, sentence offsets, table ids, headings (provenance is mandatory).
2. `src/candidate_filter.py`: keep sentences containing a number, %, comparison term, or direction word ("increased/reduced/remained/compared with/from…to"). Tune for **recall, not precision** — a compact classifier or spaCy rules to drop obvious non-claims (dates, definitions, future targets).

**Produces:** `ingest.py`, `candidate_filter.py`, per-filing candidate lists.
**Exit criterion:** on the pilot filings, the filter catches ≥95% of the manually-found derived claims (measure recall against your Phase-1 manual tally).

---

## Phase 8 — LLM structured claim extraction
**Type:** ⚙️ **Goal:** turn candidate sentences into the frozen claim schema. LLM does language only.

**Do exactly this:**
1. `src/extract_claims.py`: prompt the frozen LLM to convert each candidate → the claim tuple (P2 schema), as strict JSON (validate with Pydantic). **Prompt forbids arithmetic and verdicts** — extraction only.
2. Cache every LLM call by content hash (never pay twice).
3. Evaluate extraction against a small gold set (from pilot): field-level F1 + exact-record match.

**Produces:** `extract_claims.py`, frozen prompt in `configs/prompts/`, cached outputs, `results/extraction_eval.md`.
**Exit criterion:** field macro-F1 ≥ 0.85 on the gold extraction sample (else iterate the prompt on *dev only*).

---

## Phase 9 — Candidate fact retrieval + claim-to-fact grounding
**Type:** ⚙️ **Goal:** link each extracted claim to the right XBRL fact(s), or abstain.

**Do exactly this:**
1. `src/retrieve.py`: for a claim, fetch candidate facts by metric alias (concept dictionary) + embedding similarity (sentence-transformers) + period/unit/boundary compatibility.
2. `src/ground.py`: compute the weighted match score (`0.40·metric + 0.20·period + 0.15·unit + 0.15·boundary + 0.10·section`); pick best; **require best > threshold AND best − second_best > margin**, else `INSUFFICIENT_EVIDENCE`.
3. Tune threshold/margin/weights **on the dev split only**.
4. Evaluate top-1 grounding accuracy on gold-linked pilot claims.

**Produces:** `retrieve.py`, `ground.py`, `results/grounding_eval.md`.
**Exit criterion:** grounding top-1 ≥ 0.85 on eligible claims.

---

## Phase 10 — Integrate the end-to-end pipeline + abstention + evidence package
**Type:** ⚙️ **Goal:** one command runs filing → decisions with traces.

**Do exactly this:**
1. `src/pipeline.py`: ingest → candidate filter → LLM extract → ground → **(if grounded)** normalize → deterministic verify → confidence → decision.
2. Confidence combines grounding score + evidence completeness + distance beyond tolerance. Calibrate the abstention threshold on dev; plot risk–coverage.
3. `src/evidence.py`: emit the evidence package (narrative quote+page, XBRL concept/values/periods, normalization+arithmetic trace, label+confidence+reason). Explanations are **template-filled from the trace**; LLM may only reword against the trace.
4. Run end-to-end on a few held-out filings; eyeball every output for a correct trace.

**Produces:** `pipeline.py`, `evidence.py`, sample end-to-end outputs.
**Exit criterion:** pipeline runs start-to-finish on ≥10 filings, every non-abstained decision carries a complete, correct evidence trace.

---

## Phase 11 — Build the full BRSR-Claim dataset + splits
**Type:** 🖐⚙️ **Goal:** the labeled corpus that is your headline contribution.

**Do exactly this:**
1. Run the candidate filter across all filings; **humans confirm** eligible claims and link to facts (never use model output as gold).
2. **Double-annotate** every dev/test item (two independent annotators); **third adjudicates blind** to any system prediction. Record κ + adjudication notes.
3. **Controlled perturbations:** from human-confirmed SUPPORTED claims only, make one minimal edit each (reverse direction, alter %, swap base year, change magnitude/unit); a human verifies each mutation is grammatical, unambiguous, and truly inconsistent. Store `synthetic=true`, mutation type, source id.
4. **Split by company** (no company in >1 split); check near-duplicate boilerplate across splits.
5. Freeze `data/splits/{train,dev,test}.jsonl`. Report natural inconsistency prevalence honestly; keep natural and synthetic subsets separate.

**Produces:** `data/claims/*.jsonl` (full BRSR-Claim), frozen splits, `results/dataset_stats.md` (counts, κ, natural-vs-synthetic, prevalence).
**Exit criterion:** ~150–300 eligible claims, ≥~100 natural double-annotated, κ ≥ 0.80, splits frozen and leakage-checked.

---

## Phase 12 — Baselines
**Type:** ⚙️ **Goal:** the comparison points that make your numbers meaningful.

**Do exactly this — implement all of:**
1. Majority / always-SUPPORTED.
2. Keyword + nearest-number arithmetic (no semantic mapping, no LLM).
3. Naive LLM prompt (passage + filing content, "do they contradict?").
4. Retrieval + LLM (LLM grounds *and* does math).
5. Long-context LLM verifier (FinDVer-style, forced choice).
6. Neuro-symbolic ablation (AuditFlow-style: LLM grounds, engine computes, **no** abstention).
7. VeriBRSR (the full proposed system).

**Produces:** `src/baselines/`, one runnable entry point per baseline.
**Exit criterion:** all seven run on dev and emit comparable predictions + logged cost/version/prompt.

---

## Phase 13 — Freeze, final evaluation, ablations, statistics ⛔
**Type:** ⚙️ **Goal:** the locked results that go in the paper. Touch test **once**.

**Do exactly this:**
1. Freeze everything: model versions, prompts, temperature, thresholds, normalization tables. Commit a tag.
2. Run all systems on the **test** split — one time.
3. Compute the full metric suite (v2 §8): INCONSISTENT precision/recall/F1, FPR on supported-natural, 3-class macro-F1, extraction F1, grounding top-1, evidence completeness, calc accuracy, abstention coverage, selective risk (risk–coverage curve), calibration (ECE/Brier), latency/cost. Report natural vs synthetic separately.
4. **Ablations** (remove one at a time): deterministic calc, unit normalization, period filter, boundary filter, abstention.
5. **Statistics:** paired bootstrap CIs over claims; McNemar's on end-to-end decision errors vs naive prompting; report effect sizes + CIs, not just p-values.

**Produces:** `results/final_tables/`, all figures, `results/ablations.md`.
**⛔ Go/No-Go (success definition):** VeriBRSR reaches **INCONSISTENT precision ≥0.85 combined, ≥0.80 natural**, **F1 ≥0.80 with a statistically supported win over naive prompting**, FPR ≤10%, without hiding errors behind excessive abstention (coverage ≥0.70). If precision misses, do **not** re-tune on test — diagnose on dev, refreeze, rerun. If the win over naive prompting isn't statistically supported, that itself is a (weaker but honest) result — report it; likely the abstention/normalization ablations still tell a publishable story.

---

## Phase 14 — Error analysis
**Type:** 🖐⚙️ **Goal:** the qualitative substance reviewers expect.

**Do exactly this:**
1. Categorize every error: extraction, taxonomy-mapping, period, unit, boundary, arithmetic/tolerance, parsing, unsupported-claim-type.
2. Use **dev** errors for improvement ideas; inspect **test** errors only after the final run (never to re-tune).
3. Pull 3–5 illustrative cases (with traces) for the paper.

**Produces:** `results/error_analysis.md`, case studies.
**Exit criterion:** every error class quantified; representative examples selected.

---

## Phase 15 — ✅ PAPER-READY checkpoint
**You are ready to write the full paper when ALL of these exist:**
- [ ] BRSR-Claim frozen with κ ≥ 0.80 and honest prevalence reported (P11)
- [ ] Deterministic engine ≥0.98 on gold math (P5)
- [ ] End-to-end pipeline with evidence traces (P10)
- [ ] All baselines run (P12)
- [ ] Final locked test results + ablations + stats (P13)
- [ ] Error analysis + case studies (P14)

**Then the paper maps 1:1 to what you built:**
| Paper section | Comes from |
|---|---|
| Introduction + contributions | v2 §0, §9 |
| Related work + differentiation | v2 §2, §5 (must cite **FinDVer**) |
| Task formalization | v2 §1.3 |
| Dataset (BRSR-Claim) | P11 + `dataset_stats.md` |
| Method / architecture | v2 §4 + P5–P10 |
| Experiments (baselines, metrics) | P12, P13 |
| Results + ablations + stats | P13 `final_tables/` |
| Error analysis | P14 |
| Limitations & ethics (reviewer-assist, not fraud; circularity caveat) | v2 §1.4, §6 |

---

## Phase 16 — Reproducibility bundle + demo
**Type:** ⚙️ **Goal:** what makes reviewers trust it and what you show at the conference.

**Do exactly this:**
1. Package: annotation manual, schemas, split lists, evaluation scripts, frozen prompts, model config, cached permitted outputs. If the LLM can't be redistributed, include fixed prompts + an open-model/mocked path so the rest of the pipeline is verifiable on a 16 GB machine.
2. Minimal FastAPI + Streamlit demo: select a filing → show evidence cards (the UI is *not* a contribution — keep it minimal).
3. Ethics statement: flags require human review; a mismatch is not misconduct.

**Produces:** `repro/` bundle, demo app, README with exact run commands.
**Exit criterion:** a fresh clone runs parsing → normalization → baseline inference → metric calculation on a normal machine.

---

## When exactly are we ready to write the paper (short version)
- **Start drafting at P2:** Introduction, Related Work, Task Formalization, Method — these depend only on the design, not results. Do them in parallel with building.
- **Dataset section:** fill after P11.
- **Results/Ablations/Error analysis:** only after P13–P14 (never write numbers before the locked run).
- **Submit-ready:** at P15 all boxes checked. **You do NOT need a polished prototype** — a functional pipeline (P10) + dataset (P11) + locked results (P13) is a complete paper. The demo (P16) is for the conference, not for acceptance.

## The three ways this fails (all already avoided in the design)
1. Building raw value-equality matching instead of **derived-claim** verification → trivial, unpublishable. (Prime directive.)
2. Claiming fraud/greenwashing → indefensible. (Stay reviewer-assist.)
3. Not citing/differentiating **FinDVer** → instant reviewer objection. (v2 §5 handles it.)

## What can be modified freely during implementation (and what cannot)
**Freely:** metric set size, corpus size (30→60→more), match-score weights, tolerances (on dev), LLM choice, prompt wording, UI.
**Never:** engine-before-LLM order; freeze-definitions-before-annotation; split-by-company; touch-test-only-once; LLM-never-does-final-math; keep natural and synthetic subsets separate.
