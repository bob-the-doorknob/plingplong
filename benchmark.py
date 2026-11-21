"""Measure selectors with public answers used only after all output is produced."""
from collections import Counter
import json
from pathlib import Path
import time

from hybrid import decide, load
from score import evaluate_run
import selector

SAMPLE = Path(__file__).resolve().parent / 'blast-radius-sample/sample'


def main():
    tests = json.loads((SAMPLE/'tests.json').read_text())['tests']
    answers = json.loads((SAMPLE/'answers.json').read_text())['commits']
    for mode in ['all', 'file', 'scope']:
        start, cpu = time.perf_counter(), time.process_time()
        full = selector.schedule(tests)
        evidence = load(tests) if mode != 'all' else None
        rows, counts, reasons = [], [], Counter()
        for patch in sorted((SAMPLE/'commits').glob('*.patch')):
            ids, reason = (None,'baseline') if mode == 'all' else decide(patch.read_text(encoding='utf-8'),evidence,mode)
            workers = full if ids is None else selector.schedule([t for t in tests if t['id'] in ids])
            if ids is None:
                reasons[reason] += 1
            counts.append(sum(map(len,workers)))
            rows.append(json.dumps(dict(commit=patch.stem,workers=workers),separators=(',',':')))
        payload = ('\n'.join(rows)+'\n').encode()
        cpu, wall = time.process_time()-cpu, time.perf_counter()-start
        result = evaluate_run(payload, tests, answers)
        assert result['ok'] and len(payload)<2_000_000, result
        print(mode, result, 'cpu',cpu,'wall',wall,'mean',sum(counts)/len(counts),'max',max(counts),'fallback',dict(reasons))
        if mode == 'scope':
            Path('output.jsonl').write_bytes(payload)


if __name__ == '__main__':
    main()
