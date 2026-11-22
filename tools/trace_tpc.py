"""Trace actual TPC parent tests and submitted query work in the locked environment."""
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import sys

import pytest

METHODS = {'test_execute_tpch', 'test_execute_tpcds'}
OUT = Path(os.environ.get('BR_TPC_TRACE_OUT', '/tmp/tpc-trace'))
ROOT = '/src/'


@contextmanager
def capture(output):
    lines = defaultdict(set)
    monitor = sys.monitoring

    def trace(code, line):
        path = code.co_filename
        if path.startswith(ROOT + 'sqlglot/'):
            lines[path[len(ROOT):]].add(line)

    previous = monitor.register_callback(4, monitor.events.LINE, trace)
    monitor.set_events(4, monitor.events.LINE)
    try:
        yield
    finally:
        monitor.register_callback(4, monitor.events.LINE, previous)
        if previous is None:
            monitor.set_events(4, 0)
        output.write_text(json.dumps({path: sorted(values) for path, values in sorted(lines.items())}),
                          encoding='utf-8')


def trace_worker(directory, index, function, args, kwargs):
    sys.monitoring.use_tool_id(4, 'blast-tpc-query')
    try:
        with capture(Path(directory) / f'{index}.worker'):
            return function(*args, **kwargs)
    finally:
        sys.monitoring.free_tool_id(4)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item):
    if item.name not in METHODS or item.path.name != 'test_executor.py':
        yield
        return
    module = item.module
    test_class = item.cls
    source = test_class._mp_execute.__code__
    directory = OUT / item.name
    directory.mkdir(parents=True)
    parse, submit, check = module.parse_one, ProcessPoolExecutor.submit, test_class.subtestHelper
    queries = []
    compared = set()

    def parse_query(sql, *args, **kwargs):
        if sys._getframe(1).f_code is not source:
            return parse(sql, *args, **kwargs)
        with capture(directory / f'{len(queries)}.parse'):
            expression = parse(sql, *args, **kwargs)
        queries.append((sha256(sql.encode()).hexdigest(), id(expression)))
        return expression

    def submit_query(pool, function, /, *args, **kwargs):
        if function is not module.mp_execute:
            return submit(pool, function, *args, **kwargs)
        index = len(queries) - 1
        if index < 0 or id(args[0]) != queries[index][1]:
            raise RuntimeError('could not link TPC parse and worker')
        return submit(pool, trace_worker, str(directory), index, function, args, kwargs)

    def compare_query(self, index, *args, **kwargs):
        with capture(directory / f'{index}.compare'):
            result = check(self, index, *args, **kwargs)
        compared.add(index)
        return result

    sys.monitoring.use_tool_id(4, 'blast-tpc-query')
    module.parse_one, ProcessPoolExecutor.submit, test_class.subtestHelper = parse_query, submit_query, compare_query
    try:
        with capture(directory / 'shared'):
            yield
    finally:
        module.parse_one, ProcessPoolExecutor.submit, test_class.subtestHelper = parse, submit, check
        sys.monitoring.free_tool_id(4)
        indexes = set(range(len(queries)))
        if not indexes or {int(path.stem) for path in directory.glob('*.worker')} != indexes:
            raise RuntimeError('incomplete TPC query workers')
        (directory / 'index.json').write_text(json.dumps(dict(
            parent=item.nodeid, queries=[digest for digest, _ in queries], compared=sorted(compared))),
            encoding='utf-8')
