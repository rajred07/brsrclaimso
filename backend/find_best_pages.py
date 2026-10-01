import json

with open('data/processed/batches.json', 'r', encoding='utf-8') as f:
    batches = json.load(f)

keywords = ['reduced', 'decreased', 'increased', 'emissions', 'water', 'energy', 'scope 1', 'scope 2', '%']

results = []
for b in batches:
    text = b['text'].lower()
    score = sum(text.count(k) for k in keywords)
    results.append((score, b['batch_id'], b['start_page'], b['end_page']))

# Sort by score descending and print top 5
results.sort(reverse=True)
for score, batch_id, start, end in results[:5]:
    print(f"Batch {batch_id} (Pages {start}-{end}): {score} keyword hits")
