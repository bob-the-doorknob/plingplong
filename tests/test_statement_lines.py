"""Line narrowing requires aligned executable statements in the pinned source."""
import unittest

from semantic import statement_spans
from predicate import comparison_swap


class StatementLines(unittest.TestCase):
    def test_uses_original_condition_span_and_finds_nested_return(self):
        old = ("def outer(value):\n"
               "    def inner(a):\n"
               "        if (a > 0\n"
               "                and a < 4):\n"
               "            return 1\n"
               "        return 2\n"
               "    return inner(value)\n")
        new = old.replace('a < 4', 'a <= 4').replace('return 2', 'return 3')
        self.assertEqual(statement_spans(old, new), {(3, 4), (6, 6)})

    def test_keeps_function_coverage_for_unmapped_changes(self):
        old = 'def f(a=1):\n    if a > 0:\n        return a\n    return 2\n'
        for new in (old.replace('a=1', 'a=2'), old.replace('return a', 'return -a'),
                    old.replace('return a', 'pass'), old.replace('    if', '    a = 2\n    if')):
            with self.subTest(new=new):
                self.assertIsNone(statement_spans(old, new))

    def test_short_circuit_edit_anchors_to_full_predicate(self):
        old = 'def f(a,b):\n    if a and b:\n        return 1\n'
        self.assertEqual(statement_spans(old,old.replace('and','or')), {(2, 2)})

    def test_executable_docstrings_and_lambda_are_opaque(self):
        for old, new in [('def f():\n    "a"\n', 'def f():\n    "b"\n'),
                         ('def f():\n    return lambda: 1\n', 'def f():\n    return lambda: 2\n')]:
            self.assertIsNone(statement_spans(old, new))

    def test_missing_or_shared_span_falls_back_to_scope(self):
        from hybrid import statement_tests
        old = 'def f(a):\n    if a > 0:\n        return 1\n'
        new = old.replace('> 0', '>= 0')
        path = 'sqlglot/example.py'
        evidence = {'files': {path: {'2': 0}}, 'groups': [[2, 3]], 'extra': [0]}
        self.assertEqual(statement_tests(old, new, path, evidence), {0, 2, 3})
        evidence['groups'][0] = [-1]
        self.assertIsNone(statement_tests(old, new, path, evidence))
        evidence['files'][path] = {}
        self.assertIsNone(statement_tests(old, new, path, evidence))


