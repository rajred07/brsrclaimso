import re, json, os, sys

LOG1 = r'C:\Users\jraj1\.gemini\antigravity-ide\brain\9256af52-61e9-4acf-bafa-e33de1da8de7\.system_generated\tasks\task-1524.log'
LOG2 = r'C:\Users\jraj1\.gemini\antigravity-ide\brain\9256af52-61e9-4acf-bafa-e33de1da8de7\.system_generated\tasks\task-1592.log'
OUT  = r'c:\Users\jraj1\OneDrive\Desktop\xrbr\backend\data\filings\infosys-lts-202526-0434\extracted_claims.json'

RE_PAGE    = re.compile(r'\[(\d+)/\d+\] Processing page (\d+)')
RE_SECTION = re.compile(r'   Section\s*:\s*(.+)')
RE_CLAIM   = re.compile(
    r'\s+\d+\.\s+(.+?)'
    r'\s+=\s+'
    r'([\d\.\-e\+]+)\s+'
    r'([^\|]+?)\s*\|\s*'
    r'([^\|]+?)\s*\|\s*'
    r'([^\|]+?)\s*\|\s*'
    r'([^\[\n]+?)'
    r'(\s*\[TARGET\])?\s*$'
)

def is_source_line(line):
    s = line.strip()
    return s.startswith('"') and s.endswith('"') and len(s) > 2

def parse_log(path):
    claims = []
    current_page = None
    current_section = 'Unknown'
    pending_claim = None
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        for raw in f:
            line = raw.rstrip()

            m = RE_PAGE.search(line)
            if m:
                current_page = int(m.group(2))
                continue

            m = RE_SECTION.match(line)
            if m:
                current_section = m.group(1).strip()
                continue

            if is_source_line(line) and pending_claim is not None:
                pending_claim['source_passage'] = line.strip().strip('"')
                claims.append(pending_claim)
                pending_claim = None
                continue

            m = RE_CLAIM.match(line)
            if m:
                label_raw  = m.group(1).strip()
                val_str    = m.group(2).strip()
                unit       = m.group(3).strip()
                period     = m.group(4).strip()
                operation  = m.group(5).strip()
                confidence = m.group(6).strip()
                is_target  = bool(m.group(7))

                qualifier = None
                qm = re.search(r'\[(.+)\]$', label_raw)
                if qm:
                    qualifier = qm.group(1)
                    label_raw = label_raw[:qm.start()].strip()

                try:
                    value = float(val_str)
                except Exception:
                    value = None

                pending_claim = {
                    'claim_id'       : f'2526-pg{current_page}-{len(claims)+1:04d}',
                    'filing_id'      : 'infosys-lts-202526-0434',
                    'metric'         : re.sub(r'[^a-z0-9_]', '_', label_raw.lower()),
                    'metric_label'   : label_raw,
                    'qualifier'      : qualifier,
                    'operation'      : operation,
                    'asserted_value' : value,
                    'value_as_printed': val_str,
                    'unit'           : unit,
                    'comparator'     : 'exact',
                    'current_period' : period,
                    'prior_period'   : 'FY 2024-25' if ('2026' in period or '2025-26' in period) else None,
                    'boundary'       : 'consolidated',
                    'is_target'      : is_target,
                    'source_passage' : '',
                    'source_type'    : 'table',
                    'confidence'     : confidence,
                    '_page'          : current_page,
                    '_section'       : current_section,
                }
    if pending_claim:
        claims.append(pending_claim)
    return claims

print('Parsing log 1 (run 1: pages 28,29,71,79)...')
c1 = parse_log(LOG1)
print(f'  {len(c1)} claims')

print('Parsing log 2 (run 2: remaining 19 pages)...')
c2 = parse_log(LOG2)
print(f'  {len(c2)} claims')

all_claims = c1 + c2

# Deduplicate on (metric_label, current_period, qualifier, _page)
seen = set()
unique = []
for c in all_claims:
    key = (c['metric_label'], c['current_period'], c.get('qualifier'), c['_page'])
    if key not in seen:
        seen.add(key)
        unique.append(c)

print(f'\nTotal raw: {len(all_claims)}  |  After dedup: {len(unique)}')

for i, c in enumerate(unique):
    c['claim_id'] = f'infosys-2526-{i+1:04d}'

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, 'w', encoding='utf-8') as f:
    json.dump({
        'filing_id'    : 'infosys-lts-202526-0434',
        'year'         : '2025-26',
        'total_claims' : len(unique),
        'claims'       : unique
    }, f, indent=2, ensure_ascii=False)

print(f'SAVED: {len(unique)} claims -> {OUT}')

from collections import Counter
by_page = Counter(c['_page'] for c in unique)
print('\nClaims per page:')
for pg, cnt in sorted(by_page.items()):
    sec = next((c['_section'] for c in unique if c['_page'] == pg), '')[:50]
    print(f'  Page {pg:>3}: {cnt:>3} claims  [{sec}]')
