# Independent annotation guide

Use two different project members for every final test example, including
perturbations. Work independently before discussion. Do not read system verdicts.
The blind annotation pack contains original PDF locations and the full filing's
numeric facts, not just the system's selected candidate. Check the original XML
when the parser's representation is uncertain.

1. Locate the exact sentence/table passage on the 1-based PDF page. Check table
   headers, fiscal years, units, boundary notes, employee categories and footnotes.
   A table row is a genuine value claim; do not invent a percentage-change claim
   from two table values. Record the narrative/prose or table provenance.
2. Independently identify matching XBRL concepts, contexts and dimensions from
   the same company-year instance. Record the stable fact IDs. Never treat water
   withdrawal as consumption, an intensity as a total, or employees as workers.
   Never sum category facts without a predefined, independently checked rule.
3. Copy asserted magnitudes; decreases are negative and increases positive.
   Direction-only assertions use -1, 1, 0. Missing operands/years/units stay null.
   An explicit full-year workforce count may be an instant fact: use its actual
   date, not an assumed duration period. Retain XBRL unit measures; a `pure` unit
   is not automatically a physical unit. `MtCO2e` needs documented clarification.
4. Calculate independently: current minus previous; percentage =
   (current - previous) / previous * 100. A zero prior value cannot support a
   percentage claim. Compare signed results, not their magnitudes.
5. Label SUPPORTED for an agreement within 0.5 percentage points for percentages
   or `abs(calculated-claimed)/max(abs(calculated),1e-12) <= 0.01` for values and
   absolute changes. Counts are exact unless explicit source rounding is noted.
   Label INCONSISTENT only when compatible evidence actually contradicts the
   statement. Otherwise use INSUFFICIENT_EVIDENCE and explain what is uncertain.
6. Write claim_id, your real annotator name/identifier, label, the JSON array of
   fact IDs and notes in your own member_a.csv/member_b.csv. Resolve differences
   through discussion in adjudications.csv with the final label and discussion
   notes. Independently checked numerical evidence, not system predictions,
   determines the final natural_claims.json/perturbations.json gold_label.

Natural records use: claim_id, filing_id, company, page, source_sentence, metric,
operation, asserted_value, unit, current_period, previous_period, boundary,
gold_label, gold_xbrl_fact_ids, annotation_notes. Also retain reporting_year,
is_target, extraction_confidence, dimensions and pdf_context when available.
Keep extraction run IDs so model interpretation can be audited separately from
your manual labels. `pdf_context` must be copied from the PDF, not from XBRL.

Modified records also need perturbation_id, original_claim_id, mutation_type,
original_sentence, modified_sentence and split. Keep changed interpretation
fields, and independently check the expected verdict: a wrong base year often
lacks evidence and a unit mutation may be incompatible rather than inconsistent.
Do not copy the parent's gold evidence IDs to a changed base-year claim.

The generator writes only drafts with null gold labels and a proposed machine
verdict for later review. Have annotators review blind packs without this proposal.
Use `python -m src.cli kappa` only after genuine independent records exist. It
calculates agreement over paired pre-discussion test labels, returning null when
kappa's denominator is zero. Never manually invent an agreement score.
