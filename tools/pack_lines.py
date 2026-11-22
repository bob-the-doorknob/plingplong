"""Pack a two-order line trace keyed to the verified source and manifest."""
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
from pack_direct_children import complete_footprints

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
attributed_workers = {order: set() for order in ("0", "1")}
shards = {p.name: p for p in Path('/tmp/lines').glob('*.json')}
startup = {p.name: json.loads(p.read_text()) for p in Path('/tmp/line-started').glob('*.json')}
assert shards.keys() == startup.keys()
for order in ('0', '1'):
    child_owners = {v['owner'] for v in startup.values() if v['order'] == order}
    assert set(baseline['child_files']) <= child_owners, (order, child_owners)
executed = {}
for shard in shards.values():
    shard_owners = set()
    coverage = json.loads(shard.read_text())
    executed[shard.stem] = set(coverage)
    for path, lines in coverage.items():
        assert path in baseline['sources'], path
        for line, contexts in lines.items():
            for context in contexts:
                if context not in catalog['skipped']:
                    observed[path][int(line)].update(owners[context])
                    shard_owners.add(context)
    process = startup[shard.name]
    file = process['owner']
    if file in baseline['child_files'] and any(owner.startswith(file + '::') for owner in shard_owners):
        attributed_workers[process['order']].add(file)
for files_seen in attributed_workers.values():
    assert set(baseline['child_files']) <= files_seen, files_seen
child_files = set(baseline['child_files'])

groups = {}
files = {}
for path, lines in sorted(observed.items()):
    files[path] = {}
    for line, tests in sorted(lines.items()):
        key = (-1,) if -1 in tests else tuple(sorted(tests))
        files[path][line] = groups.setdefault(key, len(groups))
direct_root = Path('/tmp/direct-children')
direct = {}
if {report.name for report in direct_root.glob('*.json')} == startup.keys():
    direct = complete_footprints(
        direct_root, owners, set(baseline['hits'].get('!untraced', ())),
        startup, executed,
    )
direct = {i: files for i, files in direct.items() if int(i) not in extra}
print('Completed direct-child traces for', len(direct), 'test IDs')
payload = {
    'version': 1, 'pin': baseline['pin'], 'ids': ids, 'extra': sorted(extra),
    'base_digest': hashlib.sha256((repo / 'evidence.gz').read_bytes()).hexdigest(),
    'groups': list(groups), 'files': files, 'child_files': sorted(child_files),
    'certified_direct_children': direct,
}
output = repo / 'lines.gz'
output.write_bytes(gzip.compress(json.dumps(payload, separators=(',', ':')).encode(), mtime=0))
print('Observed', sum(map(len, files.values())), 'lines and', len(groups), 'groups.', output.stat().st_size, 'bytes')
