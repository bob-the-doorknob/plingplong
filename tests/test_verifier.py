import tempfile
import unittest
from pathlib import Path


class VerifierTests(unittest.TestCase):
    def test_overlay_preserves_originals_and_uses_patched_bytes(self):
        from verifier import overlay
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / 'base'
            (base / 'pkg').mkdir(parents=True)
            (base / 'pkg/changed.py').write_bytes(b'original')
            (base / 'pkg/data').write_bytes(b'data')
            with overlay(base, {'pkg/changed.py': 'replacement'}, directory=tmp) as view:
                self.assertEqual((view / 'pkg/changed.py').read_bytes(), b'replacement')
                self.assertEqual((view / 'pkg/data').read_bytes(), b'data')
                self.assertTrue((view / 'pkg/data').is_symlink())
            self.assertEqual((base / 'pkg/changed.py').read_bytes(), b'original')

    def test_planner_skips_candidates_hidden_under_makespan(self):
        from verifier import plan
        tests = [dict(id='heavy', number=0, seconds=20), dict(id='cheap', number=1, seconds=.05)]
        self.assertEqual(plan(tests, {'heavy'}), [])
        self.assertEqual(plan(tests[1:], set()), ['cheap'])

    def test_only_complete_unskipped_passes_count(self):
        from verifier import passed_tests
        report = dict(exit=1, collected=['ok', 'failed', 'skip'], passing=['ok', 'failed', 'skip'],
                      failed=['failed'], skipped=['skip'], collection_error=False)
        self.assertEqual(passed_tests(report, ['ok', 'failed', 'skip']), {'ok'})
        self.assertEqual(passed_tests(report | {'collection_error': True}, report['collected']), set())
        self.assertEqual(passed_tests(report, ['different']), set())
