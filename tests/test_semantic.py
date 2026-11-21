"""AST locality is evidence about syntax, never a proof of unobservability."""
import unittest
from semantic import classify_change


class SemanticTests(unittest.TestCase):
    def test_function_body(self):
        result = classify_change('def f():\n return 1\n','def f():\n return 2\n')
        self.assertEqual(result['functions'], ['f'])
        self.assertFalse(result['structural'])

    def test_method_body(self):
        result = classify_change('class C:\n def f(self):\n  return 1\n','class C:\n def f(self):\n  return 2\n')
        self.assertEqual(result['functions'], ['C.f'])
        self.assertFalse(result['structural'])

    def test_definition_time_changes(self):
        pairs = [('def f(x=1):\n pass','def f(x=2):\n pass'), ('@one\ndef f():\n pass','@two\ndef f():\n pass'), ('class C(A):\n pass','class C(B):\n pass'), ('class C:\n x=1','class C:\n x=2'), ('import one','import two'), ('x=1','x=2')]
        for old,new in pairs:
            with self.subTest(old=old):
                self.assertTrue(classify_change(old,new)['structural'])

    def test_added_removed_renamed_functions(self):
        for old,new in [('', 'def f():\n pass'), ('def f():\n pass',''), ('def f():\n pass','def g():\n pass')]:
            self.assertTrue(classify_change(old,new)['structural'])

    def test_comments_are_textually_observable(self):
        result = classify_change('x=1 # old','x=1 # new')
        self.assertTrue(result['text_changed'])
        self.assertTrue(result['ast_equal'])
        self.assertEqual(result['functions'], [])

    def test_invalid_python_requires_fallback(self):
        result = classify_change('x=1','def !!!')
        self.assertEqual(result['reason'], 'parse_error')
        self.assertTrue(result['structural'])

    def test_duplicate_definitions_require_fallback(self):
        old = 'def f():\n pass\ndef f():\n pass'
        self.assertEqual(classify_change(old,old+'\n')['reason'], 'duplicate_scope')

    def test_nested_function_attributes_module_scope(self):
        result=classify_change('if True:\n def f():\n  return 1','if True:\n def f():\n  return 2')
        self.assertTrue(result['structural'])

    def test_nested_function_attributed_to_outer(self):
        result=classify_change('def f():\n def g():\n  return 1','def f():\n def g():\n  return 2')
        self.assertEqual(result['functions'], ['f'])

    def test_async_and_order_are_deterministic(self):
        old='async def z():\n return 1\ndef a():\n return 1'
        result=classify_change(old,old.replace('return 1','return 2'))
        self.assertEqual(result['functions'], ['a','z'])

    def test_unrelated_overload_does_not_hide_unique_scope(self):
        old = 'def f(): pass\ndef f(): pass\ndef g(): return 1'
        result = classify_change(old, old.replace('return 1','return 2'))
        self.assertFalse(result['structural'])
        self.assertEqual(result['functions'], ['g'])

    def test_observable_function_metadata(self):
        for old,new in [('return 1', 'yield 1'), ('"doc"', '"other"')]:
            self.assertTrue(classify_change('def f(): '+old, 'def f(): '+new)['structural'])
