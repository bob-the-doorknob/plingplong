"""Behavior tests for experimental static impact analysis; no sample labels."""
import tempfile
import unittest
from pathlib import Path
from impact import build_index, select_tests


def patch(path, old='return 1', new='return 2'):
    return f'diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n-{old}\n+{new}\n'


class ImpactTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.files = {
            'sqlglot/__init__.py': '',
            'sqlglot/leaf.py': 'def value():\n    return 1\n',
            'sqlglot/other.py': 'def value():\n    return 9\n',
            'sqlglot/bridge.py': 'from .leaf import value\n',
            'tests/test_leaf.py': 'from sqlglot.bridge import value\n',
            'tests/test_other.py': 'import sqlglot.other\n',
        }
        self.tests = [dict(number=17, file='tests/test_leaf.py'), dict(number=42, file='tests/test_other.py')]

    def index(self):
        for name, text in self.files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        return build_index(self.root)

    def test_relative_transitive_dependency(self):
        self.assertEqual(select_tests(patch('sqlglot/leaf.py'), self.tests, self.index()), [17])

    def test_direct_import_and_number_mapping(self):
        self.assertEqual(select_tests(patch('sqlglot/other.py'), self.tests, self.index()), [42])

    def test_multifile_union(self):
        self.assertEqual(select_tests(patch('sqlglot/leaf.py')+patch('sqlglot/other.py'), self.tests, self.index()), [17,42])

    def test_unknown_shared_and_malformed_fallback(self):
        index = self.index()
        for path in ['sqlglot/parser.py','sqlglot/generator.py','sqlglot/__init__.py','sqlglot/dialects/foo.py','tests/helpers.py','tests/conftest.py','pyproject.toml','sqlglot/new.py']:
            with self.subTest(path=path):
                self.assertEqual(select_tests(patch(path),self.tests,index), [17,42])
        for text in ['', 'garbage', patch('sqlglot/leaf.py').replace('@@ -1 +1 @@','@@ nonsense @@'), patch('sqlglot/leaf.py')+'junk\n']:
            with self.subTest(text=text):
                self.assertEqual(select_tests(text,self.tests,index), [17,42])

    def test_comments_fallback(self):
        self.assertEqual(select_tests(patch('sqlglot/leaf.py','# old','# new'),self.tests,self.index()), [17,42])

    def test_missing_metadata_fallback(self):
        self.assertEqual(select_tests(patch('sqlglot/leaf.py'),self.tests,None), [17,42])

    def test_unresolved_import_fallback(self):
        self.files['tests/test_other.py'] = 'import sqlglot.missing\n'
        self.assertEqual(select_tests(patch('sqlglot/leaf.py'),self.tests,self.index()), [17,42])

    def test_dynamic_import_fallback(self):
        self.files['sqlglot/other.py'] = 'import importlib\nvalue = importlib.import_module("sqlglot.leaf")\n'
        self.assertEqual(select_tests(patch('sqlglot/leaf.py'),self.tests,self.index()), [17,42])

    def test_syntax_error_fallback(self):
        self.files['sqlglot/other.py'] = 'invalid python !'
        self.assertEqual(select_tests(patch('sqlglot/leaf.py'),self.tests,self.index()), [17,42])

    def test_added_removed_renamed_symbols_remain_file_level(self):
        for old,new in [('def foo():','def bar():'), ('','def added():'), ('def removed():','')]:
            self.assertEqual(select_tests(patch('sqlglot/leaf.py',old,new),self.tests,self.index()),[17])

    def test_missing_test_module_fallback(self):
        self.tests.append(dict(number=99,file='tests/test_missing.py'))
        self.assertEqual(select_tests(patch('sqlglot/leaf.py'),self.tests,self.index()),[17,42,99])

    def test_parent_relative_import(self):
        self.files['sqlglot/sub/__init__.py'] = ''
        self.files['sqlglot/sub/bridge.py'] = 'from ..leaf import value\n'
        self.files['tests/test_leaf.py'] = 'from sqlglot.sub.bridge import value\n'
        self.assertEqual(select_tests(patch('sqlglot/leaf.py'),self.tests,self.index()),[17])
