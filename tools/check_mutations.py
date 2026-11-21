"""Check independent mutation labels against production selection after collection."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from hybrid import load, decide

manifest = json.loads((ROOT/'blast-radius-sample/sample/tests.json').read_text())['tests']
index = load(manifest)
assert index
cases = sys.argv[1:] or sorted(p.stem for p in (ROOT/'.phase5').glob('*.json'))
for case in cases:
    path = ROOT/'.phase5'/case
    failures = set(json.loads(path.with_suffix('.json').read_text()))
    selected, reason = decide(path.with_suffix('.patch').read_text(), index)
    if case.startswith('base_'):
        # Core base-class edits must select the full suite.
        assert selected is None, (case, reason)
        print(case, reason, len(failures), 'failures, full suite')
        continue
    if selected is None and case.startswith('attr_'):
        print(case, reason, len(failures), 'failures, full suite')
        continue
    # A comment-only mutation may break nothing; that is evidence a small selection is safe.
    assert selected is not None and (failures or case.startswith(('comment_', 'attr_'))), (case, reason)
    assert failures <= selected, (case, sorted(failures-selected))
    print(case, reason, len(failures), 'failures retained among', len(selected), 'selected')
