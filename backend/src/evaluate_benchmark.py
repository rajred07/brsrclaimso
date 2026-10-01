"""
VeriBRSR: Benchmark Evaluation & Paper Table Generator
======================================================
Reproduces Table II (Aggregate Performance) and Table III (Ablations)
for the research paper:
"VeriBRSR: Verifying Quantitative Sustainability Claims against XBRL Disclosures"
Authors: Ganesh Gupta, Jatin Gupta, Raj Joshi, Dimple Maurya (TCET Mumbai)
"""

import json
import os
import random
import copy
from typing import List, Dict, Tuple
from dataclasses import dataclass

# ============================================================
# EVALUATION METRICS CALCULATOR
# ============================================================

@dataclass
class EvaluationMetrics:
    precision_inconsistent: float  # P_I
    recall_inconsistent: float     # R_I
    f1_inconsistent: float         # F1,I
    fpr_supported: float           # FPR_S (False alarms on naturally supported claims)
    macro_f1: float                # Macro-F1 across all 3 classes
    coverage: float                # % of claims where system made a definitive decision

def compute_metrics(gold_labels: List[str], pred_labels: List[str]) -> EvaluationMetrics:
    """
    Computes exact metrics defined in Section IV-B and Equations (5) of paper.
    Labels: 'SUPPORTED', 'INCONSISTENT', 'INSUFFICIENT_EVIDENCE'
    """
    assert len(gold_labels) == len(pred_labels)
    total = len(gold_labels)
    
    # Inconsistent class confusion matrix
    tp_i = sum(1 for g, p in zip(gold_labels, pred_labels) if g == 'INCONSISTENT' and p == 'INCONSISTENT')
    fp_i = sum(1 for g, p in zip(gold_labels, pred_labels) if g != 'INCONSISTENT' and p == 'INCONSISTENT')
    fn_i = sum(1 for g, p in zip(gold_labels, pred_labels) if g == 'INCONSISTENT' and p != 'INCONSISTENT')
    
    p_i = tp_i / (tp_i + fp_i) if (tp_i + fp_i) > 0 else 0.0
    r_i = tp_i / (tp_i + fn_i) if (tp_i + fn_i) > 0 else 0.0
    f1_i = (2 * p_i * r_i) / (p_i + r_i) if (p_i + r_i) > 0 else 0.0
    
    # FPR_S: Denominator is gold naturally SUPPORTED claims; numerator is those marked INCONSISTENT
    gold_supported = [p for g, p in zip(gold_labels, pred_labels) if g == 'SUPPORTED']
    fp_s = sum(1 for p in gold_supported if p == 'INCONSISTENT')
    fpr_s = fp_s / len(gold_supported) if len(gold_supported) > 0 else 0.0
    
    # Macro-F1 calculation across all three classes
    f1_per_class = []
    for cls in ['SUPPORTED', 'INCONSISTENT', 'INSUFFICIENT_EVIDENCE']:
        tp = sum(1 for g, p in zip(gold_labels, pred_labels) if g == cls and p == cls)
        fp = sum(1 for g, p in zip(gold_labels, pred_labels) if g != cls and p == cls)
        fn = sum(1 for g, p in zip(gold_labels, pred_labels) if g == cls and p != cls)
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
        f1_per_class.append(f1)
        
    macro_f1 = sum(f1_per_class) / len(f1_per_class)
    
    # Coverage: Fraction not marked INSUFFICIENT_EVIDENCE
    definitive = sum(1 for p in pred_labels if p in ['SUPPORTED', 'INCONSISTENT'])
    coverage = definitive / total if total > 0 else 0.0
    
    return EvaluationMetrics(
        precision_inconsistent=round(p_i, 2),
        recall_inconsistent=round(r_i, 2),
        f1_inconsistent=round(f1_i, 2),
        fpr_supported=round(fpr_s, 2),
        macro_f1=round(macro_f1, 2),
        coverage=round(coverage, 2)
    )

# ============================================================
# SYNTHETIC PERTURBATION GENERATOR (Section IV-A)
# ============================================================

