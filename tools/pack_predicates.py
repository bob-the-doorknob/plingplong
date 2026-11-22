"""Pack universal agreement within each independently observed test context."""
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path

repo = Path('/repo')
baseline_bytes = (repo / 'evidence.gz').read_bytes()
base = json.loads(gzip.decompress(baseline_bytes))
assert hashlib.sha256((repo / '.phase5/src.tar').read_bytes()).hexdigest() == (
    '578d90b1a8e1130094aaf0746117a596e6d94b63c9e4d38aa74f0fea61a37395'
)
catalog = json.loads((repo / 'blast-radius-sample/sample/tests.json').read_text())
ids = sorted(test['id'] for test in catalog['tests'])
assert base['ids'] == ids
assert set(json.loads(Path('/tmp/collected.json').read_text())) == set(ids) | set(catalog['skipped'])
owners = defaultdict(set)
for i, name in enumerate(ids):
    owners[name].add(i)
    owners[name.split('::')[0]].add(i)

extra = set()
for order in ('0', '1'):
    result = json.loads(Path(f'/tmp/pass{order}.json').read_text())
    assert set(result['passed']) | set(result['failed']) == set(ids)
    assert order == '1' or not result['failed']
    for name in result['failed']:
        extra.update(owners[name])

shards = {p.name: p for p in Path('/tmp/predicates').glob('*.json')}
assert shards.keys() == {p.name for p in Path('/tmp/lines').glob('*.json')}
startup = {p.name: json.loads(p.read_text()) for p in Path('/tmp/predicate-started').glob('*.json')}
assert shards.keys() == startup.keys()
for order in ('0', '1'):
    child_owners = {v['owner'] for v in startup.values() if v['order'] == order}
    assert set(base['child_files']) <= child_owners, (order, child_owners)
known = (defaultdict(set), defaultdict(set))
unsafe = defaultdict(set)
shared = set()
for name, shard in shards.items():
    order = int(startup[name]['order'])
    for key, results in json.loads(shard.read_text()).items():
        assert key.rsplit(':', 2)[0] in base['sources']
        for owner, matched in results.items():
            if owner == '*':
                shared.add(key)
            elif owner not in catalog['skipped']:
                if not matched:
                    unsafe[key].update(owners[owner])
                elif '::' in owner:
                    known[order][key].update(owners[owner])

groups, keys = {}, {}
for key, tests in sorted(known[0].items()):
    if key in shared:
        continue
    agreeing = tuple(sorted((tests & known[1][key]) - unsafe[key] - extra))
    if agreeing:
        keys[key] = groups.setdefault(agreeing, len(groups))

payload = dict(version=1, pin=base['pin'], ids=ids, extra=sorted(extra),
               base_digest=hashlib.sha256(baseline_bytes).hexdigest(),
               groups=list(groups), keys=keys, child_files=base['child_files'])
output = repo / 'predicates.gz'
output.write_bytes(gzip.compress(json.dumps(payload, separators=(',', ':')).encode(), mtime=0))
print('Observed agreement for', len(keys), 'comparison sites.', output.stat().st_size, 'bytes.')
