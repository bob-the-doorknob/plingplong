"""Tests for literal changes whose effects are confined to numeric decoding."""
import unittest

from numeric import numeric_radix_edit


class NumericRadixEdit(unittest.TestCase):
    OLD = '''class Demo:
    class Tokenizer:
        NUMERIC_ESCAPES = {"u": (16, 4, 4, 0xFFFF), "x": (16, 2, 2, 255)}
'''

    def test_single_valid_radix_edit(self):
        new = self.OLD.replace('(16, 4, 4', '(17, 4, 4')
        self.assertTrue(numeric_radix_edit(self.OLD, new, 'Demo.Tokenizer'))

    def test_keeps_existing_fallback_for_changed_keys_bounds_and_expressions(self):
        for new in (
                self.OLD.replace('"u"', '"U"'),
                self.OLD.replace('(16, 4, 4', '(37, 4, 4'),
                self.OLD.replace('(16, 4, 4', '(False, 4, 4'),
                self.OLD.replace('(16, 4, 4', '(16, 3, 4'),
                self.OLD.replace('(16, 4, 4', '(base(), 4, 4'),
                self.OLD.replace('16', '17'),
        ):
            with self.subTest(new=new):
                self.assertFalse(numeric_radix_edit(self.OLD, new, 'Demo.Tokenizer'))

    def test_numeric_narrowing_keeps_generic_readers_and_requires_decoder_hits(self):
        from hybrid import numeric_escape_tests
        from numeric import DECODER

        path = 'sqlglot/dialects/example.py'
        cls = path + '::Demo.Tokenizer'
        change = {'cls': 'Demo.Tokenizer', 'attr': 'NUMERIC_ESCAPES', 'body_read': False}
        decoder = """class TokenizerCore:
    def one(self, key):
        return self.numeric_escapes.get(key)
    def two(self, key):
        return self.numeric_escapes.get(key)
"""
        data = {
            'sources': {DECODER: decoder},
            'hits': {},
            'classes': {
                'M': {cls: ['sqlglot/tokens.py::Tokenizer']},
                'I': {cls + '@NUMERIC_ESCAPES': [path + '::Demo']},
                'W': [],
                'A': {cls + '@__dict__': [2]},
            },
            'line_evidence': {'files': {DECODER: {'3': 0}}, 'extra': [0], 'groups': [[1]]},
        }
        new = self.OLD.replace('(16, 4, 4', '(17, 4, 4')
        self.assertEqual(numeric_escape_tests(data, path, self.OLD, new, change), {0, 1, 2})
        data['classes']['I'][cls + '@NUMERIC_ESCAPES'].append('<module>')
        self.assertIsNone(numeric_escape_tests(data, path, self.OLD, new, change))
        data['classes'].pop('_index', None)
        data['classes']['I'][cls + '@NUMERIC_ESCAPES'].pop()
        data['line_evidence']['groups'][0] = [-1]
        self.assertIsNone(numeric_escape_tests(data, path, self.OLD, new, change))

    def test_week_offsets_require_an_in_range_literal_with_stable_truthiness(self):
        from numeric import week_offset_edit
        old = 'class Demo:\n    WEEK_OFFSET = -1\n'
        self.assertTrue(week_offset_edit(old, old.replace('-1', '3'), 'Demo'))
        for invalid in ('0', '7', '-7', 'True', 'parse(2)', '1 + 2'):
            self.assertFalse(week_offset_edit(old, old.replace('-1',invalid), 'Demo'))
