"""Measure selectors with public answers used only after all output is produced."""
import argparse
from collections import Counter
import json
from pathlib import Path
import time

from hybrid import decide, load
from score import evaluate_run
import selector

SAMPLE = Path(__file__).resolve().parent / 'blast-radius-sample/sample'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--details', action='store_true', help='show scope costs per patch')
    details = parser.parse_args().details
    tests = json.loads((SAMPLE/'tests.json').read_text())['tests']
    answers = json.loads((SAMPLE/'answers.json').read_text())['commits']
    durations = {t['number']: round(t['seconds'] * 1000) for t in tests}
    for mode in ['all', 'file', 'scope']:
        start, cpu = time.perf_counter(), time.process_time()
        full = selector.schedule(tests)
        evidence = load(tests) if mode != 'all' else None
        breakdown = []
        rows, counts, reasons = [], [], Counter()
        for patch in sorted((SAMPLE/'commits').glob('*.patch')):
            ids, reason = (None,'baseline') if mode == 'all' else decide(patch.read_text(encoding='utf-8'),evidence,mode)
            workers = full if ids is None else selector.schedule([t for t in tests if t['id'] in ids])
            if ids is None:
                reasons[reason] += 1
            counts.append(sum(map(len,workers)))
            if details and mode == 'scope':
                makespan = max((sum(durations[n] for n in w) for w in workers), default=0)
                largest = sorted((n for w in workers for n in w), key=lambda n: (-durations[n], n))[:3]
                breakdown.append((makespan + 2000 * len(workers), patch.stem, counts[-1],
                                  len(workers), makespan, reason, largest))
            rows.append(json.dumps(dict(commit=patch.stem,workers=workers),separators=(',',':')))
        payload = ('\n'.join(rows)+'\n').encode()
        cpu, wall = time.process_time()-cpu, time.perf_counter()-start
        result = evaluate_run(payload, tests, answers)
        assert result['ok'] and len(payload)<2_000_000, result
        print(mode, result, 'cpu',cpu,'wall',wall,'mean',sum(counts)/len(counts),'max',max(counts),'fallback',dict(reasons))
        if mode == 'scope':
            Path('output.jsonl').write_bytes(payload)
            for cost, commit, count, workers, makespan, reason, largest in sorted(breakdown, reverse=True):
                print(f'{commit}: cost={cost / 1000:.3f}s makespan={makespan / 1000:.3f}s '
                      f'workers={workers} tests={count} reason={reason} '
                      f'longest={[(tests[n]["id"], durations[n]) for n in largest]}')


if __name__ == '__main__':
    main()
