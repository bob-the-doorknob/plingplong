"""Generate structural metadata from the verified, unmodified SQLGlot archive."""
import ast
from collections import defaultdict
import gzip
import json
import sys

from generalization import archive, CATALOG, ROOT, PIN, digest

sys.path.insert(0, str(ROOT))
from structural import global_readers, SCALARS


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
    (ROOT/'structural.gz').write_bytes(gzip.compress(json.dumps(data, sort_keys=True).encode(), mtime=0))
    print(globals_index)


if __name__ == '__main__':
    main()
