"""Class-level attribute edits select tests through recorded attribute reads."""
import copy
import difflib
import unittest

from hybrid import decide, tests_of
from semantic import classify_change


def git_patch(changes):
    out = []
    for path, (old, new) in changes.items():
        out.append(f'diff --git a/{path} b/{path}\n')
        out.extend(difflib.unified_diff(old.splitlines(True), new.splitlines(True), 'a/' + path, 'b/' + path))
    return ''.join(out)

PATH = 'sqlglot/toys/widget.py'
OLD = '''from sqlglot.toys.base import Base, make, build


class Widget(Base):
    SETTING = 1
    MAPPING = {"a": make(flag=True), "b": make(flag=False)}
    SOURCE = (1, 2)
    TRIE = build(SOURCE)

    class Part:
        VALUE = 1

    def method(self):
        return self.SETTING


LIMIT = 3
'''
WIDGET, PART = PATH + '::Widget', PATH + '::Widget.Part'
CUSTOM, OTHER = 'tests/test_widget.py::Custom', 'sqlglot/toys/other.py::Other'
IDS = ['tests/test_widget.py::TestWidget::test_' + c for c in 'abcdefghij']
EVIDENCE = {
    'M': {WIDGET: ['sqlglot/toys/base.py::Base'], PART: [], CUSTOM: [WIDGET], OTHER: []},
    'R': {WIDGET: [1, 2], CUSTOM: [3], OTHER: [5]},
    'A': {WIDGET + '@SETTING': [2], WIDGET + '@MAPPING': [6], WIDGET + '@SOURCE': [7]},
    'I': {}, 'W': [], 'K': [],
}


def data(**changes):
    evidence = copy.deepcopy(EVIDENCE)
    for key, value in changes.items():
        evidence[key] = value if not isinstance(value, dict) else {**evidence[key], **value}
    return {'ids': IDS, 'sources': {PATH: OLD}, 'classes': evidence,
            'hits': {'!untraced': [0], PATH + '::Widget.method': [8]}}


def run(new, evidence=None, path=PATH):
    source = evidence or data()
    if path != PATH:
        source['sources'] = {path: OLD}
    return decide(git_patch({path: (OLD, new)}), source)


def names(*indexes):
    return {IDS[i] for i in indexes}


class Detection(unittest.TestCase):
    def test_value_changes_are_located(self):
        cases = [('SETTING = 1', 'SETTING = 2', 'Widget', 'SETTING', False),
                 ('"b": make(flag=False)', '"b": make(flag=True)', 'Widget', 'MAPPING', False),
                 ('VALUE = 1', 'VALUE = 9', 'Widget.Part', 'VALUE', False),
                 ('SOURCE = (1, 2)', 'SOURCE = (2, 1)', 'Widget', 'SOURCE', True)]
        for old, new, cls, attr, body_read in cases:
            with self.subTest(old=old):
                result = classify_change(OLD, OLD.replace(old, new))
                self.assertTrue(result['structural'])
                self.assertEqual(result['class_attributes'], [dict(cls=cls, attr=attr, body_read=body_read)])

    def test_other_structural_edits_are_not_attribute_values(self):
        cases = [('SETTING = 1', 'RENAMED = 1'), ('SETTING = 1', 'SETTING = 1\n    EXTRA = 2'),
                 ('class Widget(Base):', 'class Widget(Base, Mixin):'),
                 ('class Widget(Base):', '@decorate\nclass Widget(Base):'),
                 ('class Widget(Base):', 'class Widget(Base, metaclass=Meta):'),
                 ('LIMIT = 3', 'LIMIT = 4'), ('SETTING = 1', 'SETTING: int = 1'),
                 ('SETTING = 1', 'SETTING = 1\n    SETTING = 2'), ('def method(self):', 'def method(self, x=1):')]
        for old, new in cases:
            with self.subTest(new=new):
                result = classify_change(OLD, OLD.replace(old, new))
                self.assertTrue(result['structural'])
                self.assertIsNone(result['class_attributes'])


    def test_duplicate_methods_do_not_hide_attribute_edits(self):
        old = OLD.replace('    def method(self):', '    def method(self):\n        pass\n\n    def method(self):')
        result = classify_change(old, old.replace('SETTING = 1', 'SETTING = 2'))
        self.assertEqual(result['class_attributes'], [dict(cls='Widget', attr='SETTING', body_read=False)])
        twice = OLD + 'class Widget(Base):\n    SETTING = 1\n'
        result = classify_change(twice, twice.replace('SETTING = 1', 'SETTING = 2', 1))
        self.assertEqual((result['reason'], result.get('class_attributes')), ('duplicate_scope', None))

