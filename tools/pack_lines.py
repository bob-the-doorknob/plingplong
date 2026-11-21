"""Pack a two-order line trace keyed to the verified source and manifest."""
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path

repo = Path('/repo')
archive = repo / '.phase5/src.tar'
assert hashlib.sha256(archive.read_bytes()).hexdigest() == (
    '578d90b1a8e1130094aaf0746117a596e6d94b63c9e4d38aa74f0fea61a37395'
)
baseline = json.loads(gzip.decompress((repo / 'evidence.gz').read_bytes()))
catalog = json.loads((repo / 'blast-radius-sample/sample/tests.json').read_text())
ids = sorted(test['id'] for test in catalog['tests'])
assert baseline['ids'] == ids
assert set(json.loads(Path('/tmp/collected.json').read_text())) == set(ids) | set(catalog['skipped'])
owners = defaultdict(set)
for i, name in enumerate(ids):
    owners[name].add(i)
    owners[name.split('::')[0]].add(i)
owners['*'] = {-1}
extra = set()
for order in ('0', '1'):
    result = json.loads(Path(f'/tmp/pass{order}.json').read_text())
    assert set(result['passed']) | set(result['failed']) == set(ids)
    assert order == '1' or not result['failed']
    for name in result['failed']:
        extra.update(owners[name])

observed = defaultdict(lambda: defaultdict(set))
child_files = set()
for shard in Path('/tmp/lines').glob('*.json'):
    shard_owners = set()
    for path, lines in json.loads(shard.read_text()).items():
        assert path in baseline['sources'], path
        for line, contexts in lines.items():
            for context in contexts:
                if context not in catalog['skipped']:
                    observed[path][int(line)].update(owners[context])
                    shard_owners.add(context)
    nonshared = shard_owners - {'*'}
    if len(nonshared) == 1 and '::' not in next(iter(nonshared)):
        child_files.update(nonshared)
assert set(baseline['child_files']) <= child_files, child_files

groups = {}
files = {}
for path, lines in sorted(observed.items()):
    files[path] = {}
    for line, tests in sorted(lines.items()):
        key = (-1,) if -1 in tests else tuple(sorted(tests))
        files[path][line] = groups.setdefault(key, len(groups))
payload = {
    'version': 1, 'pin': baseline['pin'], 'ids': ids, 'extra': sorted(extra),
    'base_digest': hashlib.sha256((repo / 'evidence.gz').read_bytes()).hexdigest(),
    'groups': list(groups), 'files': files, 'child_files': sorted(child_files),
}
output = repo / 'lines.gz'
output.write_bytes(gzip.compress(json.dumps(payload, separators=(',', ':')).encode(), mtime=0))
print('Observed', sum(map(len, files.values())), 'lines and', len(groups), 'groups.', output.stat().st_size, 'bytes')
