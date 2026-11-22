import unittest
from hybrid import apply_patch, decide

class Reconstruction(unittest.TestCase):
    def test_context_and_new_coordinates(self):
        patch = 'diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -2 +2 @@\n-b\n+B\n'
        self.assertEqual(apply_patch(patch, {'x':'a\nb\nc\n'}), {'x':'a\nB\nc\n'})
        for bad in [patch.replace('-b','-a'),patch.replace('+2 @@','+3 @@'),patch.replace('a/x b/x','a/y b/x')]:
            with self.assertRaises(ValueError):
                apply_patch(bad, {'x':'a\nb\nc\n'})

    def test_git_lf_framing_preserves_payload_bytes(self):
        prefix = 'diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n'
        for before, after, body in [
            ('a\n', 'b', '-a\n+b\n\\ No newline at end of file\n'),
            ('a', 'b\n', '-a\n\\ No newline at end of file\n+b\n'),
            ('a', 'b', '-a\n\\ No newline at end of file\n+b\n\\ No newline at end of file\n'),
            ('a\n', 'b\r\n', '-a\n+b\r\n'),
            ('a\f1\n', 'b\x851\n', '-a\f1\n+b\x851\n'),
        ]:
            with self.subTest(before=before, after=after):
                self.assertEqual(apply_patch(prefix + body, {'x': before}), {'x': after})

    def test_uniform_crlf_transport_preserves_crlf_payload(self):
        patch = 'diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\r\n'
        self.assertEqual(apply_patch(patch.replace('\n', '\r\n'), {'x': 'a\n'}), {'x': 'b\r\n'})
        mixed = patch.replace(' b/x\n', ' b/x\r\n', 1)
        with self.assertRaises(ValueError):
            apply_patch(mixed, {'x': 'a\n'})

    def test_missing_newline_context_has_to_be_at_end(self):
        prefix = 'diff --git a/x b/x\n--- a/x\n+++ b/x\n'
        marker = '\\ No newline at end of file\n'
        patch = prefix + '@@ -1,2 +1,2 @@\n-a\n+b\n z\n' + marker
        self.assertEqual(apply_patch(patch, {'x': 'a\nz'}), {'x': 'b\nz'})
        for body in [
            '@@ -1 +1 @@\n-a\n+b\n' + marker,
            '@@ -1 +1 @@\n-a\n+b\n' + marker + marker,
            '@@ -1 +1 @@\n' + marker + '-a\n+b\n',
            '@@ -1 +1 @@\n-a\n+b',
        ]:
            with self.subTest(body=body), self.assertRaises(ValueError):
                apply_patch(prefix + body, {'x': 'a\nz\n'})

    def test_sql_comment_and_spacing_select_readers(self):
        for old,new in [('-- abc','-- def'),('SELECT 1','SELECT   1')]:
            path='tests/fixtures/example.sql'
            p=f'diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n-{old}\n+{new}\n'
            data={'sources':{path:old+'\n'},'hits':{path:[0]},'ids':['one','two']}
            self.assertEqual(decide(p,data), ({'one'}, 'observed'))
            for readers in ([], [-1]):
                data['hits'][path] = readers
                self.assertIsNone(decide(p,data)[0])

    def test_missing_shared_and_unobserved_evidence(self):
        path = 'sqlglot/toy.py'
        patch = f'diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n-def f(): return 1\n+def f(): return 2\n'
        data = {'ids':['a','b','c'], 'sources':{path:'def f(): return 1\n'}, 'hits':{}}
        self.assertEqual(decide(patch, None), (None,'catalog'))
        self.assertEqual(decide(patch, data), (None,'unobserved_scope'))
        data['hits'][path+'::f'] = [-1]
        self.assertEqual(decide(patch, data), (None,'shared_or_missing'))
        data['hits'][path+'::f'] = [1]
        data['hits']['!untraced'] = [0]
        self.assertEqual(decide(patch, data), ({'a','b'},'observed'))
        data['hits'][path+'::@importers'] = [2]
        self.assertEqual(decide(patch, data)[0], {'a','b','c'})


