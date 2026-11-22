"""Experimental verification of a conservative selector's candidates."""
from contextlib import contextmanager
import json
import os
from pathlib import Path, PurePosixPath
import signal
import subprocess
import sys
import tempfile
import time

from hybrid import apply_patch
from impact import changed_files
from selector import schedule, main as select

BASE = Path('/opt/sqlglot')


@contextmanager
def overlay(base, updates, directory=None):
    paths = [PurePosixPath(name) for name in updates]
    if any(p.is_absolute() or '..' in p.parts or p.as_posix() != name
           or not (base / p).is_file() or not (base / p).resolve().is_relative_to(base.resolve())
           for name, p in zip(updates, paths)):
        raise ValueError('invalid overlay path')

    def populate(source, target, prefix=''):
        target.mkdir()
        for entry in source.iterdir():
            if entry.name == '__pycache__':
                continue
            name = prefix + entry.name
            out = target / entry.name
            if name in updates:
                out.write_bytes(updates[name].encode('utf-8'))
            elif any(path.startswith(name + '/') for path in updates):
                populate(entry, out, name + '/')
            else:
                out.symlink_to(entry.resolve(), target_is_directory=entry.is_dir())

    with tempfile.TemporaryDirectory(prefix='br-verify-', dir=directory) as tmp:
        view = Path(tmp) / 'source'
        populate(base, view)
        yield view


def simulated(tests):
    durations = {t['number']: round(t['seconds'] * 1000) for t in tests}
    workers = schedule(tests)
    return (max((sum(durations[n] for n in w) for w in workers), default=0) + 2000 * len(workers))/1000


def plan(tests, retained, calibrate=False):
    cheap = sorted((t for t in tests if t['id'] not in retained and t['seconds'] <= .25),
                   key=lambda t: (-t['seconds'], t['id']))[:32]
    affordable = {t['id'] for t in cheap}
    possible = simulated(tests) - simulated([t for t in tests if t['id'] not in affordable])
    # This estimate controls work admission only. Test reports control exclusions.
    if not calibrate and possible <= .45 + 1.5 * sum(t['seconds'] for t in cheap):
        return []
    return sorted(affordable)


def pytest_report(ids, temporary):
    import pytest

    class Reports:
        def __init__(self):
            self.collected = []
            self.calls = set()
            self.finished = set()
            self.failed = set()
            self.skipped = set()
            self.collection_error = False

        def pytest_collection_finish(self, session):
            self.collected = [item.nodeid for item in session.items]

        def pytest_collectreport(self, report):
            self.collection_error |= report.failed

        def pytest_runtest_logreport(self, report):
            if report.failed:
                self.failed.add(report.nodeid)
            if report.skipped or hasattr(report, 'wasxfail'):
                self.skipped.add(report.nodeid)
            if report.passed and report.when == 'call':
                self.calls.add(report.nodeid)
            if report.passed and report.when == 'teardown':
                self.finished.add(report.nodeid)

    reports = Reports()
    status = pytest.main(['-q', '--tb=no', '-p', 'no:cacheprovider',
                          '--basetemp', str(temporary), *ids], plugins=[reports])
    return dict(exit=int(status), collected=reports.collected, passing=sorted(reports.calls & reports.finished),
                failed=sorted(reports.failed), skipped=sorted(reports.skipped),
                collection_error=reports.collection_error)


def passed_tests(report, ids):
    if (report.get('exit') not in (0, 1) or report.get('collection_error', True)
            or sorted(report.get('collected', [])) != sorted(ids)):
        return set()
    return (set(report['passing']) & set(ids)) - set(report['failed']) - set(report['skipped'])


def child(view, action, data, timeout=5):
    result = view.parent / 'result.json'
    result.unlink(missing_ok=True)
    command = [sys.executable, '-B', str(Path(__file__).resolve()), 'child',
               str(result), action, json.dumps(data)]
    env = os.environ | {'PYTHONPATH': str(view), 'SKIP_INTEGRATION': '0', 'PYTHONHASHSEED': '0',
                        'PYTHONDONTWRITEBYTECODE': '1', 'OPENBLAS_NUM_THREADS': '1',
                        'TMPDIR': str(view.parent)}
    with subprocess.Popen(command, cwd=view, env=env, start_new_session=True,
                          stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) as proc:
        try:
            if proc.wait(timeout) or not result.is_file() or result.stat().st_size > 2_000_000:
                return {}
            return json.loads(result.read_bytes())
        except (subprocess.TimeoutExpired, ValueError):
            return {}
        finally:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()


def read_updates(diff, base):
    paths = changed_files(diff, require_code=False)
    if not paths or not all(path.startswith(('sqlglot/', 'tests/'))
                            and '\\' not in path and '..' not in PurePosixPath(path).parts for path in paths):
        raise ValueError('unsupported verification edit')
    return apply_patch(diff, {path: (base / path).read_bytes().decode('utf-8') for path in paths})


class Experiment:
    def __init__(self, enabled):
        self.enabled = enabled
        self.jobs_left = 20
        self.deadline = time.monotonic() + 100

    def __call__(self, diff, ids, tests, evidence, reason):
        remaining = self.deadline - time.monotonic()
        if not ids or not self.jobs_left or 'cheap' not in self.enabled or remaining <= .1:
            return ids
        protected = set(evidence['hits'].get('!untraced', ())) | set(evidence.get('line_evidence', {}).get('extra', ()))
        retained = {evidence['ids'][i] for i in protected if i >= 0}
        proposed = plan([test for test in tests if test['id'] in ids], retained, 'calibrate' in self.enabled)
        if not proposed:
            return ids
        self.jobs_left -= 1
        try:
            with overlay(BASE, read_updates(diff, BASE)) as view:
                report = child(view, 'pytest', proposed, min(5, remaining))
                observed = passed_tests(report, proposed)
                status = 'reported' if report else 'inconclusive'
                print('verification pytest', status, len(proposed), len(observed), file=sys.stderr)
                return ids - observed
        except (OSError, ValueError, KeyError, RecursionError):
            return ids


def main():
    if len(sys.argv) == 5 and sys.argv[1] == 'child':
        import resource

        cpu = 5 if sys.argv[3] == 'pytest' else 35
        resource.setrlimit(resource.RLIMIT_CPU, (cpu - 1, cpu))
        resource.setrlimit(resource.RLIMIT_FSIZE, (8_000_000, 8_000_000))
        resource.setrlimit(resource.RLIMIT_AS, (3_000_000_000, 3_000_000_000))
        sys.path.insert(0, os.getcwd())
        result, action, payload = Path(sys.argv[2]), sys.argv[3], json.loads(sys.argv[4])
        if action == 'pytest':
            report = pytest_report(payload, result.parent/'pytest-tmp')
        else:
            raise ValueError(action)
        result.write_text(json.dumps(report))
    else:
        select(Experiment(set(os.environ.get('BR_VERIFY', '').split(','))))


if __name__ == '__main__':
    main()
