"""Small correctness checks for research-critical arithmetic and abstention."""
import json
import tempfile
import unittest
import csv
import hashlib
from unittest.mock import patch, Mock
from pathlib import Path

from experiments.evaluate import compute_metrics, evaluate
from src.baselines import keyword_interpret
from src.extract_claims import page_numbers, validate_claim
from src.units import convert, number
from src.perturbations import mutations
from src.verifier import verify
from src.xbrl_parser import parse_xbrl, store_facts, load_facts
from src.dataset import require_complete_dataset, require_reference_reviews
from experiments.run import run
from src.batch_llm import verdict_batch
from src.llm import load_config


def fact(identifier, value, period, concept="TotalVolumeOfWaterConsumption", unit="kL", **extra):
    return {"fact_id": identifier, "filing_id": "f", "company": "Company", "concept": concept,
            "concept_qname": "{taxonomy}" + concept, "value": str(value), "unit": unit,
            "period_start": f"{period}-04-01", "period_end": f"{period+1}-03-31", "period_type": "duration",
            "boundary": "consolidated", "dimensions_json": "{}", **extra}


def claim(**changes):
    return {"claim_id": "c", "filing_id": "f", "company": "Company", "metric": "total_water_consumption",
            "operation": "percentage_change", "asserted_value": -10, "unit": "%", "current_period": "2023-24",
            "previous_period": "2022-23", "boundary": "consolidated", "source_sentence": "Water decreased by 10%.",
            **changes}