class FixtureComments(unittest.TestCase):
    path = 'tests/fixtures/example.sql'

    def decide(self, old, new):
        path = self.path
        patch = f'diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1,3 +1,3 @@\n {old[0]}\n-{old[1]}\n+{new}\n {old[2]}\n'
        data = {'sources': {path: '\n'.join(old) + '\n'}, 'hits': {path: [0]}, 'ids': ['one', 'two']}
        return decide(patch, data)

    def test_code_edit_outside_block_comments_selects_readers(self):
        self.assertEqual(self.decide(['/* header */', 'SELECT 1;', '/* footer */'], 'SELECT 2;'), ({'one'}, 'observed'))

    def test_comment_edits_select_readers(self):
        cases = [(['/* a', 'b', 'c */'], 'B'), (['/* a */', 'SELECT 1;', 'x'], 'SELECT 1; /* note */'),
                 (['/* a */', 'SELECT 1; -- one', 'x'], 'SELECT 1; -- two'), (['/* a */', 'SELECT 1;', 'x'], 'SELECT 1; */'),
                 (['x', 'SELECT 1; -- c', '*/'], 'SELECT 1; -- c /*'), (['/* open', 'SELECT 1;', 'x'], 'SELECT 2;')]
        for old, new in cases:
            with self.subTest(old=old, new=new):
                self.assertEqual(self.decide(old, new), ({'one'}, 'observed'))


def git_patch(changes):
    import difflib
    from io import StringIO
    out = []
    for path, (old, new) in changes.items():
        out.append(f'diff --git a/{path} b/{path}\n')
        out.extend(difflib.unified_diff(StringIO(old).readlines(), StringIO(new).readlines(), 'a/' + path, 'b/' + path))
    return ''.join(out)


class GeneratorOverride(unittest.TestCase):
    PATH = 'sqlglot/generators/toy.py'
    BASE = 'sqlglot/generator.py'
    OLD = 'from sqlglot import generator\n\nclass Toy(generator.Generator):\n    CONFIG = True\n'
    METHOD = '    def select_sql(self, expression):\n        return "SELECT 0"\n'

    def data(self):
        cls, base = self.PATH + '::Toy', self.BASE + '::Generator'
        return {
            'sources': {self.PATH: self.OLD, self.BASE: 'class Generator:\n    def select_sql(self, expression):\n        return ""\n'},
            'ids': ['receiver', 'reader', 'other', 'importer'],
            'hits': {self.PATH: [1], self.PATH + '::@importers': [3]},
            'classes': {'M': {cls: [base], base: []}, 'R': {cls: [0]}, 'I': {}, 'W': []},
        }

    def test_pure_override_keeps_receivers_readers_and_importers(self):
        patch = git_patch({self.PATH: (self.OLD, self.OLD + self.METHOD)})
        self.assertEqual(decide(patch, self.data()), ({'receiver', 'reader', 'importer'}, 'generator_override'))

    def test_module_import_read_through_class_or_ancestor_keeps_full_suite(self):
        patch = git_patch({self.PATH: (self.OLD, self.OLD + self.METHOD)})
        cls = self.PATH + '::Toy'
        base = self.BASE + '::Generator'
        for key in (cls + '@__dict__', base + '@select_sql', base + '@where_sql'):
            data = self.data()
            data['classes']['I'][key] = ['<module>']
            method = self.METHOD.replace('select_sql', 'where_sql') if 'where' in key else self.METHOD
            self.assertIsNone(decide(git_patch({self.PATH: (self.OLD, self.OLD + method)}), data)[0])

    def test_subclass_receivers_join_the_selection(self):
        data = self.data()
        data['classes']['M']['other::Child'] = [self.PATH + '::Toy']
        data['classes']['R']['other::Child'] = [2]
        patch = git_patch({self.PATH: (self.OLD, self.OLD + self.METHOD)})
        self.assertEqual(decide(patch, data), ({'receiver', 'reader', 'other', 'importer'}, 'structure'))

    def test_import_consumer_of_ancestor_name_joins_the_selection(self):
        data = self.data()
        data['classes']['M']['other::Holder'] = []
        data['classes']['R']['other::Holder'] = [2]
        data['classes']['I'][self.BASE + '::Generator@select_sql'] = ['other::Holder']
        patch = git_patch({self.PATH: (self.OLD, self.OLD + self.METHOD)})
        self.assertEqual(decide(patch, data), ({'receiver', 'reader', 'other', 'importer'}, 'structure'))

    def test_runtime_class_write_keeps_full_suite(self):
        patch = git_patch({self.PATH: (self.OLD, self.OLD + self.METHOD)})
        data = self.data()
        data['classes']['W'].append(self.PATH + '::Toy@select_sql')
        self.assertIsNone(decide(patch, data)[0])

    def test_other_members_select_class_receivers(self):
        middle = self.OLD.replace('    CONFIG = True\n', self.METHOD + '    CONFIG = True\n')
        for new in (middle, self.OLD + self.METHOD.replace('select_sql', 'where_sql'),
                    self.OLD + self.METHOD.replace('"SELECT 0"', 'other()'),
                    self.OLD + self.METHOD.replace('expression)', 'expression=None)'),
                    self.OLD + '    @staticmethod\n' + self.METHOD):
            with self.subTest(new=new):
                patch = git_patch({self.PATH: (self.OLD, new)})
                self.assertEqual(decide(patch, self.data()), ({'receiver', 'reader', 'importer'}, 'structure'))

    def test_unsafe_members_keep_full_suite(self):
        for method in ('    @register\n' + self.METHOD, self.METHOD.replace('expression)', 'expression=make())'),
                       self.METHOD.replace('select_sql', '__eq__')):
            with self.subTest(method=method):
                patch = git_patch({self.PATH: (self.OLD, self.OLD + method)})
                self.assertIsNone(decide(patch, self.data())[0])


