"""Automatic references using exact concepts, not the main fuzzy matcher.

These are automatically generated consistency references, NOT independent human
ground truth. Arithmetic and parsed evidence are necessarily shared with the task.
"""
import hashlib
import json
from decimal import Decimal
from .llm import ROOT
from .units import compatible, convert, number, canonical_unit

CONCEPTS = {
    'total_water_consumption': {'TotalVolumeOfWaterConsumption'},
    'total_energy_consumption': {'TotalEnergyConsumedFromRenewableAndNonRenewableSources', 'TotalEnergyConsumption'},
    'scope_1_emissions': {'TotalScope1Emissions'},
    'scope_2_emissions': {'TotalScope2Emissions'},
    'total_waste': {'TotalWasteGenerated'},
    'total_employees': {'NumberOfEmployeesOrWorkersIncludingDifferentlyAbled'},
    'female_employees_percentage': {'PercentageOfFemaleEmployees'},
}


def period_dates(period):
    if isinstance(period, dict):
        return period.get('start'), period.get('end'), period.get('type', 'duration')
    value = str(period or '').removeprefix('FY ').strip()
    if len(value) == 10 and value[4] == '-' and value[7] == '-':
        return None, value, 'instant'
    if len(value) in (7,9) and value[:4].isdigit():
        start = int(value[:4])
        end = int(value[-4:]) if len(value) == 9 else start // 100 * 100 + int(value[-2:])
        if end == start + 1:
            return f'{start}-04-01', f'{end}-03-31', 'duration'
    return None


def reference(claim, facts, filing, config):
    record = {'claim_id': claim.get('perturbation_id',claim['claim_id']),
              'annotation_mode': 'automated_source_reference',
              'source_sha256': hashlib.sha256((ROOT/filing['pdf_path_or_url']).read_bytes()).hexdigest(),
              'xml_sha256': hashlib.sha256((ROOT/filing['xbrl_path_or_url']).read_bytes()).hexdigest(),
              'pdf_page': claim.get('page',claim.get('page_number')), 'source_sentence':claim['source_sentence'],
              'evidence':[], 'candidate_evidence':[], 'calculation':None,
              'reference_label':'INSUFFICIENT_EVIDENCE', 'reason':None}
    def abstain(reason):
        record['reason'] = reason
        return record
    if claim.get('is_target'):
        return abstain('FUTURE_TARGET')
    selected = []
    operation = claim.get('operation')
    operands = ['current'] if operation == 'value_equality' else ['current','previous']
    target_unit = claim.get('unit') if operation in ('value_equality','absolute_change') else claim.get('metric_unit')
    for operand in operands:
        dates = period_dates(claim.get(operand+'_period'))
        if not dates:
            return abstain('MISSING_PERIOD')
        candidates = [f for f in facts if f['concept'] in CONCEPTS.get(claim.get('metric'),set())
                      and (f['period_start'],f['period_end'],f['period_type']) == dates]
        record['candidate_evidence'].extend(candidates)
        if not candidates:
            return abstain('NO_MATCHING_FACT')
        if not claim.get('boundary'):
            return abstain('BOUNDARY_AMBIGUOUS')
        candidates = [f for f in candidates if f['boundary'] == claim['boundary']]
        if not candidates:
            return abstain('BOUNDARY_AMBIGUOUS')
        candidates = [f for f in candidates if {k:v for k,v in json.loads(f['dimensions_json']).items()
                                              if 'boundary' not in k.casefold() and 'consolidat' not in k.casefold()}
                      == (claim.get('dimensions') or {})]
        if len(candidates) != 1:
            return abstain('MULTIPLE_PLAUSIBLE_FACTS')
        f = candidates[0]
        if not target_unit:
            target_unit = f['unit'] if operation == 'direction_of_change' else None
        if not compatible(f['unit'],target_unit):
            return abstain('UNIT_INCOMPATIBLE')
        selected.append(f)
    record['evidence'] = selected
    if len(selected) == 2 and (selected[0]['concept_qname'] != selected[1]['concept_qname'] or
                               selected[0]['period_end'] <= selected[1]['period_end']):
        return abstain('MISSING_OPERAND')
    try:
        claimed = number(claim['asserted_value'])
        current = convert(selected[0]['value'],selected[0]['unit'],target_unit)
        previous = convert(selected[1]['value'],selected[1]['unit'],target_unit) if len(selected)>1 else None
    except (ValueError,KeyError):
        return abstain('MISSING_OPERAND')
    if operation == 'value_equality':
        calculated, formula = current, 'current'
    elif operation == 'absolute_change':
        calculated, formula = current-previous, 'current - previous'
    elif operation == 'percentage_change':
        if previous == 0:
            return abstain('ZERO_DENOMINATOR')
        calculated, formula = (current-previous)/previous*100, '(current - previous) / previous * 100'
    elif operation == 'direction_of_change':
        calculated, formula = Decimal((current>previous)-(current<previous)), 'sign(current - previous)'
    else:
        return abstain('UNSUPPORTED_OPERATION')
    if operation == 'percentage_change':
        supported = abs(calculated-claimed) <= number(config['verification']['percentage_points_tolerance'])
    elif operation == 'direction_of_change' or (canonical_unit(target_unit)=='count' and not claim.get('rounding_explicit')):
        supported = calculated == claimed
    else:
        supported = abs(calculated-claimed)/max(abs(calculated),number(config['verification']['epsilon'])) <= number(config['verification']['relative_tolerance'])
    record.update(reference_label='SUPPORTED' if supported else 'INCONSISTENT',
                  calculation={'formula':formula,'current':str(current),'previous':str(previous) if previous is not None else None,
                               'claimed':str(claimed),'calculated':str(calculated),'unit':target_unit,
                               'tolerances':config['verification']})
    return record


def attach_reference(claim, facts, filing, config):
    record = reference(claim,facts,filing,config)
    claim.update(gold_label=record['reference_label'],gold_xbrl_fact_ids=[f['fact_id'] for f in record['evidence']],
                 annotation_notes='AUTOMATED REFERENCE, not independent ground truth: '+str(record['calculation'] or record['reason']))
    return record