class ComparisonSwap(unittest.TestCase):
    def test_one_comparison_with_identical_operands_and_context(self):
        old = 'def f(a):\n    if a is None:\n        return 1\n'
        new = old.replace('is None','== None')
        self.assertEqual(comparison_swap(old, new), '2:7')
        self.assertIsNone(comparison_swap(old, new.replace('return 1', 'return 2')))
        self.assertIsNone(comparison_swap(old, new.replace('None', 'a')))
        self.assertIsNone(comparison_swap(old, new.replace('==', '!=')))

    def test_untracked_importers_readers_and_uncertainty_are_retained(self):
        from test_class_attributes import git_patch
        from hybrid import decide
        path = 'sqlglot/example.py'
        old = 'def f(a):\n    if a is None:\n        return 1\n    return 2\n'
        new = old.replace('is None', '== None')
        patch = git_patch({path: (old, new)})
        evidence = {
            'ids': ['uncertain','agree','disagree','reader','importer'],
            'sources': {path: old},
            'hits': {path+'::f': [1, 2], path: [3], path+'::@importers': [4]},
            'predicate_evidence': {'keys': {path+':2:7': 0}, 'groups': [[1]], 'extra': [0]},
        }
        self.assertEqual(decide(patch, evidence),
                         ({'uncertain','disagree','reader','importer'}, 'predicate'))
        self.assertEqual(decide(patch, evidence, 'statement')[0],
                         {'agree','disagree','reader','importer'})

    def test_operand_slots_do_not_admit_custom_rich_comparison(self):
        import importlib
        import sys
        from pathlib import Path
        from unittest.mock import patch

        with patch.object(sys, 'path', [str(Path('tools').resolve()), *sys.path]):
            tracer = importlib.import_module('trace_predicates')

        class Spoof(type):
            @property
            def __mro__(self):
                return (object,)

        class Hostile(metaclass=Spoof):
            def __eq__(self, other):
                raise AssertionError('extra equality evaluation')

        value = Hostile()
        self.assertFalse(tracer.native(value))
        self.assertTrue(tracer.compare(value, value, 'unknown', 'Is'))
        self.assertFalse(tracer.observations['unknown'][tracer.trace_events.context])
        self.assertFalse(tracer.compare(object(), None, 'native', 'Is'))
        self.assertTrue(tracer.observations['native'][tracer.trace_events.context])

    def test_line_and_operand_evidence_can_both_narrow_the_same_patch(self):
        from test_class_attributes import git_patch
        from hybrid import decide
        path = 'sqlglot/example.py'
        old = 'def f(a):\n    if a is None:\n        return 1\n'
        patch = git_patch({path: (old, old.replace('is None', '== None'))})
        evidence = {
            'ids': ['agree', 'never_reached', 'disagree', 'untraced'],
            'sources': {path: old},
            'hits': {path+'::f': [0, 1, 2], '!untraced': [3]},
            'line_evidence': {'files': {path: {'2': 0}}, 'groups': [[0, 2]], 'extra': []},
            'predicate_evidence': {'keys': {path+':2:7': 0}, 'groups': [[0]], 'extra': []},
        }
        self.assertEqual(decide(patch, evidence), ({'disagree','untraced'}, 'predicate'))

    def test_process_pool_tasks_restore_the_previous_context_after_an_error(self):
        import importlib
        import sys
        from pathlib import Path
        from unittest.mock import patch

        with patch.object(sys, 'path', [str(Path('tools').resolve()), *sys.path]):
            tracer = importlib.import_module('trace_predicates')
        history = []

        def fail():
            raise RuntimeError('example')

        with patch.object(tracer.trace_events, 'context', 'tests/example.py'), \
             patch.object(tracer.trace_events, 'owner', history.append):
            with self.assertRaisesRegex(RuntimeError, 'example'):
                tracer.run_labeled('tests/example.py::test_one', fail, (), {})
        self.assertEqual(history, ['tests/example.py::test_one', 'tests/example.py'])

    def test_reassociated_boolean_tree_uses_the_original_control_span(self):
        old = 'def f(a, b, c):\n    if a and b and c:\n        return 1\n'
        new = old.replace('and b and c', 'and b or c')
        self.assertEqual(statement_spans(old, new), {(2, 2)})
        self.assertIsNone(statement_spans(old, new.replace('or c', 'or a')))

    def test_completed_direct_child_removes_only_blanket_guard(self):
        from test_class_attributes import git_patch
        from hybrid import decide
        path = 'sqlglot/example.py'
        old = 'def f():\n    return 1\n'
        patch = git_patch({path: (old, old.replace('return 1', 'return 2'))})
        data = {
            'ids': ['direct_child', 'other_uncertain', 'body'],
            'sources': {path: old},
            'hits': {'!untraced': [0, 1], path + '::f': [2]},
            'line_evidence': {'files': {}, 'certified_direct_children': {'0': ['sqlglot/unrelated.py']}},
        }
        self.assertEqual(decide(patch,data)[0], {'other_uncertain', 'body'})
        data['hits'][path] = [0]
        self.assertEqual(decide(patch,data)[0], {'direct_child', 'other_uncertain', 'body'})
        data['hits'].pop(path)
        data['line_evidence']['certified_direct_children']['0'].append(path)
        self.assertEqual(decide(patch,data)[0], {'direct_child', 'other_uncertain', 'body'})

    def test_direct_child_certificate_needs_both_complete_processes(self):
        import json
        from pathlib import Path
        import tempfile

        from tools.pack_direct_children import complete_footprints

        owners = {'tests/test_example.py::test_child': {9}}
        owner = next(iter(owners))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def write(pid, order, token=None, launches=None, uncertain=(), paths=()):
                record = dict(order=order, token=token, launches=launches or {},
                              uncertain=uncertain, paths=paths)
                (root / f'{pid}.json').write_text(json.dumps(record))

            for order, parent in [('0', 10), ('1', 20)]:
                key = str(parent)
                launch = {key: dict(owner=owner, pid=parent + 1, status=0)}
                write(parent, order, launches=launch)
                write(parent + 1, order, token=key,
                      paths=['sqlglot/__init__.py', f'sqlglot/module_{order}.py'])
            startup = {f'{pid}.json': dict(owner=owner, order=order)
                       for pid, order in [(11, '0'), (21, '1')]}
            executed = {'11': {'sqlglot/__init__.py'}, '21': {'sqlglot/__init__.py'}}
            expected = {'9': ['sqlglot/__init__.py', 'sqlglot/module_0.py', 'sqlglot/module_1.py']}
            self.assertEqual(complete_footprints(root, owners, {9}, startup, executed), expected)
            executed['21'].add('sqlglot/missing.py')
            self.assertEqual(complete_footprints(root, owners, {9}, startup, executed), {})
