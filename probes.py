"""Development probes for import state and the SQLGlot executor handoff."""
from collections import defaultdict
from hashlib import sha256
import importlib
from pathlib import Path
import sys

from fingerprints import fingerprint


def import_state(modules):
    state = {}
    for name in sorted(modules):
        try:
            module = importlib.import_module(name)
        except Exception as error:
            return {'import_error': type(error).__name__}
        for key, value in vars(module).items():
            if not key.startswith('__'):
                state[name + '.' + key] = value
                if isinstance(value, type) and value.__module__ == name:
                    state[name + '.' + key + ' attributes'] = dict(vars(value))
                    state[name + '.' + key + ' bases'] = value.__bases__
    from sqlglot import exp, Dialect
    from sqlglot.generator import _DISPATCH_CACHE

    state.update(expressions=exp.EXPR_CLASSES, dialects=Dialect.classes, generator_dispatch=_DISPATCH_CACHE)
    cells, unknown = {}, []
    for name, value in sorted(state.items()):
        try:
            cells[name] = fingerprint(value)
        except (TypeError, ValueError, RecursionError):
            unknown.append(name)
    return dict(cells=cells, opaque=unknown, imports=sorted(n for n in sys.modules if n.startswith('sqlglot')))


def tpc_handoff(dataset, trace=False):
    from sqlglot import exp, parse_one, transpile
    from sqlglot.optimizer import optimize
    from sqlglot.planner import Plan, Step
    from sqlglot.schema import ensure_schema
    from tests.helpers import TPCH_SCHEMA, TPCDS_SCHEMA, load_sql_fixture_pairs

    def project(value):
        if isinstance(value, exp.Expr):
            names = [name for cls in type(value).__mro__ for name in cls.__dict__.get('__slots__', ())
                     if name not in ('__dict__', '__weakref__')]
            return {name: getattr(value, name) for name in sorted(set(names)) if hasattr(value, name)}
        if isinstance(value, (Plan, Step)):
            return vars(value)
        raise TypeError(type(value))

    schema = TPCH_SCHEMA if dataset == 'tpc-h' else TPCDS_SCHEMA
    rows, lines = {}, defaultdict(set)
    root = str(Path.cwd()) + '/'

    def record(code, line):
        if code.co_filename.startswith(root + 'sqlglot/'):
            lines[code.co_filename[len(root):]].add(line)

    if trace:
        sys.monitoring.use_tool_id(3, 'tpc-handoff')
        sys.monitoring.register_callback(3, sys.monitoring.events.LINE, record)
    for index, (meta, sql, _) in enumerate(load_sql_fixture_pairs(f'optimizer/{dataset}/{dataset}.sql'), 1):
        lines.clear()
        executing = bool(meta.get('execute'))
        if trace:
            sys.monitoring.set_events(3, sys.monitoring.events.LINE)
        try:
            parsed = parse_one(sql)
            if executing:
                expression = optimize(parsed, ensure_schema(schema), leave_tables_isolated=True, dialect=None)
                logged = expression.sql(pretty=True)
                state = (expression, Plan(expression), logged, transpile(sql, write='duckdb'))
            else:
                # _mp_execute parses every query in the parent before workers inspect its flag.
                state = parsed
        finally:
            if trace:
                sys.monitoring.set_events(3, 0)
        try:
            graph = fingerprint((meta, state), project)
        except (TypeError, ValueError, RecursionError):
            graph = None
        rows[str(index)] = dict(graph=graph, executes=executing, query=sha256(sql.encode()).hexdigest(),
                                lines={path: sorted(values) for path, values in sorted(lines.items())})
    return rows
