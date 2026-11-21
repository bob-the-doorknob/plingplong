"""Verify the committed collector output against the organizer catalog."""
import json
import unittest
from pathlib import Path

from hybrid import PIN, load


class TraceContract(unittest.TestCase):
    def test_exact_identity_survives_renumbering(self):
        path = Path('blast-radius-sample/sample/tests.json')
        tests = json.loads(path.read_text())['tests']
        manifest = [dict(test, number=2000+i) for i,test in enumerate(reversed(tests))]
        data = load(manifest)
        self.assertEqual(data['pin'], PIN)
        self.assertEqual(set(data['ids']), {t['id'] for t in tests})
        self.assertTrue(data['hits']['sqlglot/serde.py::dump'])
        self.assertTrue(data['hits']['tests/fixtures/optimizer/eliminate_joins.sql'])
        self.assertIsNone(load(manifest[:-1]))
