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

    def test_ordered_verification_requires_all_predecessors(self):
        from verifier import ordered_prefix, ordered_passes
        full = ['writer', 'reader', 'other']
        self.assertEqual(ordered_prefix(full, ['reader'], full, 2), ['writer', 'reader'])
        self.assertIsNone(ordered_prefix(full, ['reader'], full, 1))
        self.assertIsNone(ordered_prefix(full[1:], ['reader'], full, 2))
        report = dict(exit=1, collection_error=False, prefix=['writer', 'reader'],
                      collected=['writer', 'reader'], finished=['writer', 'reader'], passing=['reader'],
                      failed=['reader'], skipped=[])
        self.assertEqual(ordered_passes(report, ['reader']), set())
        report['failed'] = []
        self.assertEqual(ordered_passes(report, ['reader']), {'reader'})
        report['finished'] = ['reader']
        self.assertEqual(ordered_passes(report, ['reader']), set())

    def test_state_fingerprint_detects_nested_replacement_and_aliases(self):
        from fingerprints import fingerprint
        child = ['before']
        first = {'x': child, 'alias': child}
        self.assertNotEqual(fingerprint(first), fingerprint({'x': ['before'], 'alias': ['before']}))
        previous = fingerprint(first)
        child[0] = 'after'
        self.assertNotEqual(previous, fingerprint(first))
        child.append(first)
        self.assertEqual(fingerprint(first), fingerprint(first))

    def test_opaque_fingerprint_is_inconclusive(self):
        from fingerprints import fingerprint
        with self.assertRaises(TypeError):
            fingerprint({'opaque': object()})

    def test_infinite_plan_limits_are_representable(self):
        from fingerprints import fingerprint
        self.assertNotEqual(fingerprint(float('inf')), fingerprint(float('-inf')))
        with self.assertRaises(TypeError):
            fingerprint(float('nan'))

    def test_mutation_recipe_with_two_edits_emits_one_file_patch(self):
        from tools.generalization import CASES, generate
        from hybrid import apply_patch
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'toy.py'
            path.write_bytes(b'a = 0\nb = 0\n')
            try:
                CASES['test_recipe'] = ('code', 'dev',
                                        [('toy.py', 'a = 0', 'a = 1'), ('toy.py', 'b = 0', 'b = 2')])
                patch, changed = generate('test_recipe', Path(tmp))
                self.assertEqual(apply_patch(patch.decode(), {'toy.py': 'a = 0\nb = 0\n'}),
                                 {'toy.py': 'a = 1\nb = 2\n'})
            finally:
                CASES.pop('test_recipe', None)

    def test_import_failure_has_an_explicit_result(self):
        from probes import import_state
        self.assertEqual(import_state(['nonexistent_phase14_module']),
                         {'import_error': 'ModuleNotFoundError'})

    def test_production_provenance_excludes_experimental_stage(self):
        from tools.provenance import production_files
        text = ('FROM python AS selector\nCOPY selector.py evidence.gz /app/\n'
                'FROM selector AS verifier\nCOPY verifier.py /app/\n'
                'FROM selector AS production\n')
        self.assertEqual(production_files(text), ['selector.py', 'evidence.gz'])