def generate_controlled_modifications(supported_claims: List[Dict]) -> List[Dict]:
    """
    Generates the 165 controlled perturbations described in Section IV-A:
    - 38 direction reversals
    - 45 percentage alterations
    - 31 base-year substitutions
    - 29 magnitude changes
    - 22 unit changes
    """
    perturbations = []
    
    # 1. Direction Reversal (38)
    for c in supported_claims[:38]:
        p = copy.deepcopy(c)
        p['claim_id'] = f"{c['claim_id']}-MOD-DIR"
        p['asserted_value'] = -float(c['asserted_value'])
        p['perturbation_type'] = 'direction_reversal'
        p['gold_label'] = 'INCONSISTENT'
        perturbations.append(p)
        
    # 2. Percentage Alteration (45)
    pct_claims = [c for c in supported_claims if c.get('unit') == '%' or c.get('operation') == 'percentage_change']
    pool = pct_claims if len(pct_claims) >= 45 else supported_claims
    for c in pool[:45]:
        p = copy.deepcopy(c)
        p['claim_id'] = f"{c['claim_id']}-MOD-PCT"
        # Alter by +/- 5 to 15%
        p['asserted_value'] = round(float(c['asserted_value']) * 1.25, 2)
        p['perturbation_type'] = 'percentage_alteration'
        p['gold_label'] = 'INCONSISTENT'
        perturbations.append(p)

    # 3. Base-year substitution (31)
    for c in supported_claims[:31]:
        p = copy.deepcopy(c)
        p['claim_id'] = f"{c['claim_id']}-MOD-BASE"
        p['prior_period'] = "FY 2020-21" if c.get('prior_period') != "FY 2020-21" else "FY 2019-20"
        p['perturbation_type'] = 'base_year_substitution'
        p['gold_label'] = 'INCONSISTENT'
        perturbations.append(p)

    # 4. Magnitude Change (29)
    for c in supported_claims[:29]:
        p = copy.deepcopy(c)
        p['claim_id'] = f"{c['claim_id']}-MOD-MAG"
        p['asserted_value'] = round(float(c['asserted_value']) * 1.5, 2)
        p['perturbation_type'] = 'magnitude_change'
        p['gold_label'] = 'INCONSISTENT'
        perturbations.append(p)

    # 5. Unit Change (22)
    unit_map = {"kL": "ML", "GJ": "MWh", "tCO2e": "kgCO2e", "%": "count"}
    for c in supported_claims[:22]:
        p = copy.deepcopy(c)
        p['claim_id'] = f"{c['claim_id']}-MOD-UNIT"
        orig_unit = c.get('unit', '')
        p['unit'] = unit_map.get(orig_unit, "unspecified_unit")
        p['perturbation_type'] = 'unit_change'
        p['gold_label'] = 'INCONSISTENT'
        perturbations.append(p)
        
    return perturbations

# ============================================================
# TABLE FORMATTERS
# ============================================================

def format_table_2(results: Dict[str, EvaluationMetrics]) -> str:
    """Renders Table II in exact paper markdown format"""
    table = []
    table.append("TABLE II: REPORTED AGGREGATE VERIFICATION PERFORMANCE")
    table.append("-" * 75)
    table.append(f"{'System':<28} {'P_I':>6} {'R_I':>6} {'F1,I':>6} {'FPR_S':>7} {'Macro-F1':>10}")
    table.append("-" * 75)
    for name, m in results.items():
        table.append(f"{name:<28} {m.precision_inconsistent:>6.2f} {m.recall_inconsistent:>6.2f} {m.f1_inconsistent:>6.2f} {m.fpr_supported:>7.2f} {m.macro_f1:>10.2f}")
    table.append("-" * 75)
    return "\n".join(table)

def format_table_3(ablations: Dict[str, EvaluationMetrics]) -> str:
    """Renders Table III in exact paper markdown format"""
    table = []
    table.append("TABLE III: REPORTED ABLATIONS ON THE NATURAL TEST SUBSET")
    table.append("-" * 65)
    table.append(f"{'Configuration':<35} {'P_I':>6} {'R_I':>6} {'F1,I':>6} {'FPR_S':>7}")
    table.append("-" * 65)
    for name, m in ablations.items():
        table.append(f"{name:<35} {m.precision_inconsistent:>6.2f} {m.recall_inconsistent:>6.2f} {m.f1_inconsistent:>6.2f} {m.fpr_supported:>7.2f}")
    table.append("-" * 65)
    return "\n".join(table)

if __name__ == "__main__":
    raise SystemExit("Legacy illustrative benchmark retired. Run python -m experiments.evaluate with real held-out predictions; no hard-coded scores are printed.")
