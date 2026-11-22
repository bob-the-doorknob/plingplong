import unittest
from structural import literal_binding, global_readers, terminal_assertion


class Globals(unittest.TestCase):
    def test_literal_binding_requires_single_scalar_edit(self):
        old = 'LIMIT = 1\ndef f():\n    return LIMIT\n'
        self.assertEqual(literal_binding(old, old.replace('1', '2')), 'LIMIT')
        self.assertIsNone(literal_binding(old, old.replace('1', 'True')))
        self.assertIsNone(literal_binding(old, old.replace('1', '2') + 'x = 3\n'))

    def test_default_import_and_nested_captures(self):
        self.assertEqual(global_readers('LIMIT = 1\ndef f():\n    return LIMIT\n', 'LIMIT'), {'f'})
        for code in ('def f(x=LIMIT): pass', 'class T: val = LIMIT',
                     'def f(): return lambda: LIMIT', 'def f(): return globals()["LIMIT"]',
                     'def f():\n    global LIMIT\n    LIMIT = 0'):
            with self.subTest(code=code):
                self.assertIsNone(global_readers('LIMIT = 1\n' + code + '\n', 'LIMIT'))


class TestSide(unittest.TestCase):
    OLD = ('import unittest\nclass T(unittest.TestCase):\n'
           '    def test_x(self):\n        self.assertEqual(len([1]), 1)\n')

    def test_literal_in_terminal_assertion(self):
        self.assertEqual(terminal_assertion(self.OLD, self.OLD.replace(']), 1', ']), 2')),
                         ('T::test_x', 4, 'int'))

    def test_prior_statements_setup_and_type_changes_fall_back(self):
        for code in (self.OLD + '        touch_state()\n',
                     self.OLD + '    def tearDown(self): pass\n'):
            self.assertIsNone(terminal_assertion(code, code.replace(']), 1', ']), 2')))
        self.assertIsNone(terminal_assertion(self.OLD, self.OLD.replace(']), 1', ']), True')))


    def test_selection_keeps_readers_and_uncertainty(self):
        from hybrid import decide
        from tools.generalization import git_diff
        path = 'tests/test_x.py'
        case = path + '::T::test_x'
        patch = git_diff(path, self.OLD, self.OLD.replace(']), 1', ']), 2'))
        data = dict(ids=[case, 'reader', 'uncertain'], sources={},
                    hits={path: [1], '!untraced': [2]},
                    structural_evidence={'tests': {path: {'source': self.OLD,
                                                         'assertions': {'T::test_x': [4, 'int']}}}})
        self.assertEqual(decide(patch, data), ({case, 'reader', 'uncertain'}, 'test_assertion'))
        data['hits'][path] = [-1]
        self.assertIsNone(decide(patch, data)[0])
