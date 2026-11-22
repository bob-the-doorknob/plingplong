"""Label an arbitrary same-path patch against the pinned archive: python label_patch.py PATCH OUT.json."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))
import generalization as g  # noqa: E402
from hybrid import apply_patch  # noqa: E402


def main():
    import pytest
    patch_path, out = Path(sys.argv[1]), Path(sys.argv[2])
    patch = patch_path.read_bytes()
    os.environ['SKIP_INTEGRATION'] = '0'
    with tempfile.TemporaryDirectory(prefix='sqlglot-') as tmp, g.archive() as source:
        root = Path(tmp)
        source.extractall(root, filter='data')
        text = patch.decode('utf-8')
        names = [line.split()[2][2:] for line in text.splitlines() if line.startswith('diff --git ')]
        updates = apply_patch(text, {name: (root / name).read_bytes().decode('utf-8') for name in names})
        for name, content in updates.items():
            (root / name).write_bytes(content.encode('utf-8'))
        os.chdir(root)
        sys.path.insert(0, str(root))
        os.environ['PYTHONPATH'] = str(root)
        outcomes = g.Outcomes()
        start = time.perf_counter()
        status = int(pytest.main(['-q', '--tb=no', '-p', 'no:cacheprovider', 'tests'], plugins=[outcomes]))
    out.write_text(json.dumps(dict(sha256=g.digest(patch), exit=status, collected=outcomes.collected,
                                   finished=sorted(outcomes.finished), errors=outcomes.errors,
                                   failed=sorted(outcomes.failed), skipped=sorted(outcomes.skipped),
                                   wall=time.perf_counter() - start)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
