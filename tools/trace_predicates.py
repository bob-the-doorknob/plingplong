"""Offline operand observations, using only native comparison slots for alternate evaluations."""
import ast
import atexit
import builtins
from concurrent.futures import ProcessPoolExecutor
from enum import EnumType
import importlib.machinery
import json
import operator
import os
from pathlib import Path
import sys

sys.path.insert(0, '/repo')
from predicate import supported
import trace_events

OPERATORS = dict(Is=operator.is_, IsNot=operator.is_not, Eq=operator.eq, NotEq=operator.ne)
ALTERNATE = dict(Is='Eq', IsNot='NotEq', Eq='Is', NotEq='IsNot')
NATIVE_TYPES = (int, float, complex, bool, bytes, str, type(None))
observations = {}


def native(value):
    cls = type(value)
    if any(cls is kind for kind in NATIVE_TYPES):
        return True
    if type(cls) not in (type, EnumType):
        return False
    raw = [type.__getattribute__(base, '__dict__')
           for base in type.__getattribute__(cls, '__mro__')]
    eq = next(mapping['__eq__'] for mapping in raw if '__eq__' in mapping)
    ne = next(mapping['__ne__'] for mapping in raw if '__ne__' in mapping)
    return (eq is object.__eq__ and ne is object.__ne__) or (
        issubclass(cls, str) and eq is str.__eq__ and ne is str.__ne__
    )


def compare(left, right, key, op):
    seen = observations.setdefault(key, {})
    context = trace_events.context
    if seen.get(context) is False:
        return OPERATORS[op](left, right)
    pure = native(left) and native(right)
    result = OPERATORS[op](left, right)
    if not pure:
        seen[context] = False
        return result
    alternate = OPERATORS[ALTERNATE[op]](left, right)
    seen[context] = type(result) is bool and result is alternate
    return result


class Instrument(ast.NodeTransformer):
    def __init__(self, path):
        self.path = path

    def visit_Compare(self, node):
        node = self.generic_visit(node)
        if not supported(node):
            return node
        key = f'{self.path}:{node.lineno}:{node.col_offset}'
        replacement = ast.Call(ast.Name('_blast_radius_observe_compare', ast.Load()),
                               [node.left, node.comparators[0], ast.Constant(key),
                                ast.Constant(type(node.ops[0]).__name__)], [])
        return ast.copy_location(replacement, node)


def dump():
    Path(f'/tmp/predicates/{os.getpid()}.json').write_text(json.dumps(observations))


def run_labeled(nodeid, function, args, kwargs):
    previous = trace_events.context
    trace_events.owner(nodeid)
    try:
        return function(*args, **kwargs)
    finally:
        trace_events.owner(previous)


def labeled_submit(original):
    def submit(pool, function, /, *args, **kwargs):
        context = trace_events.context
        if '::' in context:
            return original(pool, run_labeled, context, function, args, kwargs)
        return original(pool, function, *args, **kwargs)
    return submit


def start():
    Path(f'/tmp/predicate-started/{os.getpid()}.json').write_text(
        json.dumps(dict(owner=trace_events.context, order=os.environ.get('BR_REVERSE', '0')))
    )
    ProcessPoolExecutor.submit = labeled_submit(ProcessPoolExecutor.submit)
    builtins._blast_radius_observe_compare = compare
    original = importlib.machinery.SourceFileLoader.get_code

    def instrumented(loader, fullname):
        path = loader.path
        if not path.startswith('/src/sqlglot/') or not path.endswith('.py'):
            return original(loader, fullname)
        tree = ast.parse(loader.get_data(path), filename=path)
        tree = ast.fix_missing_locations(Instrument(path[5:]).visit(tree))
        return compile(tree, path, 'exec', dont_inherit=True)

    importlib.machinery.SourceFileLoader.get_code = instrumented
    atexit.register(dump)
