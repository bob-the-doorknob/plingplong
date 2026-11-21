"""Experimental file-level dependency analysis, deliberately not enabled in submission.

shortcut: imports do not model arbitrary Python behavior, require pinned-source
and mutation validation before enabling any runtime narrowing.
"""
import ast
import re
import sys
from pathlib import Path


def build_index(root: Path) -> dict:
    """Read source without importing it; flag incomplete/dynamic graphs globally."""
    paths = sorted(p for folder in ('sqlglot', 'tests') for p in (root / folder).rglob('*.py'))
    files = {p.relative_to(root).as_posix(): p for p in paths}
    modules = {name: name[:-3].replace('/', '.').removesuffix('.__init__') for name in files}
    known = set(modules.values())
    reverse = {module: set() for module in known}
    complete = bool(files) and 'sqlglot/__init__.py' in files
    for name, path in files.items():
        module = modules[name]
        package = module if name.endswith('/__init__.py') else module.rpartition('.')[0]
        try:
            tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        except (SyntaxError, UnicodeError, OSError):
            complete = False
            continue
        dependencies = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                called = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, 'attr', '')
                if called in {'__import__', 'import_module', 'exec', 'eval', 'getattr'}:
                    complete = False
            if isinstance(node, ast.Import):
                dependencies.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ''
                if node.level:
                    parts = package.split('.')
                    if node.level > len(parts):
                        complete = False
                        continue
                    base = '.'.join(parts[:len(parts)-node.level+1] + ([base] if base else []))
                dependencies.add(base)
                dependencies.update(f'{base}.{alias.name}' for alias in node.names if f'{base}.{alias.name}' in known)
        for dependency in dependencies:
            if dependency in known:
                parts = dependency.split('.')
                for end in range(1, len(parts)+1):
                    parent = '.'.join(parts[:end])
                    if parent in reverse:
                        reverse[parent].add(module)
            elif dependency.split('.')[0] not in sys.stdlib_module_names:
                complete = False
    return {'files': modules, 'reverse': {m: sorted(users) for m, users in sorted(reverse.items())}, 'complete': complete}


def changed_files(diff: str, require_code: bool = True) -> set[str] | None:
    """Accept ordinary same-path textual Git diffs; everything else falls back.

    With require_code, a diff whose changed lines are all blank or start with
    '#' also falls back. The hybrid selector disables this textual check and
    decides comment-only edits on the AST instead.
    """
    lines = diff.splitlines()
    paths, changed = set(), []
    i = 0
    while i < len(lines):
        header = re.fullmatch(r'diff --git a/(\S+) b/(\S+)', lines[i])
        if not header or header[1] != header[2] or '..' in header[1].split('/'):
            return None
        path = header[1]
        i += 1
        if i < len(lines) and lines[i].startswith('index '):
            i += 1
        if lines[i:i+2] != [f'--- a/{path}', f'+++ b/{path}']:
            return None
        i += 2
        hunks = 0
        while i < len(lines) and lines[i].startswith('@@'):
            match = re.fullmatch(r'@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@.*', lines[i])
            if not match:
                return None
            old, new = int(match[1] or 1), int(match[2] or 1)
            i += 1
            while i < len(lines) and not lines[i].startswith(('@@', 'diff --git ')):
                line = lines[i]
                if line == '\\ No newline at end of file':
                    i += 1
                    continue
                if not line or line[0] not in ' +-':
                    return None
                old -= line[0] in ' -'
                new -= line[0] in ' +'
                if line[0] in '+-':
                    changed.append(line[1:].strip())
                i += 1
            if old != 0 or new != 0:
                return None
            hunks += 1
        if not hunks:
            return None
        paths.add(path)
    if not paths or (require_code and not any(line and not line.startswith('#') for line in changed)):
        return None
    return paths


def select_tests(diff: str, tests: list[dict], index: dict | None) -> list[int]:
    """Experimental transitive candidates, or all actual numbers on uncertainty."""
    all_numbers = sorted(t['number'] for t in tests)
    paths = changed_files(diff)
    if not index or not index.get('complete') or not paths:
        return all_numbers
    files, reverse = index['files'], index['reverse']
    if any(t.get('file') not in files for t in tests):
        return all_numbers
    broad = {'sqlglot/parser.py', 'sqlglot/generator.py', 'sqlglot/tokens.py', 'sqlglot/expressions.py'}
    if any(p not in files or not p.startswith('sqlglot/') or p.endswith('/__init__.py')
           or p in broad or p.startswith('sqlglot/dialects/') for p in paths):
        return all_numbers
    affected = {files[p] for p in paths}
    pending = list(affected)
    while pending:
        for user in reverse.get(pending.pop(), []):
            if user not in affected:
                affected.add(user)
                pending.append(user)
    selected = [t['number'] for t in tests if files[t['file']] in affected]
    return sorted(selected) if selected else all_numbers