class CommentOnly(unittest.TestCase):
    A, B = 'sqlglot/a.py', 'sqlglot/b.py'
    OLD_A = 'import os\n\n\ndef f():\n    """Doc."""\n    return "a"\n\n\nX = "x"\n'
    OLD_B = 'def g():\n    return 1\n'

    def data(self, **extra):
        hits = {'!untraced': [0], self.A + '::f': [1], self.B + '::g': [2]}
        hits.update(extra)
        return {'ids': ['t0', 't1', 't2', 't3', 't4'], 'sources': {self.A: self.OLD_A, self.B: self.OLD_B}, 'hits': hits}

    def decide_a(self, new, data=None):
        return decide(git_patch({self.A: (self.OLD_A, new)}), data or self.data())

    def test_comment_on_line_one_selects_readers_and_untraced(self):
        new = '# note\n' + self.OLD_A
        self.assertEqual(self.decide_a(new), ({'t0'}, 'comment_only'))
        self.assertEqual(self.decide_a(new, self.data(**{self.A: [3]})), ({'t0', 't3'}, 'comment_only'))

    def test_comment_inside_function(self):
        new = self.OLD_A.replace('    return "a"', '    # inner\n    return "a"  # trailing')
        self.assertEqual(self.decide_a(new, self.data(**{self.A: [3]})), ({'t0', 't3'}, 'comment_only'))

    def test_multi_file_comment_does_not_force_fallback(self):
        patch = git_patch({self.A: (self.OLD_A, '# note\n' + self.OLD_A),
                           self.B: (self.OLD_B, self.OLD_B.replace('1', '2'))})
        self.assertEqual(decide(patch, self.data(**{self.A: [3]})), ({'t0', 't2', 't3'}, 'observed'))
        unobserved = self.data()
        del unobserved['hits'][self.B + '::g']
        self.assertEqual(decide(patch, unobserved), (None, 'unobserved_scope'))

    def test_hash_inside_strings_is_code(self):
        self.assertEqual(self.decide_a(self.OLD_A.replace('return "a"', 'return "a # b"')), ({'t0', 't1'}, 'observed'))
        # Docstring text is observable only through source readers, like a comment.
        self.assertEqual(self.decide_a(self.OLD_A.replace('"""Doc."""', '"""Doc. # b"""')), ({'t0'}, 'comment_only'))
        self.assertIsNone(self.decide_a(self.OLD_A.replace('    """Doc."""\n', ''))[0])
        self.assertEqual(self.decide_a(self.OLD_A.replace('X = "x"', 'X = "x # y"')), (None, 'structural_or_text'))

    def test_all_comment_only_without_evidence_selects_nothing(self):
        data = self.data()
        data['hits']['!untraced'] = []
        self.assertEqual(self.decide_a('# note\n' + self.OLD_A, data), (set(), 'comment_only'))

    def test_shared_reader_falls_back(self):
        self.assertEqual(self.decide_a('# note\n' + self.OLD_A, self.data(**{self.A: [-1]})), (None, 'shared_or_missing'))

    def test_encoding_cookie_falls_back(self):
        for new in ['# -*- coding: latin-1 -*-\n' + self.OLD_A, '#!/usr/bin/env python\n# vim: set fileencoding=utf-8\n' + self.OLD_A,
                    '# a\x0cb\n# coding: latin-1\n' + self.OLD_A, '# a\x85b\n# coding: latin-1\n' + self.OLD_A]:
            with self.subTest(new=new[:30]):
                self.assertEqual(self.decide_a(new), (None, 'encoding_cookie'))
        data = self.data()
        data['sources'][self.A] = 'import os\n# coding=utf-8\n' + self.OLD_A[len('import os\n'):]
        patch = git_patch({self.A: (data['sources'][self.A], data['sources'][self.A] + '# tail\n')})
        self.assertEqual(decide(patch, data), (None, 'encoding_cookie'))

    def test_reconstruction_failure_falls_back(self):
        patch = git_patch({self.A: (self.OLD_A.replace('os', 'sys'), '# note\n' + self.OLD_A.replace('os', 'sys'))})
        self.assertEqual(decide(patch, self.data()), (None, 'unsupported_diff'))