class ResearchTests(unittest.TestCase):
    def test_baseline_format_retry_uses_fresh_validated_model_response(self):
        c = claim(gold_label="INCONSISTENT", annotation_notes="HIDDEN REFERENCE NOTES")
        invalid = [{"claim_id": "c", "verdict": "ABSTAIN", "matched_fact_ids": []}]
        valid = [{"claim_id": "c", "verdict": "INSUFFICIENT_EVIDENCE", "matched_fact_ids": [],
                  "abstention_reason": "MISSING_OPERAND"}]
        client = Mock()
        client.generate.side_effect = [(invalid, {"run_id": "invalid"}), (valid, {"run_id": "repaired"})]
        traces = verdict_batch("llm_only", [c], {"c": (c, {})}, {"f": [fact("cur", 90, 2023)]}, load_config(), client)
        self.assertEqual(traces["c"]["llm_run"]["run_id"], "repaired")
        self.assertEqual(traces["c"]["response_format_retry"]["rejected_run"]["run_id"], "invalid")
        self.assertEqual(client.generate.call_count, 2)
        self.assertNotIn("HIDDEN REFERENCE NOTES", client.generate.call_args.args[0])
        self.assertNotIn('"gold_label"', client.generate.call_args.args[0])

    def test_baseline_second_invalid_response_stops_without_label_mapping(self):
        c = claim()
        invalid = [{"claim_id": "c", "verdict": "ABSTAIN", "matched_fact_ids": []}]
        client = Mock()
        client.generate.side_effect = [(invalid, {}), (invalid, {})]
        with self.assertRaisesRegex(ValueError, "Invalid baseline ID/verdict"):
            verdict_batch("llm_only", [c], {"c": (c, {})}, {"f": []}, load_config(), client)
        self.assertEqual(client.generate.call_count, 2)

    def test_evaluation_rejects_changed_prediction_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "predictions.csv"
            output.write_text("split,claim_id\ntest,c\n", encoding="utf-8")
            Path(str(output) + ".run.json").write_text(json.dumps({
                "split": "test", "dataset_sha256": "dataset", "implementation_sha256": "code",
                "predictions_sha256": "old CSV hash"}), encoding="utf-8")
            with patch("experiments.evaluate.examples", return_value=[claim()]), \
                    patch("experiments.evaluate.require_reference_reviews"), \
                    patch("experiments.evaluate.dataset_fingerprint", return_value="dataset"), \
                    patch("experiments.run.implementation_fingerprint", return_value="code"):
                with self.assertRaisesRegex(ValueError, "provenance does not match"):
                    evaluate(output, {}, require_complete=False)

    def test_reference_review_rejects_changed_source_document(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "report.pdf").write_bytes(b"original PDF")
            (root / "filing.xml").write_bytes(b"original XML")
            c = claim(gold_label="SUPPORTED", gold_xbrl_fact_ids=["cur"], page=1)
            record = {"claim_id": "c", "reference_label": "SUPPORTED", "annotation_mode": "automated_source_reference",
                      "source_sha256": hashlib.sha256(b"original PDF").hexdigest(),
                      "xml_sha256": hashlib.sha256(b"original XML").hexdigest(),
                      "source_sentence": c["source_sentence"], "pdf_page": 1, "evidence": [{"fact_id": "cur"}]}
            manifest = [{"filing_id": "f", "pdf_path_or_url": "report.pdf", "xbrl_path_or_url": "filing.xml"}]
            with patch("src.dataset.ROOT", root), patch("src.dataset.filings", return_value=manifest), \
                    patch("src.dataset.read_json", return_value=[record]):
                config = {"data": {"reference_reviews": "reviews.json"}}
                require_reference_reviews([c], config)
                (root / "report.pdf").write_bytes(b"changed PDF")
                with self.assertRaisesRegex(ValueError, "Source documents changed"):
                    require_reference_reviews([c], config)

    def test_batch_failure_preserves_finished_rows_without_replacing_results(self):
        records = [claim(claim_id=f"c{i}", split="development", natural_or_modified="natural") for i in range(5)]
        filing = {"filing_id": "f", "company": "Company", "split": "development"}
        sizes = []

        def verdicts(system, chunk, *args):
            sizes.append(len(chunk))
            if len(sizes) == 2:
                raise RuntimeError("Provider failed")
            return {c["claim_id"]: {"verdict": "SUPPORTED", "matched_fact_ids": [], "abstention_reason": None}
                    for c in chunk}

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "predictions.csv"
            output.write_text("previous complete results", encoding="utf-8")
            with patch("experiments.run.filings", return_value=[filing]), \
                    patch("experiments.run.examples", return_value=records), \
                    patch("experiments.run.load_facts", return_value=[]), \
                    patch("experiments.run.interpret_statement", side_effect=lambda c, *a: (c, {})), \
                    patch("experiments.run.verdict_batch", side_effect=verdicts):
                with self.assertRaisesRegex(RuntimeError, "Provider failed"):
                    run({"data": {"facts_db": "unused"}, "llm": {}}, split="development", systems=["llm_only"],
                        output=output, batch=True, batch_size=2)
            self.assertEqual(sizes, [2, 2])
            self.assertEqual(output.read_text(encoding="utf-8"), "previous complete results")
            with Path(str(output) + ".partial.csv").open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual([r["claim_id"] for r in rows], ["c0", "c1"])

    def test_complete_dataset_rejects_missing_test_filings(self):
        manifest = [{"filing_id": f"f{i}"} for i in range(10)]
        records = [{"filing_id": f"f{i}", "natural_or_modified": "natural"} for i in range(7) for _ in range(6)]
        with patch("src.dataset.filings", return_value=manifest):
            with self.assertRaisesRegex(ValueError, "each of the ten filings"):
                require_complete_dataset(records, {"scope": {"perturbations_target": 40}})

    def test_numbers_and_bidirectional_conversions(self):
        self.assertEqual(number("1,36,592"), 136592)
        self.assertEqual(convert(1, "MWh", "GJ"), number("3.6"))
        self.assertEqual(convert(1000, "kgCO2e", "tCO2e"), 1)
        self.assertEqual(convert(1, "kL", "L"), 1000)
        with self.assertRaises(ValueError):
            convert(1, "MtCO2e", "tCO2e")

    def test_preserves_direction(self):
        facts = [fact("cur", 90, 2023), fact("prev", 100, 2022)]
        self.assertEqual(verify(claim(), facts)["verdict"], "SUPPORTED")
        self.assertEqual(verify(claim(asserted_value=10), facts)["verdict"], "INCONSISTENT")
        self.assertEqual(verify(claim(operation="direction_of_change", asserted_value=-1), facts)["verdict"], "SUPPORTED")
        self.assertEqual(verify(claim(operation="absolute_change", unit="kL", asserted_value=-10), facts)["verdict"], "SUPPORTED")

    def test_relative_tolerance_uses_calculated_denominator(self):
        facts = [fact("cur", 100, 2023)]
        self.assertEqual(verify(claim(operation="value_equality", unit="kL", asserted_value=101), facts)["verdict"], "SUPPORTED")
        self.assertEqual(verify(claim(operation="value_equality", unit="kL", asserted_value=number("101.01")), facts)["verdict"], "INCONSISTENT")
        # No arbitrary +/-0.5 allowance for small scalar quantities.
        self.assertEqual(verify(claim(operation="value_equality", unit="kL", asserted_value=number("0.4")), [fact("cur", "0.1", 2023)])["verdict"], "INCONSISTENT")

    def test_percentage_tolerance_and_zero_denominator(self):
        facts = [fact("cur", 90, 2023), fact("prev", 100, 2022)]
        self.assertEqual(verify(claim(asserted_value="-10.5"), facts)["verdict"], "SUPPORTED")
        self.assertEqual(verify(claim(asserted_value="-10.51"), facts)["verdict"], "INCONSISTENT")
        self.assertEqual(verify(claim(), [fact("cur", 90, 2023), fact("prev", 0, 2022)])["abstention_reason"], "ZERO_DENOMINATOR")

    def test_both_period_units_are_normalized(self):
        facts = [fact("cur", 90, 2023), fact("prev", 100000, 2022, unit="L")]
        self.assertEqual(verify(claim(), facts)["verdict"], "SUPPORTED")

    def test_ambiguity_and_boundary_abstain(self):
        facts = [fact("cur", 90, 2023), fact("duplicate", 95, 2023), fact("prev", 100, 2022)]
        self.assertEqual(verify(claim(), facts)["abstention_reason"], "MULTIPLE_PLAUSIBLE_FACTS")
        self.assertEqual(verify(claim(boundary=None), facts)["abstention_reason"], "BOUNDARY_AMBIGUOUS")
        self.assertEqual(verify(claim(previous_period=None), facts)["abstention_reason"], "MISSING_PERIOD")

    def test_dimensions_and_workforce_exactness(self):
        facts = [fact("cur", 100, 2023, concept="NumberOfEmployeesOrWorkersIncludingDifferentlyAbled", unit="count")]
        c = claim(metric="total_employees", operation="value_equality", asserted_value=101, unit="count")
        self.assertEqual(verify(c, facts)["verdict"], "INCONSISTENT")
        facts[0]["dimensions_json"] = json.dumps({"GenderAxis": "FemaleMember"})
        self.assertEqual(verify(c, facts)["verdict"], "INSUFFICIENT_EVIDENCE")

    def test_components_and_overlapping_periods_cannot_verify_a_total(self):
        facts = [fact("cur", 90, 2023, concept="TotalEnergyConsumedFromRenewableSources"), fact("prev",100,2022)]
        c = claim(metric="total_energy_consumption", unit="GJ", operation="value_equality", asserted_value=90)
        self.assertEqual(verify(c, facts)["verdict"], "INSUFFICIENT_EVIDENCE")
        same_period = claim(previous_period="FY 2023-24")
        self.assertEqual(verify(same_period, [fact("cur",90,2023)])["abstention_reason"], "MISSING_PERIOD")

    def test_missing_unknown_units_and_period_not_guessed(self):
        c = claim(operation="value_equality", unit="kL", asserted_value=90)
        self.assertEqual(verify(c, [fact("cur", 90, 2023, unit=None)])["abstention_reason"], "UNIT_INCOMPATIBLE")
        self.assertEqual(verify({**c, "current_period": "2024"}, [fact("cur", 90, 2023)])["verdict"], "INSUFFICIENT_EVIDENCE")

    def test_page_ranges(self):
        self.assertEqual(page_numbers("2,4-6", 6), [2, 4, 5, 6])
        for spec in ["0", "4-2", "7", "all", None]:
            with self.assertRaises(ValueError):
                page_numbers(spec, 6)

    def test_extraction_rejects_noncontiguous_and_calculated_sources(self):
        filing = {"filing_id": "f", "company": "Company", "reporting_year": "2023-24"}
        record = {**claim(operation="value_equality", unit="L", asserted_value=1000),
                  "reporting_year": "2023-24", "page_number": 1, "extraction_confidence": 0.9,
                  "is_target": False, "source_sentence": "Water consumption 1,000 L"}
        text = "Water consumption 1,000 L"
        self.assertEqual(validate_claim(record, filing, 1, text)["asserted_value"], 1000)
        with self.assertRaises(ValueError):
            validate_claim({**record, "source_sentence": "Water ... 1,000 L"}, filing, 1, text)
        with self.assertRaises(ValueError):
            validate_claim({**record, "asserted_value": 1000000}, filing, 1, text)

    def test_rule_baseline_does_not_use_gold_fields(self):
        source = claim(source_sentence="Consolidated water consumption decreased by 10% in FY 2023-24 vs FY 2022-23.", gold_label="INCONSISTENT")
        result = keyword_interpret(source, {"company": "Company", "filing_id": "f"})
        self.assertEqual(result["asserted_value"], "-10.0")
        self.assertEqual(result["previous_period"], "2022-23")
        self.assertNotIn("gold_label", result)

    def test_mutations_change_real_sentence_spans_and_preserve_alignment(self):
        c = claim(source_sentence="Water consumption decreased by 10% in 2023-24 compared with 2022-23.",
                  previous_period={"start":"2022-04-01", "end":"2023-03-31", "type":"duration"})
        changed = {kind:(text,fields) for kind,text,fields in mutations(c)}
        self.assertIn("increased by 10%", changed["direction_reversal"][0])
        self.assertEqual(number(changed["direction_reversal"][1]["asserted_value"]),10)
        self.assertEqual(changed["base_year_alteration"][1]["previous_period"]["end"],"2022-03-31")
        self.assertIn("2021-22", changed["base_year_alteration"][0])
        u=claim(operation="value_equality",asserted_value=100,unit="kilolitres",source_sentence="Water consumption was 100 kilolitres.")
        altered={kind:(text,fields) for kind,text,fields in mutations(u)}
        self.assertIn("100 L",altered["unit_alteration"][0])
        self.assertEqual(altered["unit_alteration"][1]["unit"],"L")

    def test_real_metrics_and_empty_dataset(self):
        rows = [{"claim_id": str(i), "gold_label": g, "predicted_label": p, "matched_fact_ids": "[]"}
                for i, (g,p) in enumerate([("INCONSISTENT","INCONSISTENT"), ("SUPPORTED","INCONSISTENT"),
                                          ("SUPPORTED","SUPPORTED"), ("INSUFFICIENT_EVIDENCE","INSUFFICIENT_EVIDENCE")])]
        m = compute_metrics(rows)
        self.assertEqual(m["precision_inconsistent"], 0.5)
        self.assertEqual(m["recall_inconsistent"], 1)
        self.assertEqual(m["coverage"], 0.75)
        self.assertAlmostEqual(m["false_positive_rate"], 1/3)
        self.assertIsNone(compute_metrics([])["metrics"])

    def test_parser_resolves_measures_and_is_idempotent(self):
        xml = '''<x:xbrl xmlns:x="http://www.xbrl.org/2003/instance" xmlns:t="urn:t">
        <x:context id="a"><x:entity><x:identifier scheme="test">C</x:identifier></x:entity>
        <x:period><x:startDate>2023-04-01</x:startDate><x:endDate>2024-03-31</x:endDate></x:period></x:context>
        <x:unit id="misleading_name"><x:measure>t:kl</x:measure></x:unit>
        <t:TotalVolumeOfWaterConsumption contextRef="a" unitRef="misleading_name" decimals="0">1,36,592</t:TotalVolumeOfWaterConsumption>
        <t:UnknownNumber contextRef="a" decimals="0">42</t:UnknownNumber></x:xbrl>'''
        with tempfile.TemporaryDirectory() as directory:
            path, db = Path(directory)/"f.xml", Path(directory)/"f.sqlite"
            path.write_text(xml)
            facts = parse_xbrl(path, "Company", "2023-24", "f")
            self.assertEqual(facts[0]["unit"], "kL")
            self.assertEqual(facts[0]["normalized_value"], "136592000")
            self.assertIsNone(facts[1]["unit"])
            store_facts(facts, db)
            store_facts(facts, db)
            self.assertEqual(len(load_facts(db,"f")), 2)


if __name__ == "__main__":
    unittest.main()
