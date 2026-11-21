import unittest
from hybrid import apply_patch, decide

class Reconstruction(unittest.TestCase):
    def test_context_and_new_coordinates(self):
        patch = 'diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -2 +2 @@\n-b\n+B\n'
        self.assertEqual(apply_patch(patch, {'x':'a\nb\nc\n'}), {'x':'a\nB\nc\n'})
        for bad in [patch.replace('-b','-a'),patch.replace('+2 @@','+3 @@'),patch.replace('a/x b/x','a/y b/x')]:
            with self.assertRaises(ValueError):
                apply_patch(bad, {'x':'a\nb\nc\n'})

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
