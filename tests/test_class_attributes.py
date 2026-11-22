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

class ExpressionRegistry(unittest.TestCase):
    def test_boolean_flag_keeps_registry_keys_but_other_reads_still_fall_back(self):
        path = 'sqlglot/expressions/example.py'
        old = 'class Example(Expression):\n    arg_types = {"this": True, "optional": False}\n'
        new = old.replace('False', 'True')
        cls = path + '::Example'
        evidence = data(
            M={cls: ['sqlglot/expressions/core.py::Expression']},
            R={cls: [1, 2]},
            I={cls + '@arg_types': [cls], cls + '@key': ['<module>']},
        )
        evidence['sources'] = {path: old}
        self.assertEqual(decide(git_patch({path: (old, new)}), evidence), (names(0, 1, 2), 'observed'))
        subclass = copy.deepcopy(evidence)
        subclass['classes'].pop('_index', None)
        subclass['classes']['M'][CUSTOM] = [cls]
        # Subclass receivers join; their own derived reads would enter the closure as consumers.
        self.assertEqual(decide(git_patch({path: (old, new)}), subclass), (names(0, 1, 2, 3), 'observed'))
        subclass['classes'].pop('_index', None)
        subclass['classes']['I'][cls + '@arg_types'].append(CUSTOM)
        subclass['classes']['I'][CUSTOM + '@required_args'] = ['<module>']
        self.assertEqual(decide(git_patch({path: (old, new)}), subclass), (None, 'import_module_read'))

        transitive = copy.deepcopy(evidence)
        transitive['classes'].pop('_index', None)
        transitive['classes']['I'][cls + '@arg_types'].append(OTHER)
        transitive['classes']['I'][OTHER + '@derived'] = ['<module>']
        self.assertEqual(decide(git_patch({path: (old, new)}), transitive), (None, 'import_module_read'))

        for field in ('arg_types', 'required_args', '__dict__'):
            expanded = copy.deepcopy(evidence)
            expanded['classes'].pop('_index', None)
            expanded['classes']['I'][cls + '@' + field] = ['<module>']
            self.assertEqual(decide(git_patch({path: (old, new)}), expanded), (None, 'import_module_read'))

    def test_registry_proof_requires_simple_literal_edit(self):
        path = 'sqlglot/expressions/example.py'
        cls = path + '::Example'
        evidence = data(
            M={cls: ['sqlglot/expressions/core.py::Expression']},
            R={cls: [1]},
            I={cls + '@arg_types': [cls], cls + '@key': ['<module>']},
        )
        old = 'class Example(Expression):\n    arg_types = {"this": True, "optional": False}\n'
        evidence['sources'] = {path: old}
        # Renamed argument keys reach code only through receivers of the class.
        self.assertEqual(decide(git_patch({path: (old, old.replace('optional', 'other'))}), evidence)[0], names(0, 1))
        self.assertIsNone(decide(git_patch({path: (old, old.replace('False', '1 / 0'))}), evidence)[0])

    def test_import_fallback_for_literal_replaced_with_runtime_expression(self):
        self.assertEqual(run(OLD.replace('SETTING = 1', 'SETTING = 1 / 0')),
                         (None, 'structural_or_text'))

    def test_import_fallback_for_literal_type_change(self):
        self.assertEqual(run(OLD.replace('SETTING = 1', 'SETTING = None')),
                         (None, 'structural_or_text'))


class MutatingCalls(unittest.TestCase):
    def test_class_body_mutation_changes_the_attribute_value(self):
        for old, new in [('TABLE.pop("a", None)', 'TABLE.pop("b", None)'), ('TABLE.update({"a": 1})', 'TABLE.update({"a": 2})')]:
            source = f'class Widget(Base):\n    TABLE = {{"a": 1, "b": 2}}\n    {old}\n'
            with self.subTest(new=new):
                result = classify_change(source, source.replace(old, new))
                self.assertEqual(result['class_attributes'], [dict(cls='Widget', attr='TABLE', body_read=True)])

    def test_mutations_that_may_raise_at_import_fall_back(self):
        old = 'class Widget(Base):\n    TABLE = {"a": 1, "b": 2}\n    TABLE.pop("a")\n'
        for new in (old.replace('pop("a")', 'pop("b")'), old.replace('TABLE.pop', 'OTHER.pop'),
                    old.replace('pop("a")', 'clear()'), old.replace('pop("a")', 'pop("a", None)'),
                    old.replace('    TABLE.pop("a")\n', '    TABLE.pop("a")\n    TABLE.pop("b")\n')):
            with self.subTest(new=new):
                self.assertIsNone(classify_change(old, new).get('class_attributes'))

    def test_new_names_in_class_values_fall_back(self):
        old = 'import exp\n\nSECOND = exp.Second\n\nclass Widget(Base):\n    TABLE = {"a": exp.First}\n'
        self.assertEqual(classify_change(old, old.replace('exp.First}', 'exp.Second}'))['class_attributes'],
                         [dict(cls='Widget', attr='TABLE', body_read=False)])
        self.assertIsNone(classify_change(old, old.replace('exp.First}', 'exp.Missing}')).get('class_attributes'))
        removed = 'class Widget(Base):\n    def run(self):\n        return 1\n    ALIAS = run\n'
        self.assertIsNone(classify_change(removed, removed.replace('def run(self)', 'def other(self)')).get('members'))


class ImportSafetyReview(unittest.TestCase):
    def test_added_method_shadowing_a_class_body_name_falls_back(self):
        old = 'def run():\n    return 0\n\n\nclass Widget(Base):\n    ALIAS = run\n'
        new = old.replace('class Widget(Base):\n', 'class Widget(Base):\n    def run(self):\n        return 1\n\n')
        self.assertIsNone(classify_change(old, new).get('members'))

    def test_names_only_used_in_function_bodies_are_not_known(self):
        old = 'import exp\n\nclass Widget(Base):\n    TABLE = {"a": exp.First}\n\ndef f():\n    return later.Second\n'
        self.assertIsNone(classify_change(old, old.replace('exp.First}', 'later.Second}')).get('class_attributes'))

    def test_mutators_must_match_the_literal_container(self):
        for value, old, new, ok in [('[1]', 'T.append(1)', 'T.append(2)', True), ('{1}', 'T.append(1)', 'T.append(2)', False),
                                    ('{"a": 1}', 'T.update(a=1)', 'T.update(a=2)', True),
                                    ('{"a": 1}', 'T.update({"a": X})', 'T.update({"b": X})', False),
                                    ('base.copy()', 'T.update(a=1)', 'T.update(a=2)', False)]:
            source = f'class Widget(Base):\n    T = {value}\n    {old}\n'
            with self.subTest(value=value, new=new):
                result = classify_change(source, source.replace(old, new)).get('class_attributes')
                self.assertEqual(bool(result), ok)
