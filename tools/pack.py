"""Pack events and original files for exact-context validation. Run after clean pytest."""
import base64
import hashlib
import os
import sys
import gzip
import json
from collections import defaultdict
from pathlib import Path


repo = Path(os.environ.get('BR_REPO', '/repo'))
src = Path(os.environ.get('BR_SRC', '/src'))
out = Path(os.environ.get('BR_OUT', repo/'evidence.gz'))
raw = Path(os.environ.get('BR_RAW', '/tmp'))
pin = 'eb11aec4be8cb2122afe713a4816662c3f0fb2fa'
catalog = json.loads((repo/'blast-radius-sample/sample/tests.json').read_text())
ids = sorted(t['id'] for t in catalog['tests'])
assert set(json.loads((raw/'collected.json').read_text())) == set(ids) | set(catalog['skipped'])
unstable = set()
for order in ('0', '1'):
    outcomes = json.loads((raw/('pass'+order+'.json')).read_text())
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
receivers, reads, writes, consumers, cache_tests = (defaultdict(set), defaultdict(set), defaultdict(set),
                                                    defaultdict(set), set())
CLASS_RECORDS = {'R': receivers, 'A': reads, 'W': writes}
for log in (raw/'events').iterdir():
    owners = set()
    for line in log.read_text().splitlines():
        owner,key = line.split('\t',1)
        if key[1:2] == '\t' and key[0] in 'RAWIC':
            kind, rest = key[0], key[2:]
            if kind == 'I':
                name, consumer = rest.rsplit('\t', 1)
                consumers[name].add(consumer)
                continue
            tests = {lookup[owner]} if owner in lookup else files.get(owner)
            if tests is None:
                if owner == '*' or owner not in catalog['skipped']:
                    raise ValueError((owner, key))
                continue
            if kind == 'C':
                cache_tests.update(tests)
            else:
                CLASS_RECORDS[kind][rest].update(tests)
            continue
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
    if 'ProcessPoolExecutor' in (src/name).read_text() and name not in child_files:
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
sys.path.insert(0, str(repo))
from impact import build_index
graph = build_index(src)
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
from hybrid import is_core


def encode(indexes):
    indexes = sorted(indexes)
    if len(indexes) < 48:
        return indexes
    bits = sum(1 << i for i in indexes)
    return base64.b64encode(bits.to_bytes((len(ids) + 7) // 8, 'little')).decode()


def traced(key):
    return key.startswith(('sqlglot/', 'tests/'))


bases = defaultdict(set)
for dump in (raw/'classes').iterdir():
    for cls, parents in json.loads(dump.read_text()).items():
        if traced(cls):
            bases[cls].update(p for p in parents if traced(p))
# Runtime reads are only consulted for non-core defining classes; keep those.
attribute_reads = {k: v for k, v in reads.items() if traced(k) and not is_core(k.split('::')[0])}
classes = dict(
    M={k: sorted(v) for k, v in sorted(bases.items())},
    R={k: encode(v) for k, v in sorted(receivers.items()) if traced(k)},
    A={k: encode(v) for k, v in sorted(attribute_reads.items())},
    I={k: sorted(v) for k, v in sorted(consumers.items()) if traced(k)},
    W=sorted(k for k in writes if traced(k)),
    # Reads by a test that changed sqlglot caches may feed state that later tests reuse.
    K=sorted(k for k, v in attribute_reads.items() if v & cache_tests),
)
print('classes', {k: len(v) for k, v in classes.items()}, 'cache tests', len(cache_tests))
payload = dict(schema=1, classes=classes, python=sys.version.split()[0], unstable=len(unstable), child_files=sorted(child_files), pin=pin, ids=ids, sources=sources, hits={k:sorted(v) if -1 not in v else [-1] for k,v in hits.items()})
out.write_bytes(gzip.compress(json.dumps(payload,sort_keys=True,separators=(',',':')).encode(),mtime=0))
print(len(ids),len(sources),len(hits),out.stat().st_size)
