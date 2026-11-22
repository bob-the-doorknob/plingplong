import ast
import unittest

from structural import binding_delta, precision_readers
from tools.precision_plan import make_plan


class PrecisionTest(unittest.TestCase):
    path = 'sqlglot/example.py'
    source = "UNITS = {'x': 'old', 'y': 'same'}\ndef use(self, unit): return UNITS.get(unit)\n"

    def test_only_literal_value_changes_are_eligible(self):
        self.assertEqual(binding_delta(self.source, self.source.replace('old', 'new')), ('UNITS', ('x',)))
        for replacement in ("{'z': 'old', 'y': 'same'}", "{'x': 8, 'y': 'same'}",
                            "{'x': read(), 'y': 'same'}", "{'y': 'same', 'x': 'old'}"):
            with self.subTest(replacement=replacement):
                self.assertIsNone(binding_delta(self.source, self.source.replace("{'x': 'old', 'y': 'same'}", replacement)))

    def test_key_plan_keeps_receiver_and_rejects_escapes(self):
        plan = make_plan({self.path: self.source})
        site, = plan[self.path]
        self.assertEqual(site[1:], (self.path, 'UNITS', 'key', 'self'))
        for code in ('alias = UNITS', 'all_keys = list(UNITS)', 'UNITS.update(extra)',
                     'out = UNITS.get("x")', 'def f(UNITS): return UNITS.get("x")'):
            with self.subTest(code=code):
                self.assertFalse(make_plan({self.path: self.source + code}))
        self.assertFalse(make_plan({self.path: self.source, 'tests/test_mod.py': 'from sqlglot.example import UNITS'}))

    def test_package_plan_conservatively_bounds_module_resolution(self):
        package = 'sqlglot/__init__.py'
        body = 'pretty = False\n'
        safe = 'import sqlglot as sg\ndef run(self, explicit): return explicit if explicit is not None else sg.pretty\n'
        plan = make_plan({package: body, self.path: safe})
        self.assertEqual(plan[self.path][0][1:], (package, 'pretty', 'attribute', 'self'))
        self.assertEqual(binding_delta(body, body.replace('False', 'True')), ('pretty', None))
        for extra in ('from sqlglot import *', 'from sqlglot import pretty as value',
                      'read_module(sg)', 'replacement = sg.__dict__', 'sg = replacement'):
            with self.subTest(extra=extra):
                self.assertFalse(make_plan({package: body, self.path: safe + extra}))

    def test_required_readers_include_unknown_keys_and_fail_closed(self):
        new = self.source.replace('old', 'new')
        binding = {'UNITS': {'kind': 'key', 'keys': {'x': [0], 'y': [1]}, 'unknown': [2]}}
        self.assertEqual(precision_readers(self.source, new, binding, 3), ({0, 2}, 'mapping_key'))
        for keys in ({}, {'x': [-1]}, {'x': [3]}, {'x': [False]}):
            binding['UNITS']['keys'] = keys
            self.assertIsNone(precision_readers(self.source, new, binding, 3))
