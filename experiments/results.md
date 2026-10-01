# VeriBRSR automatic-reference pilot results

These scores measure agreement with automatic exact-concept XBRL references. They are not independent human-ground-truth accuracy. Shared extraction interpretations, parsing, unit conversion and arithmetic limit the independence of this comparison.

Generated from [metrics.json](metrics.json) and [predictions.csv](predictions.csv), recorded at 2026-10-01T03:45:58.661893+00:00.

The dataset contains ten real company-year PDF/XBRL pairs, 54 exact PDF table claims and 40 sentence mutations. Seven companies supply 66 development examples; TCS, Wipro and ITC supply 28 test examples (16 natural, 12 modified). Four systems produce 264 development and 112 test rows. The test references contain 10 SUPPORTED, 12 INCONSISTENT and 6 INSUFFICIENT_EVIDENCE labels.

Configured model: `gemini-3.5-flash-lite`. Each prediction has a full trace and run provenance; batched requests use six claims or fewer. All 21 offline correctness tests pass.

## Test-split agreement

P, R and F1 concern INCONSISTENT. Macro F1 always includes all three classes. FPR counts reference non-INCONSISTENT examples predicted INCONSISTENT. Coverage is the fraction receiving a non-abstained prediction. All cells below are computed from saved predictions.

| Group | System | N | P | R | F1 | Macro F1 | FPR | Coverage | Evidence-ID agreement |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| natural | Keyword + calculator | 16 | 0.000 | 0.000 | 0.000 | 0.182 | 0.000 | 0.000 | 0.000 |
| natural | LLM only | 16 | 0.000 | 0.000 | 0.000 | 0.345 | 0.062 | 0.938 | 1.000 |
| natural | Retrieval + LLM | 16 | 0.000 | 0.000 | 0.000 | 0.327 | 0.125 | 0.938 | 1.000 |
| natural | VeriBRSR | 16 | 0.000 | 0.000 | 0.000 | 0.667 | 0.000 | 0.625 | 1.000 |
| modified | Keyword + calculator | 12 | 0.000 | 0.000 | 0.000 | 0.000 | undefined | 0.000 | 0.000 |
| modified | LLM only | 12 | 1.000 | 1.000 | 1.000 | 0.333 | undefined | 1.000 | 1.000 |
| modified | Retrieval + LLM | 12 | 1.000 | 0.750 | 0.857 | 0.286 | undefined | 0.750 | 0.833 |
| modified | VeriBRSR | 12 | 1.000 | 0.833 | 0.909 | 0.303 | undefined | 0.833 | 0.833 |
| combined | Keyword + calculator | 28 | 0.000 | 0.000 | 0.000 | 0.118 | 0.000 | 0.000 | 0.000 |
| combined | LLM only | 28 | 0.923 | 1.000 | 0.960 | 0.665 | 0.062 | 0.964 | 1.000 |
| combined | Retrieval + LLM | 28 | 0.818 | 0.750 | 0.783 | 0.559 | 0.125 | 0.857 | 0.909 |
| combined | VeriBRSR | 28 | 1.000 | 0.833 | 0.909 | 0.922 | 0.000 | 0.714 | 0.909 |

Evidence-ID agreement is exact set equality only where automatic reference fact IDs exist (10 natural, 12 modified, 22 combined). Two empty sets receive no credit. Modified examples contain no reference negatives, so their FPR is undefined. Natural examples contain no INCONSISTENT references; their inconsistency P/R/F1 is zero by the fixed zero-division convention.

## Observed behavior

VeriBRSR agrees with all 16 natural reference labels. It detects 10 of 12 inconsistent mutations and abstains on the other two with UNIT_INCOMPATIBLE. Those cases are `tcs-2023-24-p0025-001-mod-magnitude_alteration` and `tcs-2023-24-p0025-002-mod-magnitude_alteration`. Their model interpretation and unit traces are retained. No post-result unit or matching-rule adjustment was made.

The keyword baseline abstains on every test example, so its zero FPR accompanies zero coverage. Both LLM baselines mark five reference-insufficient Wipro claims SUPPORTED. This dataset exposes the limits of raw table rules and model boundary handling, but its size and automatic references cannot establish general performance.

## Protocol history and limits

The first frozen test attempt revealed six examples before a baseline returned the invalid label ABSTAIN. An unchanged-input retry also failed. A generic, single format-repair request was then added and tested; development was rerun and the revised code was frozen. Final test traces record the rejected response and the newly generated, validated response. The original freeze and partial rows are preserved. See [protocol_notes.json](protocol_notes.json). This is a company-separated pilot with disclosed test exposure, not an untouched confirmatory benchmark.

All 54 natural examples are value-equality table claims. Mutations consist of 30 magnitude changes and 10 unit changes. The implementation has offline arithmetic tests for percentage, direction and base-year behavior, but this corpus provides no empirical evaluation of those claim types.

No independent annotators or agreement scores exist. Automatic references inherit extracted claim semantics: a wrong extracted boundary can lead to a reference abstention even when the source report is clear. Genuine human review of PDF headings, boundaries and XML contexts is needed before reporting independently established accuracy.

Per-example LLM batch runtime is unmeasured. Batch API wall time, cache status and provider responses are preserved, so these runs should not be presented as an uncached speed comparison.

## Reproduce saved metrics

```powershell
py -3.13 -m src.cli validate --complete
py -3.13 -m experiments.evaluate
py -3.13 -m src.cli status
```

Dataset SHA-256: `26972b4ab5fcc6321a88c2171f9f6abd38d341f9a60bab21e9166bd23d392396`.
Implementation SHA-256: `ce4ea2c91a269a70d318850e0ac4835a528263f90c4bcdd56effa50c6b72d62e`.
Predictions SHA-256: `5723f6451ee2ad442d8efc7afc448a7b2efadb0fd177905ecaf380fca2562f9f`.
