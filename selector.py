"""Pinned-source coverage selector with cost-aware deterministic LPT scheduling."""
from hybrid import load, decide

import json
import math
import sys
from pathlib import Path

DATA = Path('/data')


def schedule(tests: list[dict]) -> list[list[int]]:
    durations = {}
    for test in tests:
        number, seconds = test['number'], test['seconds']
        if (type(number) is not int or number < 0 or number in durations
                or type(seconds) not in (int, float)
                or not math.isfinite(seconds) or seconds < 0):
            raise ValueError('invalid test number or duration')
        durations[number] = math.floor(seconds * 1000 + 0.5)
    if not durations:
        return []
    ordered = sorted(durations, key=lambda n: (-durations[n], n))
    best, best_cost = [], math.inf
    for count in range(1, min(8, len(ordered)) + 1):
        workers = [[] for _ in range(count)]
        loads = [0] * count
        for number in ordered:
            lightest = loads.index(min(loads))
            workers[lightest].append(number)
            loads[lightest] += durations[number]
        occupied = [worker for worker in workers if worker]
        cost = max(loads) + 2000 * len(occupied)
        if cost < best_cost:
            best, best_cost = occupied, cost
    return best


def main() -> None:
    tests = json.loads((DATA / 'tests.json').read_text(encoding='utf-8'))['tests']
    workers = schedule(tests)
    evidence = load(tests)
    for patch in sorted((DATA / 'commits').glob('*.patch')):
        try:
            ids, reason = decide(patch.read_text(encoding='utf-8'), evidence)
        except (UnicodeError, OSError, RecursionError):
            ids, reason = None, 'unreadable_patch'
        selected = workers if ids is None else schedule([t for t in tests if t['id'] in ids])
        print(json.dumps({'commit': patch.stem, 'workers': selected}, separators=(',', ':')))
        print(patch.stem, reason, sum(map(len, selected)), file=sys.stderr)


if __name__ == '__main__':
    main()
