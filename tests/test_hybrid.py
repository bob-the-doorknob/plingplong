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

    def test_sql_comment_and_spacing_fall_back(self):
        for old,new in [('-- abc','-- def'),('SELECT 1','SELECT   1')]:
            path='tests/fixtures/example.sql'
            p=f'diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n-{old}\n+{new}\n'
            data={'sources':{path:old+'\n'},'hits':{path:[0]},'ids':['one','two']}
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

    def test_comment_edits_with_block_comments_fall_back(self):
        cases = [(['/* a', 'b', 'c */'], 'B'), (['/* a */', 'SELECT 1;', 'x'], 'SELECT 1; /* note */'),
                 (['/* a */', 'SELECT 1; -- one', 'x'], 'SELECT 1; -- two'), (['/* a */', 'SELECT 1;', 'x'], 'SELECT 1; */'),
                 (['x', 'SELECT 1; -- c', '*/'], 'SELECT 1; -- c /*'), (['/* open', 'SELECT 1;', 'x'], 'SELECT 2;')]
        for old, new in cases:
            with self.subTest(old=old, new=new):
                self.assertIsNone(self.decide(old, new)[0])


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

    def test_observed_import_or_subclass_keeps_full_suite(self):
        patch = git_patch({self.PATH: (self.OLD, self.OLD + self.METHOD)})
        cls = self.PATH + '::Toy'
        base = self.BASE + '::Generator'
        for key in (cls + '@__dict__', base + '@select_sql'):
            data = self.data()
            data['classes']['I'][key] = ['<module>']
            self.assertIsNone(decide(patch, data)[0])
        data = self.data()
        data['classes']['M']['other::Child'] = [cls]
        self.assertIsNone(decide(patch, data)[0])

    def test_mutation_and_edits_before_end_keep_full_suite(self):
        patch = git_patch({self.PATH: (self.OLD, self.OLD + self.METHOD)})
        data = self.data()
        data['classes']['W'].append(self.PATH + '::Toy@select_sql')
        self.assertIsNone(decide(patch, data)[0])
        middle = self.OLD.replace('    CONFIG = True\n', self.METHOD + '    CONFIG = True\n')
        patch = git_patch({self.PATH: (self.OLD, middle)})
        self.assertIsNone(decide(patch, self.data())[0])

    def test_unknown_bindings_and_nonliteral_bodies_keep_full_suite(self):
        for method in (self.METHOD.replace('select_sql', 'where_sql'),
                       self.METHOD.replace('"SELECT 0"', 'other()'),
                       self.METHOD.replace('expression)', 'expression=None)'),
                       '    @staticmethod\n' + self.METHOD):
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
        self.assertEqual(self.decide_a(self.OLD_A.replace('"""Doc."""', '"""Doc. # b"""'))[0], None)
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