class Structure(unittest.TestCase):
    PATH, HELPER = 'sqlglot/toys/widget.py', 'sqlglot/toys/helpers.py'
    OLD = ('from __future__ import annotations\n\nfrom sqlglot.toys.helpers import mark, register\n\n\n'
           'def build(value, flag=False):\n    return value\n\n\nclass Widget:\n    def run(self, x=1):\n        return x\n')
    HELPERS = ('from functools import wraps\n\nREGISTRY = []\n\n\ndef mark(*names):\n    seen = {}\n'
               '    for name in names:\n        seen[name] = None\n\n    def decorator(func):\n        @wraps(func)\n'
               '        def inner(self, e):\n            self.note(seen)\n            return func(self, e)\n\n'
               '        return inner\n\n    return decorator\n\n\ndef register(func):\n    REGISTRY.append(func)\n    return func\n')

    def data(self):
        cls = self.PATH + '::Widget'
        return {'ids': ['t0', 't1', 't2', 't3', 't4'], 'sources': {self.PATH: self.OLD, self.HELPER: self.HELPERS},
                'hits': {'!untraced': [0], self.PATH + '::build': [1], self.PATH + '::Widget.run': [2]},
                'classes': {'M': {cls: []}, 'R': {cls: [3]}, 'I': {}, 'W': []}}

    def run_patch(self, new, data=None):
        return decide(git_patch({self.PATH: (self.OLD, new)}), data or self.data())

    def test_literal_default_edits_select_callers(self):
        self.assertEqual(self.run_patch(self.OLD.replace('flag=False', 'flag=True')), ({'t0', 't1'}, 'structure'))
        self.assertEqual(self.run_patch(self.OLD.replace('x=1', 'x=2')), ({'t0', 't2'}, 'structure'))
        self.assertEqual(self.run_patch(self.OLD.replace('flag=False)', 'flag=False, extra=None)')), ({'t0', 't1'}, 'structure'))

    def test_unsafe_header_edits_keep_full_suite(self):
        for old, new in [('flag=False', 'flag=make()'), ('def build(', '@mark("a")\ndef build('),
                         ('from __future__ import annotations\n\n', '')]:
            with self.subTest(new=new):
                self.assertIsNone(self.run_patch(self.OLD.replace(old, new))[0])
        data = self.data()
        data['hits'][self.PATH + '::build'] = [-1]
        self.assertIsNone(self.run_patch(self.OLD.replace('flag=False', 'flag=True'), data)[0])

    def test_pure_decorated_member_selects_receivers(self):
        method = '\n    @mark("a", ("b", "why"))\n    def other(self, e):\n        return e\n'
        self.assertEqual(self.run_patch(self.OLD + method), ({'t0', 't3'}, 'structure'))
        for decorator in ('@register', '@mark(make())', '@unknown'):
            with self.subTest(decorator=decorator):
                self.assertIsNone(self.run_patch(self.OLD + method.replace('@mark("a", ("b", "why"))', decorator))[0])


