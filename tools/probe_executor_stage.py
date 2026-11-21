"""Development-only cost and structure probe for the executor optimizer stage."""
import argparse
from enum import Enum
import json
import os
from pathlib import Path
import sys
import tarfile
import time


def expression_graph(root, expression_type):
    """Preserve argument order, shared references, type metadata and parents."""
    objects = []
    references = {}

    def encode(value):
        kind = type(value)
        if value is None or kind in (str, bool, int, float):
            return [kind.__name__, value]
        if isinstance(value, Enum):
            return [kind.__module__, kind.__qualname__, value.name]
        if not (isinstance(value, expression_type) or kind in (dict, list, tuple)):
            raise TypeError(kind)
        address = id(value)
        if address in references:
            return ['ref', references[address]]
        index = references[address] = len(objects)
        objects.append(None)
        if isinstance(value, expression_type):
            state = [value.args, value.parent, value.arg_key, value.index,
                     value.comments, value._type, value._meta]
            description = [kind.__module__, kind.__qualname__, [encode(v) for v in state]]
        elif kind is dict:
            description = ['dict', [[encode(k), encode(v)] for k, v in value.items()]]
        else:
            description = [kind.__name__, [encode(v) for v in value]]
        objects[index] = description
        return ['ref', index]

    return [encode(root), objects]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('side', choices=('tpch', 'tpcds'))
    parser.add_argument('--patch', type=Path)
    parser.add_argument('--write', type=Path, required=True)
    args = parser.parse_args()
    repository = Path('/repo')
    root = Path('/tmp/pinned-executor')
    root.mkdir()
    with tarfile.open(repository / '.phase5/src.tar') as archive:
        archive.extractall(root, filter='data')
    if args.patch:
        sys.path.insert(0, str(repository))
        from hybrid import apply_patch
        from impact import changed_files
        diff = args.patch.read_text(encoding='utf-8')
        paths = changed_files(diff, require_code=False)
        if not paths or not all(path.startswith('sqlglot/optimizer/') and path.endswith('.py')
                                for path in paths):
            raise ValueError('probe accepts only optimizer source changes')
        originals = {path: (root / path).read_text(encoding='utf-8') for path in paths}
        for path, text in apply_patch(diff, originals).items():
            (root / path).write_text(text, encoding='utf-8')
    sys.path.insert(0, str(root))
    os.chdir(root)
    start = time.process_time()
    from sqlglot import exp, parse_one
    from sqlglot.optimizer import optimize
    from sqlglot.schema import ensure_schema
    from tests.helpers import TPCH_SCHEMA, TPCDS_SCHEMA, load_sql_fixture_pairs

    side, schema = ('tpc-h', TPCH_SCHEMA) if args.side == 'tpch' else ('tpc-ds', TPCDS_SCHEMA)
    normalized = ensure_schema(schema)
    results = []
    for i, (meta, sql, _) in enumerate(load_sql_fixture_pairs(f'optimizer/{side}/{side}.sql'), 1):
        if not meta.get('execute'):
            continue
        result = optimize(parse_one(sql), normalized, leave_tables_isolated=True, dialect=None)
        results.append([i, expression_graph(result, exp.Expr)])
    args.write.write_text(json.dumps(results, separators=(',', ':'), allow_nan=False))
    print(f'{args.side}: {len(results)} optimized expression graphs in {time.process_time()-start:.3f}s CPU')


if __name__ == '__main__':
    main()
