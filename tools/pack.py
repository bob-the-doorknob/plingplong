"""Pack events and original files for exact-context validation. Run after clean pytest."""
import hashlib
import sys
import gzip
import json
from collections import defaultdict
from pathlib import Path


repo = Path('/repo')
pin = 'eb11aec4be8cb2122afe713a4816662c3f0fb2fa'
catalog = json.loads((repo/'blast-radius-sample/sample/tests.json').read_text())
ids = sorted(t['id'] for t in catalog['tests'])
assert set(json.loads(Path('/tmp/collected.json').read_text())) == set(ids) | set(catalog['skipped'])
unstable = set()
for order in ('0', '1'):
    outcomes = json.loads(Path('/tmp/pass'+order+'.json').read_text())
    assert set(outcomes['passed']) | set(outcomes['failed']) == set(ids)
    assert order == '1' or not outcomes['failed']
    unstable.update(outcomes['failed'])
lookup = {name:i for i,name in enumerate(ids)}
files = defaultdict(set)
for i,name in enumerate(ids):
    files[name.split('::')[0]].add(i)
hits = defaultdict(set)
hits['!untraced'].update(lookup[t] for t in unstable)
child_files = set()
for log in Path('/tmp/events').iterdir():
    owners = set()
    for line in log.read_text().splitlines():
        owner,key = line.split('\t',1)
        if owner != '*' and key.startswith('sqlglot/') and '::' in key:
            owners.add(owner)
        if owner == '*':
            hits[key].add(-1)
        elif owner in lookup:
            hits[key].add(lookup[owner])
        elif owner in files:
            hits[key].update(files[owner])
        elif owner not in catalog['skipped']:
            raise ValueError(owner)

    if len(owners) == 1:
        child_files.update(owners & files.keys())

# A missing worker trace broadens all tests of the file that launches a pool.
for name, indexes in files.items():
    if 'ProcessPoolExecutor' in (Path('/src')/name).read_text() and name not in child_files:
        hits['!untraced'].update(indexes)

import tarfile
sources = {}
assert hashlib.sha256((repo/'.phase5/src.tar').read_bytes()).hexdigest() == '578d90b1a8e1130094aaf0746117a596e6d94b63c9e4d38aa74f0fea61a37395'
with tarfile.open(repo/'.phase5/src.tar') as archive:
    assert archive.pax_headers.get('comment') == pin
    for member in archive:
        if member.isfile() and ((member.name.startswith('sqlglot/') and member.name.endswith('.py')) or member.name.startswith('tests/fixtures/')):
            try:
                sources[member.name] = archive.extractfile(member).read().decode('utf-8')
            except UnicodeError:
                pass
sys.path.insert(0, '/repo')
from impact import build_index
graph = build_index(Path('/src'))
test_files = {graph['files'][path]: indexes for path, indexes in files.items()}
for path, module in graph['files'].items():
    if not path.startswith('sqlglot/'):
        continue
    pending = [module]
    seen = set()
    while pending:
        for dependent in graph['reverse'][pending.pop()]:
            if dependent.startswith('tests.') and dependent not in seen:
                seen.add(dependent)
                pending.append(dependent)
                hits[path+'::@importers'].update(test_files.get(dependent, ()))
payload = dict(schema=1, python=sys.version.split()[0], unstable=len(unstable), child_files=sorted(child_files), pin=pin, ids=ids, sources=sources, hits={k:sorted(v) if -1 not in v else [-1] for k,v in hits.items()})
(repo/'evidence.gz').write_bytes(gzip.compress(json.dumps(payload,sort_keys=True,separators=(',',':')).encode(),mtime=0))
print(len(ids),len(sources),len(hits),(repo/'evidence.gz').stat().st_size)
