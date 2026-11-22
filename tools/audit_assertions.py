"""Observe test assertions and source reads in the pinned locked suite."""
from collections import defaultdict
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

from generalization import archive, CATALOG, digest, REPORTS, Outcomes, SHA256, complete_label


def main(reverse):
    import pytest

    class Audit(Outcomes):
        def pytest_collection_modifyitems(self, items):
            if reverse:
                items.reverse()

    with tempfile.TemporaryDirectory() as tmp, archive() as source:
        root = Path(tmp)
        source.extractall(root, filter='data')
        os.chdir(root)
        os.environ.update(SKIP_INTEGRATION='0', PYTHONPATH=str(root))
        sys.path.insert(0, str(root))
        paths, types = set(), defaultdict(set)

        def audit(event, args):
            if event != 'open' or not isinstance(args[0], (str, bytes)):
                return
            path = os.path.abspath(os.fsdecode(args[0]))
            if not (path.startswith(tmp + '/tests/') and path.endswith('.py')):
                return
            frame = sys._getframe(1)
            while frame:
                code = frame.f_code
                if ((code.co_name == 'get_data' and code.co_filename == '<frozen importlib._bootstrap_external>')
                        or (code.co_name == '_rewrite_test' and code.co_filename.endswith('/_pytest/assertion/rewrite.py'))):
                    return
                frame = frame.f_back
            paths.add(path[len(tmp) + 1:])

        def observed(self, first, second, msg=None):
            frame = sys._getframe(1)
            path = frame.f_code.co_filename
            if path.startswith(tmp + '/tests/'):
                types[f'{path[len(tmp)+1:]}:{frame.f_lineno}'].add(
                    type(first).__name__ if type(first) in (int, str, bool, bytes) else '?')
            return original(self, first, second, msg)

        original = unittest.TestCase.assertEqual
        unittest.TestCase.assertEqual = observed
        sys.addaudithook(audit)
        outcomes = Audit()
        status = int(pytest.main(['-q', '--tb=no', 'tests'], plugins=[outcomes]))
        payload = dict(sha256=digest(b''), archive_sha256=SHA256, catalog_sha256=digest(CATALOG.read_bytes()),
                       exit=status, collected=outcomes.collected, finished=sorted(outcomes.finished),
                       failed=sorted(outcomes.failed), skipped=sorted(outcomes.skipped), errors=outcomes.errors)
        catalog = json.loads(CATALOG.read_bytes())
        if not complete_label(payload, b'', catalog, payload['catalog_sha256']) or (status and not reverse):
            raise ValueError('incomplete assertion audit')
        payload.update(read=sorted(paths), types={k: sorted(v) for k, v in sorted(types.items())})
        (REPORTS.parent / f'assertions-{int(reverse)}.json').write_text(json.dumps(payload))


if __name__ == '__main__':
    main(sys.argv[1:] == ['reverse'])
