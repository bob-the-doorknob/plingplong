"""Compare runtime entry points with the unchanged official scorer (host only)."""
import contextlib
import importlib.util
import io
import json
import time
from pathlib import Path
import selector
from score import evaluate_run

ROOT = Path(__file__).resolve().parent
SAMPLE = ROOT / 'blast-radius-sample/sample'


def main():
    tests = json.loads((SAMPLE / 'tests.json').read_text())['tests']
    answers = json.loads((SAMPLE / 'answers.json').read_text())['commits']
    spec = importlib.util.spec_from_file_location('starter', ROOT / 'blast-radius-sample/selector.py')
    starter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(starter)
    for name, module in [('starter', starter), ('optimized', selector)]:
        module.DATA = SAMPLE
        output = io.StringIO()
        cpu, wall = time.process_time(), time.perf_counter()
        with contextlib.redirect_stdout(output):
            module.main()
        cpu, wall = time.process_time() - cpu, time.perf_counter() - wall
        payload = output.getvalue().encode('utf-8')
        result = evaluate_run(payload, tests, answers)
        assert result['ok'], result
        assert not result['missed_commits'], result
        assert len(payload) <= 2_000_000
        workers = json.loads(payload.splitlines()[0])['workers']
        result.update(variant=name, cpu_seconds=cpu, wall_seconds=wall,
                      workers=len(workers), selected_per_commit=sum(map(len, workers)),
                      recorded_seconds_per_commit=sum(t['seconds'] for t in tests),
                      worker_overhead_seconds=2 * len(workers) * len(answers))
        print(json.dumps(result))
        if name == 'optimized':
            (ROOT / 'output.jsonl').write_bytes(payload)


if __name__ == '__main__':
    main()