class Selection(unittest.TestCase):
    def test_b_runtime_readers_of_the_attribute(self):
        self.assertEqual(run(OLD.replace('SETTING = 1', 'SETTING = 2')), (names(0, 2), 'observed'))

    def test_b_class_level_dict_call_argument(self):
        new = OLD.replace('"b": make(flag=False)', '"b": make(flag=True)')
        self.assertEqual(run(new), (names(0, 6), 'observed'))

    def test_b_combines_with_function_body_changes(self):
        new = OLD.replace('SETTING = 1', 'SETTING = 2').replace('return self.SETTING', 'return -self.SETTING')
        self.assertEqual(run(new), (names(0, 2, 8), 'observed'))

    def test_a_import_read_selects_class_and_subclass_receivers(self):
        evidence = data(I={WIDGET + '@SETTING': [WIDGET]})
        self.assertEqual(run(OLD.replace('SETTING = 1', 'SETTING = 2'), evidence), (names(0, 1, 2, 3), 'observed'))

    def test_a_inherited_reads_through_a_subclass(self):
        # A subclass reading the inherited attribute at import time holds derived state.
        evidence = data(I={WIDGET + '@SETTING': [CUSTOM]})
        self.assertEqual(run(OLD.replace('SETTING = 1', 'SETTING = 2'), evidence), (names(0, 1, 2, 3), 'observed'))

    def test_a_body_read_and_consumer_closure(self):
        evidence = data(I={WIDGET + '@TRIE': [OTHER]})
        self.assertEqual(run(OLD.replace('SOURCE = (1, 2)', 'SOURCE = (2, 1)'), evidence), (names(0, 1, 2, 3, 5), 'observed'))

    def test_a_cache_or_runtime_write_escalates(self):
        new = OLD.replace('SETTING = 1', 'SETTING = 2')
        for evidence in [data(K=[WIDGET + '@SETTING']), data(W=[CUSTOM + '@SETTING']), data(K=[WIDGET + '@__dict__'])]:
            with self.subTest(evidence=evidence['classes']['K'] or evidence['classes']['W']):
                self.assertEqual(run(new, evidence), (names(0, 1, 2, 3), 'observed'))

    def test_a_module_level_import_read_falls_back(self):
        for key in ['@SETTING', '@__dict__']:
            evidence = data(I={WIDGET + key: ['<module>']})
            self.assertEqual(run(OLD.replace('SETTING = 1', 'SETTING = 2'), evidence), (None, 'import_module_read'))

    def test_c_missing_evidence_falls_back(self):
        self.assertEqual(run(OLD.replace('VALUE = 1', 'VALUE = 9')), (None, 'unobserved_class'))
        evidence = data(A={WIDGET + '@SETTING': []})
        self.assertEqual(run(OLD.replace('SETTING = 1', 'SETTING = 2'), evidence), (None, 'unobserved_attribute'))
        evidence = data()
        del evidence['classes']
        self.assertEqual(run(OLD.replace('SETTING = 1', 'SETTING = 2'), evidence), (None, 'class_evidence'))

    def test_c_other_structural_edits_and_core_files_fall_back(self):
        for old, new in [('SETTING = 1', 'RENAMED = 1'), ('class Widget(Base):', 'class Widget(Base, Mixin):'),
                         ('LIMIT = 3', 'LIMIT = 4')]:
            with self.subTest(new=new):
                self.assertEqual(run(OLD.replace(old, new)), (None, 'structural_or_text'))
        for core in ['sqlglot/parser.py', 'sqlglot/dialects/dialect.py', 'sqlglot/expressions/core.py', 'sqlglot/toys/__init__.py']:
            with self.subTest(core=core):
                self.assertEqual(run(OLD.replace('SETTING = 1', 'SETTING = 2'), path=core), (None, 'structural_or_text'))

    def test_bitset_encoding(self):
        import base64
        bits = (1 << 3) | (1 << 700)
        self.assertEqual(tests_of(base64.b64encode(bits.to_bytes(203, 'little')).decode()), {3, 700})
        self.assertEqual(tests_of([4, 5]), {4, 5})
        self.assertEqual(tests_of(None), set())
