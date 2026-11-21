"""Score independently labeled mutations against the production selector."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from hybrid import apply_patch, decide, load
from selector import schedule

manifest = json.loads((ROOT/'blast-radius-sample/sample/tests.json').read_text())['tests']
catalog = {test['id']: test for test in manifest}
durations = {test['number']: round(test['seconds'] * 1000) for test in manifest}
index = load(manifest)
assert index
reports = ROOT / '.phase5'
cases = sys.argv[1:] or sorted(p.stem for p in reports.glob('*.exit'))
for case in cases:
    path = reports / case
    status_path = path.with_suffix('.exit')
    status = int(status_path.read_text()) if status_path.exists() else None
    if not path.with_suffix('.patch').exists() or not path.with_suffix('.json').exists():
        print(json.dumps(dict(case=case, status='inconclusive', exit=status)))
        continue
    failures = set(json.loads(path.with_suffix('.json').read_text()))
    complete = (
        status in (0, 1) and bool(failures) == (status == 1) and failures <= catalog.keys()
    )
    patch = path.with_suffix('.patch').read_text(encoding='utf-8')
    paths = sorted(apply_patch(patch, index['sources']))
    candidates, reason = decide(patch, index)
    if case.startswith('base_'):
        assert candidates is None, (case, reason)
    selected = set(catalog) if candidates is None else candidates
    workers = schedule([catalog[test_id] for test_id in selected])
    cost = max((sum(durations[n] for n in worker) for worker in workers), default=0) + 2000 * len(workers)
    missed = sorted(failures - selected) if complete else None
    print(json.dumps(dict(case=case, paths=paths, status='completed' if complete else 'inconclusive',
                          exit=status, failures=len(failures) if complete else None, selected=len(selected),
                          ci_milliseconds=cost, reason=reason, missed=missed)))
    assert not missed, (case, missed)
