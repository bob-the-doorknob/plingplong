"""Observe certified accesses while leaving the mapping and key untouched."""
import ast
import atexit
import builtins
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from importlib import _bootstrap
from importlib.machinery import SourceFileLoader
import json
import os
from pathlib import Path

import trace_events
from precision_plan import location
from trace_predicates import labeled_submit


events = defaultdict(set)
root = Path('/tmp/precision') / os.environ.get('BR_REVERSE', '0')
_NO_RECEIVER = object()


def observe(value, path, binding, kind, receiver=_NO_RECEIVER):
    cls = receiver if isinstance(receiver, type) else type(receiver)
    typed = '' if receiver is _NO_RECEIVER else (cls.__module__, cls.__qualname__)
    key = value if kind == 'key' and type(value) is str else None
    events[path, binding, kind, key, typed].add(trace_events.context)
    return value


def start():
    files = json.loads(Path('/tmp/precision/plan.json').read_bytes())['files']
    if hasattr(builtins, '_blast_radius_observe_read'):
        raise RuntimeError('precision tracer name already bound')
    builtins._blast_radius_observe_read = observe
    marker = root / f'{os.getpid()}.start'
    marker.write_text(trace_events.context, encoding='utf-8')
    atexit.register(lambda: marker.with_suffix('.json').write_text(
        json.dumps([(*fields, sorted(tests)) for fields, tests in events.items()]), encoding='utf-8'))
    original_load = _bootstrap._load_unlocked

    def shared_import(spec):
        previous = trace_events.context
        trace_events.context = '*'
        try:
            return original_load(spec)
        finally:
            trace_events.context = previous

    _bootstrap._load_unlocked = shared_import
    ProcessPoolExecutor.submit = labeled_submit(ProcessPoolExecutor.submit)
    original_code = SourceFileLoader.get_code

    def get_code(loader, fullname):
        filename = loader.get_filename(fullname)
        sites = files.get(filename.removeprefix('/src/'))
        if not filename.startswith('/src/') or not sites:
            return original_code(loader, fullname)
        tree = ast.parse(loader.get_data(filename), filename=filename)
        pending = {tuple(pos): (path, name, kind, recv) for pos, path, name, kind, recv in sites}
        if len(pending) != len(sites):
            raise RuntimeError(f'ambiguous trace positions in {filename}')

        class Instrument(ast.NodeTransformer):
            def generic_visit(self, node):
                node = super().generic_visit(node)
                item = pending.pop(location(node), None) if isinstance(node, ast.expr) else None
                if not item:
                    return node
                path, name, kind, recv = item
                args = [node, ast.Constant(path), ast.Constant(name), ast.Constant(kind)]
                if recv:
                    args.append(ast.Name(id=recv, ctx=ast.Load()))
                return ast.copy_location(ast.Call(ast.Name('_blast_radius_observe_read', ast.Load()), args, []), node)

        result = Instrument().visit(tree)
        if pending:
            raise RuntimeError(f'uninstrumented read sites in {filename}: {pending}')
        return compile(ast.fix_missing_locations(result), filename, 'exec', dont_inherit=True)

    SourceFileLoader.get_code = get_code
