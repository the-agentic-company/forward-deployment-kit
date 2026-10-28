import json, re, sys
src = open(sys.argv[1]).read().splitlines()
start = next(i for i,l in enumerate(src) if l.startswith('NOT_PUBLIC = '))
end = next(i for i,l in enumerate(src) if l.startswith('def ai_mode_items'))
ns = {'re': re}; exec("\n".join(src[start:end]), ns)
clean, prefill = ns['clean_ai_text'], ns['prefill_research']
cases = []
for r in json.load(open('repro-aimode.json'))['records']:
    cases.append((r['id'], 'tool-replay', (r.get('aiMode') or {}).get('answer') or ''))
for r in json.load(open('repro-owner-only.json')):
    if r['kind'] == '12-points-run2': cases.append((r['id'], r['kind'], r.get('answer') or ''))
for lid, kind, ans in cases:
    c = clean(ans); res = prefill(c)
    npa = [l for l in c.splitlines() if re.search('not publicly', l, re.I)]
    print(f"{lid:11} {kind:14} owner={res.get('owner',{}).get('value')!r:40} facts={len(res.get('facts',[]))} menu={bool(res.get('menuUSP'))} best={bool(res.get('bestSeller'))} NPA-lines-kept={len(npa)}")
# synthetic: heading + bullet, and facts heading followed by bullets must keep 3 facts
syn = "1) Owner or Manager Full Name\n- Joyce (full surname Not publicly available)\n2) Menu style: diner\n3) 3 Interesting Facts\n- opened 1952\n- family run\n- on Route 11\n4) Best-selling dish: pancakes"
r = prefill(clean(syn)); print('synthetic owner=', r['owner']['value'], '| facts=', [f['value'] for f in r['facts']], '| best=', r['bestSeller']['value'])
assert r['owner']['value'] == 'Joyce' and len(r['facts']) == 3 and r['bestSeller']['value'] == 'pancakes'
syn2 = "1) Owner or Manager Full Name\n- Not publicly available\n3. Interesting facts:\n- a\n- b\n- c"
r2 = prefill(clean(syn2)); assert 'owner' not in r2 and len(r2['facts']) == 3, r2
print('SELF-CHECK OK')
