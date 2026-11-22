"""Pack complete two-order traces against the pinned catalog and base evidence."""
from collections import defaultdict
import gzip
import json

from tools.generalization import CATALOG, ROOT, archive, digest
from tools.precision_plan import make_plan


def main():
    root = ROOT / '.phase5/precision'
    plan = json.loads((root / 'plan.json').read_bytes())
    with archive() as tar:
        sources = {member.name: tar.extractfile(member).read().decode('utf-8')
                   for member in tar if member.isfile() and member.name.endswith('.py')
                   and member.name.startswith(('sqlglot/', 'tests/'))}
    guarded = {}
    planned = make_plan(sources, guarded)
    if plan != json.loads(json.dumps(dict(files=planned, guarded=guarded))):
        raise ValueError('trace plan does not match the pinned archive')
    base = (ROOT / 'evidence.gz').read_bytes()
    evidence = json.loads(gzip.decompress(base))
    catalog = json.loads(CATALOG.read_bytes())
    ids = evidence['ids']
    if ids != sorted(test['id'] for test in catalog['tests']):
        raise ValueError('test catalog differs from the base evidence')
    numbered, skipped = set(ids), set(catalog['skipped'])
    owners = defaultdict(set)
    for i, name in enumerate(ids):
        owners[name].add(i)
        owners[name.split('::')[0]].add(i)
    owners['*'] = {-1}
    readers = defaultdict(lambda: defaultdict(set))
    typed_readers = defaultdict(lambda: defaultdict(set))
    extra = set()
    plan_bindings = {(path, name, kind) for sites in plan['files'].values()
                     for _, path, name, kind, _ in sites}
    for order in ('0', '1'):
        run = root / order
        outcomes = json.loads((run / 'outcomes').read_bytes())
        collected = set(json.loads((run / 'collected').read_bytes()))
        if (collected != numbered | skipped or set(outcomes['passed']) | set(outcomes['failed']) != numbered
                or order == '0' and outcomes['failed']):
            raise ValueError(f'incomplete suite outcome for order {order}')
        extra.update(i for name in outcomes['failed'] for i in owners[name])
        started = {p.stem: p.read_text(encoding='utf-8') for p in run.glob('*.start')}
        reports = {p.stem: p for p in run.glob('*.json')}
        if started.keys() != reports.keys() or set(evidence['child_files']) - set(started.values()):
            raise ValueError(f'incomplete process traces in order {order}: {started.keys() - reports.keys()}')
        seen = set()
        for report in reports.values():
            for path, name, kind, key, receiver, contexts in json.loads(report.read_bytes()):
                binding = path, name, kind
                if binding not in plan_bindings:
                    raise ValueError(f'unplanned observation: {binding}')
                seen.add(binding)
                indexes = set()
                for context in contexts:
                    if context in owners:
                        indexes.update(owners[context])
                    elif context not in skipped:
                        raise ValueError(f'unknown observed owner: {context}')
                readers[binding][key].update(indexes)
                if receiver:
                    typed_readers[binding]['::'.join(receiver)].update(indexes)
        if order == '0':
            forward = seen

    bindings = defaultdict(dict)
    for path, name, kind in sorted(forward & seen):
        record = readers[path, name, kind]
        shared = {-1}.intersection(i for indexes in record.values() for i in indexes)
        if shared:
            continue
        guards = plan['guarded'].get(path, {}).get(name, ())
        unknown = set().union(*(owners[file] for file in guards))
        if kind == 'key':
            unknown.update(record.pop(None, ()))
        keys = {key if kind == 'key' else '': sorted(indices) for key, indices in record.items()}
        bindings[path][name] = dict(kind=kind, keys=keys, unknown=sorted(unknown))

    for binding, types in sorted(typed_readers.items()):
        print(*binding, {name: len(indexes) for name, indexes in sorted(types.items())})
    payload = dict(version=1, pin=evidence['pin'], ids=ids, base_digest=digest(base), extra=sorted(extra),
                   collector='typed-read-sites-v1', bindings=bindings)
    packed = gzip.compress(json.dumps(payload, separators=(',', ':'), sort_keys=True).encode(), mtime=0)
    (ROOT / 'precision.gz').write_bytes(packed)
    print(sum(map(len, bindings.values())), 'bindings in', len(packed), 'bytes')


if __name__ == '__main__':
    main()
