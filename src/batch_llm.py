"""Batched requests reduce free-tier request use without changing system roles."""
import json
from .extract_claims import validate_claim,compact
from .llm import ROOT
from .matcher import ALIASES,metric_score,retrieve
from .verifier import LABELS


def interpret_modified_batch(claims,manifest,config,client):
    if not claims:
        return {}
    contexts={}
    supplied=[]
    for c in claims:
        context_id=f"{c['filing_id']}:p{c.get('page',c.get('page_number'))}"
        contexts[context_id]=c.get('pdf_context')
        supplied.append({'claim_id':c['claim_id'],'company':c['company'],
                         'reporting_year':manifest[c['filing_id']]['reporting_year'],
                         'page_number':c.get('page',c.get('page_number')),
                         'source_sentence':c['source_sentence'],'context_id':context_id})
    rules=(ROOT/config['prompts']['extraction']).read_text(encoding='utf-8')
    prompt=('Interpret EACH supplied statement, returning an array with exactly one object per claim_id. '
            'These are controlled modifications: the supplied source_sentence is the claim to interpret. '
            'PDF contexts are for headers, units, dates and boundaries only. Preserve the supplied statement '
            'and its altered asserted number exactly. Do not replace it with the original PDF value. '
            'Do not verify, calculate, or output verdicts.\n'+rules+'\nCONTEXTS:\n'+json.dumps(contexts)+
            '\nSTATEMENTS:\n'+json.dumps(supplied))
    items,run=client.generate(prompt,'modified_batch_interpretation')
    if not isinstance(items,list):
        raise ValueError('Batch interpretation requires a JSON array')
    lookup={c['claim_id']:c for c in claims}
    result={}
    for item in items:
        cid=item.get('claim_id')
        if cid not in lookup or cid in result:
            raise ValueError('Unexpected or duplicate batch interpretation ID')
        c=lookup[cid]
        validated=validate_claim(item,manifest[c['filing_id']],c.get('page',c.get('page_number')))
        if compact(validated['source_sentence'])!=compact(c['source_sentence']):
            raise ValueError('Batch interpretation rewrote the supplied statement')
        result[cid]=({**validated,'claim_id':cid},run)
    if set(result)!=set(lookup):
        raise ValueError('Batch interpretation omitted statements')
    return result


def short_fact(f):
    return {k:f.get(k) for k in ('fact_id','concept','value','unit','period_start','period_end','period_type',
                                'boundary','dimensions_json','normalized_value','normalized_unit','unit_source')}


def verdict_batch(system,claims,interpretations,fact_cache,config,client):
    pools={}
    supplied=[]
    evidence_map={}
    for c in claims:
        interpreted=interpretations[c['claim_id']][0]
        facts=fact_cache[c['filing_id']]
        if system=='llm_only':
            key=c['filing_id']
            if key not in pools:
                pools[key]=[short_fact(f) for f in facts if any(metric_score(k,f)>=config['matching']['minimum_similarity'] for k in ALIASES)]
            evidence={'facts':pools[key],'selection':'all same-filing metric-family facts'}
        else:
            key=c['claim_id']
            retrieval=retrieve(interpreted,facts,config['matching'])
            chosen={f['fact_id']:f for f in (retrieval['current'],retrieval['previous']) if f}
            for candidates in retrieval['candidates'].values():
                chosen.update({x['fact']['fact_id']:x['fact'] for x in candidates})
            pools[key]=[short_fact(f) for f in chosen.values()]
            evidence={'facts':pools[key],'retrieval':retrieval}
        evidence_map[c['claim_id']]=evidence
        safe={k:interpreted.get(k) for k in ('claim_id','company','source_sentence','metric','operation',
                                             'asserted_value','unit','metric_unit','current_period','previous_period','boundary','dimensions')}
        safe.update(evidence_key=key,retrieval_reason=evidence.get('retrieval',{}).get('reason'))
        supplied.append(safe)
    rules=(ROOT/config['prompts']['baseline']).read_text(encoding='utf-8')
    prompt=('Return a JSON array with exactly one prediction per claim_id. Each prediction must contain claim_id '
            'and the fields required below. Evidence pools are shared by key. Cite only IDs in that claim\'s pool. '
            'Be concise: explanation at most 40 words. No gold/reference labels are provided.\n'+rules+
            '\nEVIDENCE POOLS:\n'+json.dumps(pools)+'\nCLAIMS:\n'+json.dumps(supplied))
    items,run=client.generate(prompt,'batch_'+system)
    lookup={c['claim_id']:c for c in claims}
    def validated(items, run):
        if not isinstance(items, list):
            raise ValueError('Baseline batch response must be an array')
        traces = {}
        for answer in items:
            if not isinstance(answer, dict):
                raise ValueError('Each baseline prediction must be an object')
            cid = answer.get('claim_id')
            if not isinstance(cid, str) or cid not in lookup or cid in traces or answer.get('verdict') not in LABELS:
                raise ValueError('Invalid baseline ID/verdict')
            matched = answer.get('matched_fact_ids')
            evidence = evidence_map[cid]
            if (not isinstance(matched, list) or any(not isinstance(fid, str) for fid in matched) or
                    not set(matched).issubset({f['fact_id'] for f in evidence['facts']})):
                raise ValueError('Baseline cited invented facts')
            if answer['verdict'] == 'INSUFFICIENT_EVIDENCE' and not answer.get('abstention_reason'):
                raise ValueError('Baseline abstention needs a reason')
            c = lookup[cid]
            traces[cid] = {'claim_id': cid, 'source_sentence': c['source_sentence'],
                           'pdf_page': c.get('page', c.get('page_number')), 'verdict': answer['verdict'],
                           'matched_fact_ids': matched, 'calculated_value': answer.get('calculated_value'),
                           'calculation': answer.get('explanation'), 'abstention_reason': answer.get('abstention_reason'),
                           'evidence': evidence, 'llm_run': run, 'interpretation_run': interpretations[cid][1],
                           'decision_method': 'LLM_BASELINE',
                           'batch_runtime_note': 'Per-example LLM runtime not measured; batch wall time is in llm_run.'}
        if set(traces) != set(lookup):
            raise ValueError('Baseline omitted predictions')
        return traces

    try:
        return validated(items, run)
    except ValueError as error:
        rejected_run, validation_error = run, str(error)
    # One fresh model response, never a local rewrite of invalid verdicts or IDs.
    repair = ('\nRESPONSE FORMAT VALIDATION ERROR: ' + validation_error +
              '\nReturn a JSON ARRAY of objects, one for each supplied claim_id. '
              'The verdict MUST be exactly SUPPORTED, INCONSISTENT, or INSUFFICIENT_EVIDENCE. '
              'ABSTAIN is not an allowed verdict. Include matched_fact_ids as an array of '
              'IDs from that claim\'s evidence pool, and a nonempty abstention_reason for '
              'INSUFFICIENT_EVIDENCE. Use the original claims and evidence above. '
              'Do not invent missing evidence or emit any additional claim IDs.')
    items, run = client.generate(prompt + repair, 'batch_' + system + '_format_repair')
    traces = validated(items, run)  # a second invalid response stops the run
    for trace in traces.values():
        trace['response_format_retry'] = {'rejected_run': rejected_run, 'validation_error': validation_error}
    return traces
