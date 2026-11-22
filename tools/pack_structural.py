"""Generate structural metadata from the verified, unmodified SQLGlot archive."""
import ast
from collections import defaultdict
import gzip
import json
import sys

from generalization import archive, CATALOG, ROOT, PIN, digest, complete_label

sys.path.insert(0, str(ROOT))
from structural import global_readers, plain_test_class, _assertion_literal, SCALARS


def main():
    base = (ROOT/'evidence.gz').read_bytes()
    evidence = json.loads(gzip.decompress(base))
    ids = sorted(t['id'] for t in json.loads(CATALOG.read_bytes())['tests'])
    assert evidence['pin'] == PIN and evidence['ids'] == ids
    with archive() as src:
        sources = {m.name: src.extractfile(m).read().decode('utf-8') for m in src if m.isfile()
                   and m.name.startswith(('sqlglot/', 'tests/')) and m.name.endswith('.py')}
    trees = {p: ast.parse(s) for p, s in sources.items()}
    imports = defaultdict(set)
    modules = set()
    for path, tree in trees.items():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ''
                if node.level:
                    parent = path.split('/')[:-node.level]
                    module = '.'.join(parent + ([module] if module else []))
                for alias in node.names:
                    imports[module, alias.name].add(path)
            elif isinstance(node, ast.Attribute):
                modules.add('attribute:' + node.attr)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                value = node.value
                if value.startswith('sqlglot.') and value.replace('.', '').isidentifier():
                    modules.add(value)
    globals_index = {}
    for path, tree in trees.items():
        if not path.startswith('sqlglot/') or path.count('/') != 1 or path.endswith('/__init__.py'):
            continue
        module = path[:-3].replace('/', '.')
        leaf = module.rsplit('.', 1)[1]
        if module in modules or 'attribute:'+leaf in modules or ('sqlglot', leaf) in imports:
            continue
        for node in tree.body:
            if not (isinstance(node, ast.Assign) and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name) and isinstance(node.value, ast.Constant)
                    and type(node.value.value) in SCALARS):
                continue
            name = node.targets[0].id
            # Aliases in production can be captured by other objects or re-exported.
            if imports.get((module, name)) or imports.get((module, '*')):
                continue
            readers = global_readers(sources[path], name)
            if readers:
                globals_index.setdefault(path, {})[name] = sorted(readers)
    data = dict(version=1, pin=PIN, ids=ids, base_digest=digest(base), globals=globals_index)
    paths = [ROOT/'.phase5'/f'assertions-{order}.json' for order in range(2)]
    if all(p.exists() for p in paths):
        reports = [json.loads(p.read_bytes()) for p in paths]
        catalog = CATALOG.read_bytes()
        assert all(complete_label(r, b'', json.loads(catalog), digest(catalog)) for r in reports)
        uncertain = {ids[i] for i in evidence['hits']['!untraced']}
        assert reports[0]['exit'] == 0 and set(reports[1]['failed']) <= uncertain
        read = set(reports[0]['read']) | set(reports[1]['read'])
        actual = reports[0]['types']
        mentioned = defaultdict(set)
        for path, tree in trees.items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    mentioned[node.id].add(path)
                elif isinstance(node, ast.Attribute):
                    mentioned[node.attr].add(path)
        tests = {}
        for case in ids:
            path, *names = case.split('::')
            if len(names) != 2 or path not in trees or path in read:
                continue
            module = path[:-3].replace('/', '.')
            parent, leaf = module.rsplit('.', 1)
            cls, method = names
            if (module in modules or ('attribute:' + leaf) in modules
                    or (parent, leaf) in imports or any(m == module for m, _ in imports)
                    or any(mentioned[name] - {path} for name in (cls, method))):
                continue
            tree = trees[path]
            if not any(isinstance(n, ast.Import) and any(a.name == 'unittest' and not a.asname for a in n.names)
                       for n in tree.body):
                continue
            for node in tree.body:
                if not plain_test_class(node) or node.name != cls:
                    continue
                for fn in node.body:
                    if not isinstance(fn, ast.FunctionDef) or fn.name != method:
                        continue
                    observation = _assertion_literal(fn)
                    if not observation:
                        continue
                    call, _, value = observation
                    site = f'{path}:{call.lineno}'
                    kind = type(value.value).__name__
                    if actual.get(site) == reports[1]['types'].get(site) == [kind]:
                        tests.setdefault(path, {'source': sources[path], 'assertions': {}})['assertions'][
                            f'{cls}::{method}'] = [call.lineno, kind]
        data['tests'] = tests
        print('assertion candidates', sum(len(record['assertions']) for record in tests.values()))
    (ROOT/'structural.gz').write_bytes(gzip.compress(json.dumps(data, sort_keys=True).encode(), mtime=0))
    print(globals_index)


if __name__ == '__main__':
    main()
