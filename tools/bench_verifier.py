"""Run a baseline or experimental image with the documented scorer limits."""
import argparse
import json
from pathlib import Path
import shutil
from statistics import median
import subprocess
import sys
import tempfile

from generalization import CASES, CATALOG, REPORTS, ROOT, complete_label, digest

sys.path.insert(0, str(ROOT))
from score import evaluate_run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image')
    parser.add_argument('split', choices=('public', 'holdout', 'dev', 'validation', 'p13', 'p14'))
    parser.add_argument('--mode', default='')
    parser.add_argument('--runs', type=int, default=3)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error('--runs must be positive')
    catalog_bytes = CATALOG.read_bytes()
    catalog = json.loads(catalog_bytes)
    tests = catalog['tests']
    numbers = {test['id']: test['number'] for test in tests}
    coverage = []
    with tempfile.TemporaryDirectory(dir=REPORTS.parent, prefix='bench-') as tmp:
        patches = Path(tmp)
        if args.split == 'public':
            patches = CATALOG.parent/'commits'
            answers = json.loads((CATALOG.parent/'answers.json').read_bytes())['commits']
            inconclusive = []
        else:
            answers, inconclusive = {}, []
            for case, (_, split, _) in CASES.items():
                if split != args.split:
                    continue
                patch, report = REPORTS/f'{case}.patch', REPORTS/f'{case}.json'
                shutil.copyfile(patch, patches/patch.name)
                label = json.loads(report.read_bytes()) if report.is_file() else None
                if complete_label(label, patch.read_bytes(), catalog, digest(catalog_bytes)):
                    answers[case] = {'failing': [numbers[name] for name in label['failed']]}
                else:
                    answers[case] = {'failing': []}
                    inconclusive.append(case)
        entry = '/app/verifier.py' if args.mode else '/app/selector.py'
        code = (
            "import resource,subprocess,sys,time\n"
            "start=time.monotonic()\n"
            f"subprocess.run([sys.executable,{entry!r}],check=True)\n"
            "u=resource.getrusage(resource.RUSAGE_CHILDREN)\n"
            "print(u.ru_utime+u.ru_stime,time.monotonic()-start,u.ru_maxrss,file=sys.stderr)\n"
        )
        command = ['docker', 'run', '--rm', '--platform', 'linux/amd64', '--network', 'none', '--cpus', '2',
                   '--memory', '4096m', '--memory-swap', '4096m', '--pids-limit', '256', '--read-only',
                   '--tmpfs', '/tmp:rw,size=64m,mode=1777', '--cap-drop', 'ALL',
                   '--security-opt', 'no-new-privileges', '--user', '65534:65534', '-e', 'HOME=/tmp',
                   '-e', f'BR_VERIFY={args.mode}', '-v', f'{patches}:/data/commits:ro',
                   '-v', f'{CATALOG}:/data/tests.json:ro', args.image, 'python', '-c', code]
        for _ in range(args.runs):
            run = subprocess.run(command, capture_output=True, timeout=180, check=True)
            diagnostics = run.stderr.decode().splitlines()
            cpu, wall, rss = map(float, diagnostics[-1].split())
            result = evaluate_run(run.stdout, tests, answers)
            if not result['ok'] or len(run.stdout) > 2_000_000:
                raise ValueError(result)
            record = dict(ci=result['simulated_milliseconds'] / 1000, cpu=cpu, wall=wall,
                          peak_child_rss_kib=rss, misses=result['missed_commits'], output=digest(run.stdout),
                          actions=[line for line in diagnostics if line.startswith('verification ')])
            coverage.append(record)
            print(json.dumps(record), flush=True)
    deterministic = len({run['output'] for run in coverage}) == 1
    print(json.dumps(dict(deterministic=deterministic, inconclusive=inconclusive,
                          median_total=round(median(run['ci'] + run['cpu'] for run in coverage), 6))))
    return int(not deterministic or any(run['misses'] for run in coverage))


if __name__ == '__main__':
    raise SystemExit(main())
