import json
import unittest
from pathlib import Path
import selector
from score import evaluate_run


def inventory(durations):
    return [dict(number=i, seconds=d) for i, d in enumerate(durations)]


class SchedulerTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(selector.schedule([]), [])

    def test_one_and_overhead(self):
        self.assertEqual(selector.schedule(inventory([10])), [[0]])
        result = evaluate_run(b'{"commit":"x","workers":[[0]]}', inventory([10]), {'x':{'failing':[0]}})
        self.assertEqual(result['simulated_milliseconds'], 12000)

    def test_short_tests_use_one_worker(self):
        self.assertEqual(selector.schedule(inventory([0.1]*8)), [list(range(8))])

    def test_equal_long_tests(self):
        self.assertEqual(selector.schedule(inventory([10]*4)), [[0],[1],[2],[3]])

    def test_uneven(self):
        self.assertEqual(selector.schedule(inventory([10, 3, 3, 3])), [[0],[1,2,3]])

    def test_bounded_complete_deterministic(self):
        tests = inventory([10]*20)
        workers = selector.schedule(tests)
        self.assertLessEqual(len(workers), 8)
        self.assertEqual(sorted(t for w in workers for t in w), list(range(20)))
        self.assertEqual(workers, selector.schedule(list(reversed(tests))))

    def test_invalid_inventory(self):
        for tests in [[{'number':0,'seconds':-1}], [{'number':True,'seconds':1}], inventory([float('nan')]), inventory([float('inf')]), inventory([1])+inventory([2])]:
            with self.subTest(tests=tests), self.assertRaises(ValueError):
                selector.schedule(tests)

    def test_official_sample_output(self):
        sample = Path('blast-radius-sample/sample')
        tests = json.loads((sample/'tests.json').read_text())['tests']
        answers = json.loads((sample/'answers.json').read_text())['commits']
        workers = selector.schedule(tests)
        output = ''.join(json.dumps({'commit':c,'workers':workers})+'\n' for c in answers).encode()
        self.assertLess(len(output), 2_000_000)
        result = evaluate_run(output, tests, answers)
        self.assertTrue(result['ok'])
        self.assertEqual(result['missed_commits'], [])
        self.assertLess(result['simulated_milliseconds'], 1210470)


if __name__ == '__main__':
    unittest.main()
