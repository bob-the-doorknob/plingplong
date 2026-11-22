"""Pack pinned test-module sources and static test-module importers into tests.gz."""
import ast
import gzip
import hashlib
import json
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from hybrid import PIN  # noqa: E402

ARCHIVE = ROOT / '.phase5' / 'src.tar'
SHA256 = '578d90b1a8e1130094aaf0746117a596e6d94b63c9e4d38aa74f0fea61a37395'


def module_name(path):
    return path[:-3].replace('/', '.').removesuffix('.__init__')


def imported_modules(path, tree, known):
    """Test modules a test module imports, resolving relative and package-attribute imports."""
    package = module_name(path) if path.endswith('/__init__.py') else module_name(path).rpartition('.')[0]
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split('.')
                found.update('.'.join(parts[:i]) for i in range(1, len(parts) + 1))
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ''
            if node.level:
                parts = package.split('.')[:len(package.split('.')) - node.level + 1]
                base = '.'.join(parts + ([base] if base else []))
            parts = base.split('.')
            found.update('.'.join(parts[:i]) for i in range(1, len(parts) + 1))
            found.update(f'{base}.{alias.name}' for alias in node.names)
    return {known[name] for name in found if name in known and known[name] != path}


def main():
    payload = ARCHIVE.read_bytes()
    if hashlib.sha256(payload).hexdigest() != SHA256:
        raise ValueError('source archive does not match the pinned revision')
    sources = {}
    with tarfile.open(ARCHIVE) as archive:
        if archive.pax_headers.get('comment') != PIN:
            raise ValueError('source archive commit mismatch')
        for member in archive:
            name = member.name
            if member.isfile() and name.startswith('tests/') and name.endswith('.py') and not name.startswith('tests/fixtures/'):
                sources[name] = archive.extractfile(member).read().decode('utf-8')
    known = {module_name(path): path for path in sources}
    direct = {path: set() for path in sources}
    for path, text in sources.items():
        for target in imported_modules(path, ast.parse(text), known):
            direct[target].add(path)
    importers = {}
    for path in sources:
        seen, pending = set(), list(direct[path])
        while pending:
            current = pending.pop()
            if current not in seen:
                seen.add(current)
                pending.extend(direct[current])
        importers[path] = sorted(seen)
    catalog = json.loads((ROOT / 'blast-radius-sample/sample/tests.json').read_text())
    base = hashlib.sha256((ROOT / 'evidence.gz').read_bytes()).hexdigest()
    index = dict(version=1, pin=PIN, ids=sorted(t['id'] for t in catalog['tests']), base_digest=base,
                 sources=sources, importers=importers)
    out = ROOT / 'tests.gz'
    out.write_bytes(gzip.compress(json.dumps(index, sort_keys=True, separators=(',', ':')).encode(), mtime=0))
    print(len(sources), 'test modules', out.stat().st_size, 'bytes')


if __name__ == '__main__':
    main()
