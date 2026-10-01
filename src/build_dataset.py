"""Bounded automated dataset construction, with explicit non-human references."""
import argparse
import json
import random
import yaml
from .dataset import filings,read_json
from .extract_claims import extract_batch
from .llm import ROOT,load_config
from .perturbations import mutations
from .reference import attach_reference
from .xbrl_parser import load_facts


def build(split):
    config=load_config()
    ranges=yaml.safe_load((ROOT/config['data']['page_ranges']).read_text())
    natural_path=ROOT/config['data']['natural_claims']
    modified_path=ROOT/config['data']['perturbations']
    review_path=ROOT/config['data']['reference_reviews']
    natural=read_json(natural_path)
    modified=read_json(modified_path)
    reviews=read_json(review_path) if review_path.exists() else []
    for filing in filings(config,require_ready=True):
        if filing['split'] != split:
            continue
        fid=filing['filing_id']
        if any(c['filing_id']==fid for c in natural):
            print(f'{fid}: already checkpointed',flush=True)
            continue
        out=ROOT/f'data/candidates/{fid}-batch.json'
        settings=ranges[fid]
        claims=extract_batch(filing,settings['pages'],config,out,settings.get('context_pages'))
        if not 5 <= len(claims) <= 8:
            raise ValueError(f'{fid}: extracted {len(claims)} valid claims; examine rejection archive before continuing')
        facts=load_facts(ROOT/config['data']['facts_db'],fid)
        for claim in claims:
            claim['split']=split
            reviews.append(attach_reference(claim,facts,filing,config))
            natural.append(claim)
        natural_path.write_text(json.dumps(natural,indent=2,ensure_ascii=False),encoding='utf-8')
        review_path.write_text(json.dumps(reviews,indent=2,ensure_ascii=False),encoding='utf-8')
        print(f'{fid}: {len(claims)} sourced claims',flush=True)
    # Keep mutations in the parent's company split. Fixed counts are chosen before test labels.
    desired=28 if split=='development' else 12
    candidates=[]
    manifest={f['filing_id']:f for f in filings(config)}
    for parent in natural:
        if parent['split']!=split or parent['gold_label']!='SUPPORTED':
            continue
        filing=manifest[parent['filing_id']]
        facts=load_facts(ROOT/config['data']['facts_db'],parent['filing_id'])
        for kind,sentence,changes in mutations(parent):
            claim={**parent,**changes,'source_sentence':sentence,
                   'perturbation_id':parent['claim_id']+'-mod-'+kind,
                   'original_claim_id':parent['claim_id'],'mutation_type':kind,
                   'original_sentence':parent['source_sentence'],'modified_sentence':sentence}
            review=attach_reference(claim,facts,filing,config)
            if review['reference_label']=='SUPPORTED':
                continue  # never assume a mutation contradicts the evidence
            candidates.append((claim,review))
    random.Random(config['random_seed']).shuffle(candidates)
    selected=candidates[:desired]
    modified=[c for c in modified if c['split']!=split]
    reviews=[r for r in reviews if '-mod-' not in r['claim_id'] or
             not any(r['claim_id'].startswith(c['claim_id']+'-mod-') for c in natural if c['split']==split)]
    modified.extend(c for c,r in selected)
    reviews.extend(r for c,r in selected)
    modified_path.write_text(json.dumps(modified,indent=2,ensure_ascii=False),encoding='utf-8')
    review_path.write_text(json.dumps(reviews,indent=2,ensure_ascii=False),encoding='utf-8')
    print(f'{split}: {len(selected)}/{desired} actual verified mutations',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--split',choices=['development','test'],required=True)
    build(parser.parse_args().split)
