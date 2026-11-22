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
from semantic import classify_change
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


def ordered_prefix(collected, ids, expected, limit, skipped=()):
    if ([name for name in collected if name not in skipped] != expected
            or set(collected) != set(expected) | set(skipped) or not ids or not set(ids) <= set(expected)):
        return None
    count = max(collected.index(name) for name in ids) + 1
    return collected[:count] if count <= limit else None


def ordered_passes(report, ids):
    prefix = report.get('prefix')
    if (not prefix or report.get('collected') != prefix or not set(ids) <= set(prefix)
            or set(report.get('finished', ())) != set(prefix)
            or report.get('exit') not in (0, 1) or report.get('collection_error', True)):
        return set()
    return (set(report['passing']) & set(ids)) - set(report['failed']) - set(report['skipped'])


def pytest_report(ids, temporary, expected=None, skipped=(), limit=64):
    import pytest

    class Reports:
        def __init__(self):
            self.collected = []
            self.calls = set()
            self.finished = set()
            self.completed = set()
            self.failed = set()
            self.skipped = set()
            self.collection_error = False
            self.prefix = None

        @pytest.hookimpl(trylast=True)
        def pytest_collection_modifyitems(self, items):
            if expected is None:
                return
            self.prefix = ordered_prefix([item.nodeid for item in items], ids, expected, limit, skipped)
            wanted = len(self.prefix or ())
            if wanted < len(items):
                items[:] = items[:wanted]

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
            if report.when == 'teardown':
                self.completed.add(report.nodeid)

    reports = Reports()
    status = pytest.main(['-q', '--tb=no', '-p', 'no:cacheprovider',
                          '--basetemp', str(temporary), *(ids if expected is None else ['tests'])], plugins=[reports])
    return dict(exit=int(status), collected=reports.collected, passing=sorted(reports.calls & reports.finished),
                failed=sorted(reports.failed), skipped=sorted(reports.skipped),
                collection_error=reports.collection_error, prefix=reports.prefix, finished=sorted(reports.completed))


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
        self.tpc_left = 1
        self.baselines = {}
        self.deadline = time.monotonic() + 100

    def run(self, view, action, payload, timeout):
        remaining = self.deadline - time.monotonic()
        return child(view, action, payload, min(timeout, remaining)) if remaining > .1 else {}

    def compare(self, view, action, payload, timeout):
        key = (action, tuple(payload))
        if key not in self.baselines:
            with overlay(BASE, {}) as clean:
                self.baselines[key] = self.run(clean, action, payload, timeout)
        initial = self.baselines[key]
        current = self.run(view, action, payload, timeout)
        if not initial or not current:
            return 'inconclusive'
        if action == 'import':
            if 'import_error' in initial:
                return 'inconclusive'
            if 'import_error' in current:
                return 'import_error'
            if initial['opaque'] or current['opaque']:
                return 'partial_change' if initial != current else 'partial_equal'
        if action == 'tpc' and any(row['graph'] is None for rows in (initial, current) for row in rows.values()):
            return 'inconclusive'
        return 'equal_projection' if initial == current else 'changed_projection'

    def __call__(self, diff, ids, tests, evidence, reason):
        if not ids or not self.jobs_left or not self.enabled & {'cheap', 'ordered', 'import', 'tpc'}:
            return ids
        protected = set(evidence['hits'].get('!untraced', ())) | set(evidence.get('line_evidence', {}).get('extra', ()))
        retained = {evidence['ids'][i] for i in protected if i >= 0}
        candidates = [test for test in tests if test['id'] in ids]
        ordered = 'ordered' in self.enabled
        calibrate = 'calibrate' in self.enabled
        if ordered:
            retained.update(test['id'] for test in tests[64:])
        proposed = plan(candidates, retained, calibrate) if self.enabled & {'cheap', 'ordered'} else []
        manifest = None
        if ordered and proposed:
            proposed_set = set(proposed)
            prefix_end = max(i for i, test in enumerate(tests) if test['id'] in proposed_set)
            savings = simulated(candidates) - simulated([t for t in candidates if t['id'] not in proposed_set])
            if not calibrate and savings <= 1.0 + 1.5 * sum(t['seconds'] for t in tests[:prefix_end + 1]):
                proposed = []
        tpc = [name for name, method in (('tpc-h', 'test_execute_tpch'), ('tpc-ds', 'test_execute_tpcds'))
               if any(test.endswith('::TestExecutor::' + method) for test in ids)]
        if not proposed and 'import' not in self.enabled and not ('tpc' in self.enabled and tpc and self.tpc_left):
            return ids
        try:
            updates = read_updates(diff, BASE)
            code = all(path.startswith('sqlglot/') and path.endswith('.py') for path in updates)
            structural = code and any(classify_change((BASE/path).read_text(encoding='utf-8'), content)['structural']
                                      for path, content in updates.items())
            check_import = structural and 'import' in self.enabled
            check_tpc = 'tpc' in self.enabled and bool(tpc) and self.tpc_left and code and not structural
            if not proposed and not check_import and not check_tpc:
                return ids
            self.jobs_left -= 1
            with overlay(BASE, updates) as view:
                if check_import:
                    modules = [k.removesuffix('.py').removesuffix('/__init__').replace('/', '.') for k in updates]
                    observed = self.compare(view, 'import', modules, 4)
                    print('verification import', observed, file=sys.stderr)
                    # Projected equality cannot establish absence of import-time effects.
                    return None if observed == 'import_error' else ids
                action = 'ordered' if ordered else 'pytest'
                if ordered and proposed:
                    manifest = json.loads(Path('/data/tests.json').read_bytes())
                payload = [proposed, [test['id'] for test in tests], manifest.get('skipped', [])] if manifest else proposed
                report = self.run(view, action, payload, 5) if proposed else {}
                passed = (ordered_passes if ordered else passed_tests)(report, proposed) if report else set()
                remaining = ids - passed
                if proposed:
                    status = 'reported' if report else 'inconclusive'
                    print('verification', action, status, len(proposed), len(passed), file=sys.stderr)
                if ordered:
                    # Calibration only. A prefix pass needs independent seed and suite-state validation.
                    remaining = ids
                if check_tpc:
                    self.tpc_left -= 1
                    for name in tpc:
                        print('verification', name, self.compare(view, 'tpc', [name, False], 12), file=sys.stderr)
                return remaining
        except (OSError, ValueError, KeyError, RecursionError):
            return ids


def main():
    if len(sys.argv) == 5 and sys.argv[1] == 'child':
        import resource

        cpu = 5 if sys.argv[3] in ('pytest', 'ordered') else 35
        resource.setrlimit(resource.RLIMIT_CPU, (cpu - 1, cpu))
        resource.setrlimit(resource.RLIMIT_FSIZE, (8_000_000, 8_000_000))
        resource.setrlimit(resource.RLIMIT_AS, (3_000_000_000, 3_000_000_000))
        sys.path.insert(0, os.getcwd())
        result, action, payload = Path(sys.argv[2]), sys.argv[3], json.loads(sys.argv[4])
        if action == 'pytest':
            report = pytest_report(payload, result.parent/'pytest-tmp')
        elif action == 'ordered':
            ids, expected, skipped = payload
            report = pytest_report(ids, result.parent/'pytest-tmp', expected, skipped)
        elif action == 'import':
            from probes import import_state
            report = import_state(payload)
        elif action == 'tpc':
            from probes import tpc_handoff
            report = tpc_handoff(*payload)
        else:
            raise ValueError(action)
        result.write_text(json.dumps(report))
    else:
        select(Experiment(set(os.environ.get('BR_VERIFY', '').split(','))))


if __name__ == '__main__':
    main()
