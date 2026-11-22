import unittest
from structural import literal_binding, global_readers


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
