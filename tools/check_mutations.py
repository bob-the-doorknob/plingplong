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
for case in ('function', 'fixture'):
    path = ROOT/'.phase5'/case
    failures = set(json.loads(path.with_suffix('.json').read_text()))
    selected, reason = decide(path.with_suffix('.patch').read_text(), index)
    assert failures and selected is not None, (case, reason)
    assert failures <= selected, (case, sorted(failures-selected))
    print(case, len(failures), 'failures retained among', len(selected), 'selected')
