"""Local text search to select BRSR pages; never sends whole reports to an LLM."""
import json
import re
import pymupdf
import yaml
from .dataset import filings
from .llm import ROOT, load_config

PATTERNS = {
    "energy": r"total\s+energy\s+(?:consum|usage)|total\s+energy\s+consumed",
    "water": r"total\s+(?:volume\s+of\s+)?water\s+consump",
    "emissions": r"total\s+scope\s*1\s+emissions",
    "waste": r"total\s+waste\s+generated",
}


def discover():
    config = load_config()
    selections, previews = {}, {}
    for filing in filings(config):
        if not filing['pdf_path_or_url']:
            continue
        with pymupdf.open(ROOT / filing['pdf_path_or_url']) as pdf:
            texts = [p.get_text() for p in pdf]
        selected = set()
        rows = {}
        for metric, pattern in PATTERNS.items():
            matches = [(i + 1, text) for i, text in enumerate(texts) if re.search(pattern, text, re.I)]
            # Prefer a BRSR essential-indicator table, not an earlier narrative duplicate.
            ranked = sorted(matches, key=lambda item: (-sum(bool(re.search(p, item[1], re.I)) for p in PATTERNS.values()),
                                                       -int('2022' in item[1] and '2023' in item[1]), item[0]))
            if ranked:
                page, text = ranked[0]
                selected.add(page)
                match = re.search(pattern, text, re.I)
                rows[metric] = {'page': page, 'excerpt': text[max(0, match.start()-250):match.end()+800]}
        context = [i + 1 for i, text in enumerate(texts) if re.search(r'reporting\s+boundary', text, re.I)]
        context = context[:1]
        overrides = {'infosys-2023-24': ([160,161,162,163,164], [131]),
                     'reliance-2023-24': ([38,39,40], [5]),
                     'larsen-toubro-2023-24': ([34,35,36,37], [2]),
                     'mahindra-2024-25': ([131,132,133], [116])}
        if filing['filing_id'] in overrides:
            selected, context = overrides[filing['filing_id']]
        selections[filing['filing_id']] = {'pages': ','.join(map(str, sorted(selected))),
                                           'context_pages': ','.join(map(str, context))}
        previews[filing['filing_id']] = {'metrics': rows, 'boundary': texts[context[0]-1] if context else None}
        print(f"{filing['filing_id']}: pages={sorted(selected)}, context={context}")
    (ROOT / config['data']['page_ranges']).write_text(yaml.safe_dump(selections, sort_keys=False))
    (ROOT / 'data/page_discovery.json').write_text(json.dumps(previews, indent=2), encoding='utf-8')


if __name__ == '__main__':
    discover()