class TestModules(unittest.TestCase):
    PATH, HELPER = 'tests/test_toy.py', 'tests/helpers.py'
    OLD = ('import unittest\nfrom tests.helpers import load\n\nSTATE = {}\n\n\nclass TestToy(unittest.TestCase):\n'
           '    def check(self, x):\n        return x\n\n    def test_a(self):\n        value = {"x": 1}\n        value["x"] = 2\n'
           '        self.assertEqual(value["x"], 2)\n\n    def test_b(self):\n        self.assertTrue(self.check(1))\n')
    IDS = ['tests/test_toy.py::TestToy::test_a', 'tests/test_toy.py::TestToy::test_b',
           'tests/test_other.py::TestOther::test_c', 'tests/test_far.py::TestFar::test_d']

    def data(self, importers=()):
        return {'ids': self.IDS, 'sources': {}, 'hits': {'!untraced': []},
                'test_evidence': {'sources': {self.PATH: self.OLD, self.HELPER: 'def load():\n    return 1\n',
                                              'tests/conftest.py': 'X = 1\n'},
                                  'importers': {self.PATH: list(importers), self.HELPER: ['tests/test_toy.py']}}}

    def run_patch(self, new, data=None, path=None):
        path = path or self.PATH
        old = (data or self.data())['test_evidence']['sources'][path]
        return decide(git_patch({path: (old, new)}), data or self.data())

    def test_test_method_body_selects_that_test(self):
        self.assertEqual(self.run_patch(self.OLD.replace('value["x"] = 2', 'value["x"] = 3')),
                         ({self.IDS[0]}, 'test_method'))
        data = self.data(importers=['tests/test_other.py'])
        self.assertEqual(self.run_patch(self.OLD.replace('value["x"] = 2', 'value["x"] = 3'), data),
                         ({self.IDS[0], self.IDS[2]}, 'test_method'))

    def test_helpers_and_module_level_edits_select_the_module(self):
        self.assertEqual(self.run_patch(self.OLD.replace('return x', 'return not x')), (set(self.IDS[:2]), 'test_module'))
        self.assertEqual(self.run_patch(self.OLD.replace('STATE = {}', 'STATE = {1: 2}')), (set(self.IDS[:2]), 'test_module'))
        self.assertEqual(self.run_patch('def load():\n    return 2\n', path=self.HELPER), (set(self.IDS[:2]), 'test_module'))
        self.assertEqual(self.run_patch(self.OLD.replace('def test_b', 'def test_b(self:'))[0], set(self.IDS[:2]))

    def test_shared_state_and_collection_files_keep_full_suite(self):
        for old, new in [('value["x"] = 2', 'STATE["x"] = 2'), ('value["x"] = 2', 'unittest.mock = None'),
                         ('value["x"] = 2', 'STATE.update(x=2)'), ('STATE = {}', 'STATE = {}\nload.cache = 1')]:
            with self.subTest(new=new):
                self.assertEqual(self.run_patch(self.OLD.replace(old, new)), (None, 'test_state'))
        self.assertEqual(self.run_patch('X = 2\n', path='tests/conftest.py'), (None, 'test_structure'))


