"""Line narrowing requires aligned executable statements in the pinned source."""
import unittest

from semantic import statement_spans


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