class ModuleBindings(unittest.TestCase):
    PATH, OTHER, LIB = 'sqlglot/toys/fmt.py', 'sqlglot/toys/user.py', 'sqlglot/toys/lib.py'
    OLD = ('from sqlglot.toys.lib import first, second\n\nLIMIT = 3\n\n\ndef render(x):\n    return first(x)[:LIMIT]\n\n\n'
           'def other(x):\n    return second(x)\n')
    LIB_SOURCE = 'def first(x):\n    return x\n\n\ndef second(x):\n    return x\n'
    USER = 'from sqlglot.toys.fmt import LIMIT\n\n\ndef use():\n    return LIMIT\n'

    def data(self, user=None, tests=None):
        sources = {self.PATH: self.OLD, self.LIB: self.LIB_SOURCE}
        if user:
            sources[self.OTHER] = user
        return {'ids': ['t0', 't1', 't2', 'tests/test_fmt.py::T::test_x', 'tests/test_fmt.py::T::test_y'],
                'sources': sources,
                'hits': {'!untraced': [0], self.PATH + '::render': [1], self.PATH + '::other': [2],
                         self.OTHER + '::use': [2]},
                'test_evidence': {'sources': tests or {}, 'importers': {}}}

    def run_patch(self, new, data=None):
        return decide(git_patch({self.PATH: (self.OLD, new)}), data or self.data())

    def test_literal_and_import_bindings_select_runtime_readers(self):
        self.assertEqual(self.run_patch(self.OLD.replace('LIMIT = 3', 'LIMIT = 4')), ({'t0', 't1'}, 'module_binding'))
        # second is no longer bound, so its reader fails too.
        new = self.OLD.replace('import first, second', 'import first, second as first')
        self.assertEqual(self.run_patch(new), ({'t0', 't1', 't2'}, 'module_binding'))
        new = self.OLD.replace('import first, second', 'import second as first, second')
        self.assertEqual(self.run_patch(new), ({'t0', 't1'}, 'module_binding'))

    def test_copies_in_other_modules_are_followed_once(self):
        self.assertEqual(self.run_patch(self.OLD.replace('LIMIT = 3', 'LIMIT = 4'), self.data(user=self.USER)),
                         ({'t0', 't1', 't2'}, 'module_binding'))
        tests = {'tests/test_fmt.py': 'from sqlglot.toys.fmt import LIMIT\n'}
        self.assertEqual(self.run_patch(self.OLD.replace('LIMIT = 3', 'LIMIT = 4'), self.data(tests=tests))[0],
                         {'t0', 't1', 'tests/test_fmt.py::T::test_x', 'tests/test_fmt.py::T::test_y'})

    def test_unbounded_bindings_keep_full_suite(self):
        cases = [(self.OLD.replace('LIMIT = 3', 'LIMIT = "3"'), None),
                 (self.OLD.replace('LIMIT = 3', 'LIMIT = 3\nCACHE = LIMIT').replace('LIMIT = 3\n', 'LIMIT = 4\n', 1), None),
                 (self.OLD.replace('import first, second', 'import first, missing'), None),
                 (self.OLD.replace('LIMIT = 3', 'LIMIT = 4'), self.data(user='from sqlglot.toys.fmt import *\n')),
                 (self.OLD.replace('LIMIT = 3', 'LIMIT = 4'), self.data(user='from sqlglot.toys import fmt\nX = fmt.LIMIT\n'))]
        for new, data in cases:
            with self.subTest(new=new[:60]):
                self.assertIsNone(self.run_patch(new, data)[0])
        data = self.data()
        data['hits'][self.PATH + '::render'] = [-1]
        self.assertIsNone(self.run_patch(self.OLD.replace('LIMIT = 3', 'LIMIT = 4'), data)[0])


class NamespaceReflection(unittest.TestCase):
    def test_only_own_namespace_access_counts(self):
        import ast
        from hybrid import _reflects_namespace
        for source, expected in [('def f(o):\n    return getattr(o, "x")\n', False), ('X = globals()\n', True),
                                 ('def f():\n    return vars()\n', True), ('def f(o):\n    return vars(o)\n', False),
                                 ('import sys\nM = sys.modules[__name__]\n', True), ('m = __import__("a")\n', True)]:
            with self.subTest(source=source):
                self.assertEqual(_reflects_namespace(ast.parse(source)), expected)
