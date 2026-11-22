"""Patch reconstruction and selection against the pinned, read-only evidence."""
import ast
import base64
import dis
import inspect
import difflib
import gzip
import hashlib
import json
import re
import zlib
from pathlib import Path

from impact import changed_files, git_diff_text
from semantic import without_docstrings, classify_change, literal_generator_override, statement_spans
from predicate import comparison_swap
from structural import literal_binding, terminal_assertion
from numeric import (ATTRIBUTE, DECODER, WEEK_OFFSET, decoder_sites, numeric_radix_edit,
                     week_offset_edit, week_offset_sites)

PIN = 'eb11aec4be8cb2122afe713a4816662c3f0fb2fa'


def apply_patch(diff, sources):
    diff = git_diff_text(diff)
    paths = changed_files(diff, require_code=False)
    if not paths or not paths <= sources.keys():
        raise ValueError('unknown path, textual edit or unsupported diff')
    # Git frames the diff with LF. Any CR or other separator in a hunk is payload.
    if not diff.endswith('\n'):
        raise ValueError('unterminated diff')
    lines = [line + '\n' for line in diff[:-1].split('\n')]
    i = 0
    patched = {}
    while i < len(lines):
        path = lines[i].split()[2][2:]
        if path in patched or path not in paths:
            raise ValueError('repeated file')
        *complete, last = sources[path].split('\n')
        original = [line + '\n' for line in complete]
        if last:
            original.append(last)
        result = []
        cursor = 0
        i += 1
        if lines[i].startswith('index '):
            i += 1
        i += 2
        while i < len(lines) and lines[i].startswith('@@'):
            m = re.fullmatch(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@[^\n]*\n?', lines[i])
            if not m:
                raise ValueError('bad hunk')
            old_count, new_count = int(m[2] or 1), int(m[4] or 1)
            pos = int(m[1]) - bool(old_count)
            if not cursor <= pos <= len(original):
                raise ValueError('old position')
            result.extend(original[cursor:pos])
            if len(result) != int(m[3]) - bool(new_count):
                raise ValueError('new position')
            cursor = pos
            i += 1
            while i < len(lines) and lines[i][0] in ' +-':
                kind, value = lines[i][0], lines[i][1:]
                if i + 1 < len(lines) and lines[i+1] == '\\ No newline at end of file\n':
                    value = value[:-1]
                    i += 1
                if kind != '+':
                    if cursor >= len(original) or original[cursor] != value:
                        raise ValueError('context mismatch')
                    cursor += 1
                if kind != '-':
                    result.append(value)
                i += 1
            if i < len(lines) and not lines[i].startswith(('diff --git ', '@@')):
                raise ValueError('unsupported hunk trailer')
        result.extend(original[cursor:])
        if any(not line.endswith('\n') for line in result[:-1]):
            raise ValueError('missing newline before end of file')
        patched[path] = ''.join(result)
    return patched


BLOCK_DELIMITER = re.compile(r'/\*|\*/')
# ast.parse on decoded text ignores PEP 263 cookies, so any cookie-like line falls back.
ENCODING_COOKIE = re.compile(r'coding[:=]')


def touches_block_comment(old, new):
    """True when an edited line holds a block-comment delimiter.

    Otherwise both versions share the same delimiter sequence, so block-comment
    spans match on both sides and removing them cannot hide a comment edit.
    """
    before, after = old.splitlines(), new.splitlines()
    matcher = difflib.SequenceMatcher(None, before, after, autojunk=False)
    return any(BLOCK_DELIMITER.search(line)
               for tag, i1, i2, j1, j2 in matcher.get_opcodes() if tag != 'equal'
               for line in before[i1:i2] + after[j1:j2])


def sql_without_comments(text):
    """Over-approximate comment removal; a comment-only edit always compares equal."""
    text = re.sub(r'/\*.*?(?:\*/|\Z)', '', text, flags=re.S)
    return re.sub(r'\s+', '', re.sub(r'(?m)(?:--|#).*$', '', text))


# Shared machinery: structural edits here always select the full suite.
CORE = frozenset({'sqlglot/parser.py', 'sqlglot/generator.py', 'sqlglot/tokens.py',
                  'sqlglot/dialects/dialect.py', 'sqlglot/expressions/core.py'})


def is_core(path):
    return path in CORE or path.endswith('/__init__.py')


def tests_of(encoded):
    """Decode an index list, or a base64 little-endian bitset for large sets."""
    if encoded is None:
        return set()
    if isinstance(encoded, list):
        return set(encoded)
    bits = int.from_bytes(base64.b64decode(encoded), 'little')
    return {i for i in range(bits.bit_length()) if bits >> i & 1}


def class_index(evidence):
    """Subclass and import-read lookups, built once per loaded index."""
    index = evidence.get('_index')
    if index is None:
        children, imports = {}, {}
        for cls, bases in evidence['M'].items():
            for base in bases:
                children.setdefault(base, set()).add(cls)
        for key, consumers in evidence['I'].items():
            imports.setdefault(key.rpartition('@')[0], []).append((key, consumers))
        index = evidence['_index'] = (children, imports)
    return index


def family(cls, children):
    found, pending = set(), [cls]
    while pending:
        current = pending.pop()
        if current not in found:
            found.add(current)
            pending.extend(children.get(current, ()))
    return found


def holders(cls, attr, body_read, evidence, stable_registry_key=False):
    """Classes that may hold state derived from cls.attr at import, or None.

    Starts from the consumers of import-time reads of the attribute (or of the
    class __dict__); a class whose own body reads the name holds derived state
    itself. Every holder's import-time reads propagate in turn. A read outside
    any class body or metaclass, at <module> level, cannot be bounded.
    """
    _, imports = class_index(evidence)
    found = {cls}
    pending = list(evidence['I'].get(cls + '@' + attr, ())) + list(evidence['I'].get(cls + '@__dict__', ()))
    if body_read:
        pending.append(cls)
    processed = set()
    while pending:
        current = pending.pop()
        if current == '<module>':
            return None
        if current in processed:
            continue
        processed.add(current)
        found.add(current)
        for key, consumers in imports.get(current, ()):
            # Expr.__init_subclass__ sets key from the class name and derives required_args
            # separately. EXPR_CLASSES still registers the same class under the same key.
            # Expr.__init_subclass__ derives key from the class name alone, so an arg_types
            # edit cannot change any registry key built from it at module level.
            if stable_registry_key and key.endswith('@key') and key.startswith('sqlglot/expressions/'):
                pending.extend(consumer for consumer in consumers if consumer != '<module>')
            else:
                pending.extend(consumers)
    return found


def class_attribute_tests(data, path, changes, isolated=False):
    """Tests that may observe new values of class-level attributes, or None with a reason.

    (a) An attribute read at import, or by the class body itself, selects every
    test that touched a holder of derived state or one of its subclasses.
    (b) Otherwise the runtime readers of the attribute, found through the
    class that provides it, are selected. Runtime class writes and tests that
    changed sqlglot caches turn (b) into (a), since later tests may reuse
    state built from the attribute.
    (c) Classes without evidence and attributes no test read fall back.
    """
    evidence = data.get('classes')
    if not evidence:
        return None, 'class_evidence'
    children = class_index(evidence)[0]
    receivers, reads = evidence['R'], evidence['A']
    chosen = set()
    for change in changes:
        cls = path + '::' + change['cls']
        if cls not in evidence['M'] or cls not in receivers:
            return None, 'unobserved_class'
        attr, generic = cls + '@' + change['attr'], cls + '@__dict__'
        written = any(k + '@' + change['attr'] in evidence['W'] for k in family(cls, children))
        if (change['body_read'] or written or attr in evidence['I'] or generic in evidence['I']
                or attr in evidence['K'] or generic in evidence['K']):
            stable_registry_key = (
                change['attr'] == 'arg_types' and path.startswith('sqlglot/expressions/') and not is_core(path)
                and not change['body_read']
            )
            found = holders(cls, change['attr'], change['body_read'], evidence, stable_registry_key)
            if found is None:
                return None, 'import_module_read'
            for holder in found:
                if holder.startswith('tests/'):
                    prefix = holder + '::'
                    chosen.update(i for i, name in enumerate(data['ids']) if name.startswith(prefix))
                    continue
                for member in family(holder, children):
                    chosen |= tests_of(receivers.get(member))
        else:
            readers = tests_of(reads.get(attr)) | tests_of(reads.get(generic))
            if not readers:
                return None, 'unobserved_attribute'
            chosen |= readers
    return chosen, 'observed'


def holder_receivers(data, found, evidence):
    children = class_index(evidence)[0]
    chosen = set()
    for holder in found:
        if holder.startswith('tests/'):
            prefix = holder + '::'
            chosen.update(i for i, name in enumerate(data['ids']) if name.startswith(prefix))
            continue
        for member in family(holder, children):
            chosen |= tests_of(evidence['R'].get(member))
    return chosen


HARMLESS_CALLS = frozenset({'isinstance', 'issubclass', 'len', 'dict', 'list', 'tuple', 'set', 'frozenset',
                            'str', 'sorted', 'getattr', 'hasattr', 'callable'})


def module_path(path, module, level, sources):
    if level:
        parts = path.split('/')[:-level]
        module = '.'.join(parts + ([module] if module else []))
    for candidate in (module.replace('.', '/') + '.py', module.replace('.', '/') + '/__init__.py'):
        if candidate in sources:
            return candidate
    return None


_TREES = {}


def parsed(path, sources):
    """Parse a pinned module once per process."""
    text = sources[path]
    key = (path, hash(text))
    tree = _TREES.get(key)
    if tree is None:
        tree = _TREES[key] = ast.parse(text)
    return tree


def resolve_function(path, node, sources):
    """The pinned top-level FunctionDef named by a Name or module attribute, and its module."""
    tree = parsed(path, sources)
    if isinstance(node, ast.Name):
        for statement in tree.body:
            if isinstance(statement, ast.FunctionDef) and statement.name == node.id:
                return statement, path
            if isinstance(statement, ast.ImportFrom):
                for alias in statement.names:
                    if (alias.asname or alias.name) == node.id:
                        target = module_path(path, statement.module or '', statement.level, sources)
                        return (resolve_function(target, ast.Name(id=alias.name), sources)
                                if target else (None, None))
    elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        for statement in tree.body:
            if isinstance(statement, ast.ImportFrom) and not statement.level:
                for alias in statement.names:
                    if (alias.asname or alias.name) == node.value.id:
                        target = module_path(path, f'{statement.module}.{alias.name}', 0, sources)
                        return resolve_function(target, ast.Name(id=node.attr), sources) if target else (None, None)
            if isinstance(statement, ast.Import):
                for alias in statement.names:
                    if alias.asname == node.value.id or (not alias.asname and alias.name == node.value.id):
                        target = module_path(path, alias.name, 0, sources)
                        return resolve_function(target, ast.Name(id=node.attr), sources) if target else (None, None)
    return None, None


def pure_decorator(path, text, sources):
    """True for a decorator whose application can only build and return local functions."""
    node = ast.parse(text, mode='eval').body
    if isinstance(node, ast.Call):
        if node.keywords or any(isinstance(a, ast.Starred) for a in node.args) or not all(
                _literal_node(a) for a in node.args):
            return False
        node = node.func
    function, where = resolve_function(path, node, sources)
    if function is None:
        return False
    wraps_imported = any(isinstance(n, ast.ImportFrom) and n.module == 'functools'
                         and any(a.name == 'wraps' and not a.asname for a in n.names)
                         for n in parsed(where, sources).body)
    local = set()
    for sub in ast.walk(function):
        if isinstance(sub, (ast.Global, ast.Nonlocal, ast.ClassDef, ast.Import, ast.ImportFrom, ast.Delete,
                            ast.Yield, ast.YieldFrom, ast.Await, ast.Lambda)):
            return False
        if isinstance(sub, ast.arg):
            local.add(sub.arg)
        elif isinstance(sub, ast.Name) and not isinstance(sub.ctx, ast.Load):
            local.add(sub.id)
        elif isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
            local.add(sub.name)

    def root(target):
        while isinstance(target, (ast.Attribute, ast.Subscript, ast.Starred)):
            target = target.value
        return target.id if isinstance(target, ast.Name) else None

    for sub in ast.walk(function):
        targets = (sub.targets if isinstance(sub, ast.Assign) else [sub.target]
                   if isinstance(sub, (ast.AugAssign, ast.AnnAssign, ast.For, ast.comprehension)) else [])
        for target in targets:
            for name in (t for t in ast.walk(target) if isinstance(t, (ast.Attribute, ast.Subscript))):
                if root(name) not in local:
                    return False
        if isinstance(sub, ast.Call):
            callee = sub.func
            if isinstance(callee, ast.Name):
                if not (callee.id in local or callee.id in HARMLESS_CALLS or (callee.id == 'wraps' and wraps_imported)):
                    return False
            elif root(callee) not in local:
                return False
    return True


def _literal_node(node):
    try:
        ast.literal_eval(node)
        return True
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return False


GLOBAL_LOADS = frozenset({'LOAD_GLOBAL', 'LOAD_NAME', 'LOAD_FROM_DICT_OR_GLOBALS', 'STORE_GLOBAL', 'DELETE_GLOBAL',
                          'STORE_NAME', 'DELETE_NAME'})


def _bindings_of(statement):
    """Name -> binding signature of a top-level literal assignment or from-import."""
    if (isinstance(statement, ast.Assign) and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name) and _literal_node(statement.value)):
        return {statement.targets[0].id: ('literal', type(ast.literal_eval(statement.value)).__name__)}
    if isinstance(statement, ast.ImportFrom) and statement.names and all(a.name != '*' for a in statement.names):
        return {a.asname or a.name: ('import', statement.module, statement.level, a.name) for a in statement.names}
    return None


def _reflects_namespace(tree):
    """True when a module can read or write its own globals by computed name."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in ('globals', 'locals', 'exec', 'eval', '__import__') or (
                    node.func.id == 'vars' and not node.args):
                return True
        if isinstance(node, ast.Attribute) and node.attr == 'modules' and isinstance(node.value, ast.Name) \
                and node.value.id == 'sys':
            return True
        if isinstance(node, ast.Name) and node.id == '__dict__':
            return True
    return False


def module_binding_tests(data, path, old, new):
    """Tests reaching functions that load changed top-level bindings of a module, or None.

    Supported edits change literal assignment values (same type) or the names a
    from-import binds, with the same source modules. Readers come from pinned
    bytecode; an import-time or class-body read, a rebinding, namespace reflection
    or any other module importing or attribute-reading the name falls back.
    """
    sources = data['sources']
    before, after = ast.parse(old), ast.parse(new)
    if len(before.body) != len(after.body):
        return None
    changed = set()
    for a, b in zip(before.body, after.body):
        if ast.dump(a) == ast.dump(b):
            continue
        x, y = _bindings_of(a), _bindings_of(b)
        if x is None or y is None or type(a) is not type(b):
            return None
        if isinstance(a, ast.ImportFrom):
            if (a.module, a.level) != (b.module, b.level):
                return None
            target = module_path(path, a.module or '', a.level, sources)
            if target is None or is_core(target):
                return None
            defined = {n for st in parsed(target, sources).body for n in (
                [st.name] if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                else [t.id for t in getattr(st, 'targets', []) if isinstance(t, ast.Name)]
                + [al.asname or al.name for al in getattr(st, 'names', []) if isinstance(st, (ast.Import, ast.ImportFrom))])}
            if any(entry[3] not in defined for entry in y.values()):
                return None
        elif x.keys() != y.keys() or x != y:
            return None
        changed |= {name for name in x.keys() | y.keys() if x.get(name) != y.get(name) or isinstance(a, ast.Assign)}
    if not changed:
        return None
    if _reflects_namespace(before):
        return None
    for name in changed:
        if sum(name in (_bindings_of(st) or {}) or getattr(st, 'name', None) == name for st in before.body) != 1:
            return None
    readers = _binding_readers(path, old, changed)
    if readers is None:
        return None
    hits = data['hits']
    chosen = set()
    observed = [path + '::' + reader for reader in readers]
    # Other modules: follow imported copies and module attribute reads one level.
    tokens = re.compile(r'\b(' + '|'.join(map(re.escape, sorted(changed))) + r')\b')
    tests = data.get('test_evidence', {})
    others = dict(sources) | tests.get('sources', {})
    ids = data['ids']
    for other, text in others.items():
        if other == path or not other.endswith('.py') or not (tokens.search(text) or 'import *' in text):
            continue
        copies, attributes = _imports_of(other, parsed(other, others), path, changed, others)
        if copies is None:
            return None
        if not copies and not attributes:
            continue
        if other.startswith('tests/'):
            if other.rsplit('/', 1)[-1] in ('conftest.py', '__init__.py'):
                return None
            files = {other} | set(tests.get('importers', {}).get(other, ()))
            chosen.update(i for i, name in enumerate(ids) if name.split('::')[0] in files)
            continue
        if is_core(other) or other not in sources:
            return None
        found = _binding_readers(other, text, copies, attributes)
        if found is None:
            return None
        observed.extend(other + '::' + reader for reader in found)
        chosen.update(hits.get(other + '::@importers', ()))
        # A further copy of the alias would need another level; fall back instead.
        for alias in copies:
            if any(alias in t and o not in (other, path) and re.search(r'\b' + re.escape(alias) + r'\b', t)
                   and _imports_of(o, parsed(o, others), other, {alias}, others) != (set(), set())
                   for o, t in others.items() if o.endswith('.py')):
                return None
    # Unread or unobserved readers keep the conservative fallback.
    if not observed or not all(hits.get(key) for key in observed):
        return None
    for key in observed:
        chosen.update(hits[key])
    return chosen


def _imports_of(file, tree, path, names, sources):
    """Local aliases of names imported from path, and local names bound to path's module.

    Returns (None, None) for a star import or a reflective use of the module.
    """
    copies, modules = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            target = module_path(file, node.module or '', node.level, sources)
            for alias in node.names:
                if target == path and alias.name == '*':
                    return None, None
                if target == path and alias.name in names:
                    copies.add(alias.asname or alias.name)
                if module_path(file, f'{node.module}.{alias.name}' if node.module else alias.name,
                               node.level, sources) == path:
                    modules.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if module_path(file, alias.name, 0, sources) == path:
                    modules.add(alias.asname or alias.name.split('.')[0])
    attributes = set()
    if modules:
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in names:
                attributes.add(node.attr)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in (
                    'getattr', 'vars', 'setattr', 'dir') and any(
                    isinstance(arg, ast.Name) and arg.id in modules for arg in node.args):
                return None, None
    return copies, attributes


def _binding_readers(path, source, names, attributes=()):
    """Qualified names of runtime code objects reading names, or None for import-time reads."""
    readers = set()
    code_objects = [compile(source, path, 'exec', dont_inherit=True)]
    while code_objects:
        code = code_objects.pop()
        code_objects.extend(c for c in code.co_consts if hasattr(c, 'co_code'))
        instructions = list(dis.get_instructions(code))
        top = code.co_qualname == '<module>'
        reads = any((i.opname in GLOBAL_LOADS and i.argval in names and not i.opname.startswith(('STORE', 'DELETE')))
                    or (i.opname == 'IMPORT_FROM' and i.argval in names and not top)
                    or (i.opname in ('LOAD_ATTR', 'LOAD_METHOD') and i.argval in attributes)
                    for i in instructions)
        if not reads:
            continue
        # Module and class bodies run at import; their reads may persist in derived state.
        if top or not code.co_flags & inspect.CO_OPTIMIZED:
            return None
        if any(i.opname in ('STORE_GLOBAL', 'DELETE_GLOBAL') and i.argval in names for i in instructions):
            return None
        readers.add(code.co_qualname)
    return readers


def member_tests(data, path, members):
    """Tests reaching changed definition headers or a class that gains or loses a method.

    A header edit of an existing function (literal defaults, unchanged
    decorators) is observed only through calls of that code object. An added
    or removed method changes attribute lookup on its class, so every test
    that touched the class, a subclass or a holder of its import-time state
    is selected; a module-level import read falls back.
    """
    hits, evidence = data['hits'], data.get('classes')
    chosen = set()
    for record in members:
        if record[0] == 'header':
            key = path + '::' + record[1]
            if not hits.get(key):
                return None, 'unobserved_scope'
            chosen.update(hits[key])
            continue
        if is_core(path) or not evidence:
            return None, 'structural_or_text'
        cls = path + '::' + record[1]
        if cls not in evidence['M'] or cls not in evidence['R']:
            return None, 'unobserved_class'
        if not all(pure_decorator(path, text, data['sources']) for text in record[3]):
            return None, 'structural_or_text'
        children = class_index(evidence)[0]
        if any(k + '@' + record[2] in evidence['W'] for k in family(cls, children)):
            return None, 'class_write'
        # Import-time reads through this class were attributed to the ancestor that
        # supplied the name before the edit.
        ancestors, pending = set(), list(evidence['M'][cls])
        while pending:
            current = pending.pop()
            if current not in ancestors:
                ancestors.add(current)
                pending.extend(evidence['M'].get(current, ()))
        consumers = {c for a in ancestors for c in evidence['I'].get(a + '@' + record[2], ())}
        if '<module>' in consumers:
            return None, 'import_module_read'
        found = holders(cls, record[2], True, evidence)
        for consumer in consumers:
            extra = holders(consumer, '', True, evidence) if found is not None else None
            found = None if extra is None else found | extra
        if found is None:
            return None, 'import_module_read'
        chosen |= holder_receivers(data, found, evidence)
    return chosen, 'structure'


MUTATORS = frozenset({'append', 'extend', 'insert', 'pop', 'popitem', 'remove', 'clear', 'update',
                      'setdefault', 'add', 'discard', 'sort', 'reverse', '__setitem__', '__delitem__'})


def _outside_functions(node):
    """Nodes executed by node itself, without descending into nested function bodies."""
    pending = [node]
    while pending:
        current = pending.pop()
        yield current
        for child in ast.iter_child_nodes(current):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                pending.extend(child.decorator_list + child.args.defaults + [d for d in child.args.kw_defaults if d])
            elif not isinstance(child, ast.Lambda):
                pending.append(child)


def writes_shared_state(nodes):
    """True when code may change state that outlives its own frame or test instance."""
    for node in nodes:
        local = {a.arg for a in ast.walk(node) if isinstance(a, ast.arg)} | {
            n.id for n in ast.walk(node) if isinstance(n, ast.Name) and not isinstance(n.ctx, ast.Load)}
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            local = set()

        def root(target):
            while isinstance(target, (ast.Attribute, ast.Subscript, ast.Starred)):
                target = target.value
            return target.id if isinstance(target, ast.Name) else None

        for sub in (ast.walk(node) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else _outside_functions(node)):
            if isinstance(sub, (ast.Global, ast.Nonlocal)):
                return True
            targets = (sub.targets if isinstance(sub, (ast.Assign, ast.Delete)) else [sub.target]
                       if isinstance(sub, (ast.AugAssign, ast.AnnAssign)) else [])
            for target in targets:
                for part in ast.walk(target):
                    if isinstance(part, (ast.Attribute, ast.Subscript)) and root(part) not in local:
                        return True
            if isinstance(sub, ast.Call):
                callee = sub.func
                if isinstance(callee, ast.Name) and callee.id in ('setattr', 'delattr', 'exec', 'eval', '__import__'):
                    return True
                if isinstance(callee, ast.Attribute) and callee.attr in MUTATORS and root(callee) not in local:
                    return True
    return False


def test_module_tests(data, path, original, new):
    """Tests that may observe an edit of a pinned test module, or None with a reason.

    Collection-wide files fall back. A module edit selects its own tests and every
    test module that imports it; an edit confined to test method bodies selects
    those tests (including inherited copies in the same module) plus importers.
    New code that writes non-local state could leak into later tests and falls back.
    """
    if path.rsplit('/', 1)[-1] in ('conftest.py', '__init__.py'):
        return None, 'test_structure'
    importers = set(data['test_evidence']['importers'].get(path, ()))
    ids = data['ids']
    own = {i for i, name in enumerate(ids) if name.startswith(path + '::')}
    imported = {i for i, name in enumerate(ids) if name.split('::')[0] in importers}
    try:
        compile(new, path, 'exec', dont_inherit=True)
        change = classify_change(original, new)
        before, after = ast.parse(original), ast.parse(new)
    except (SyntaxError, ValueError, RecursionError):
        # The module and its importers fail to import, which fails exactly their tests.
        return own | imported, 'test_module'
    if change['ast_equal']:
        return set(), 'comment_only'
    old_nodes = {ast.dump(n) for n in ast.walk(before) if isinstance(n, ast.stmt)}
    changed = [n for n in ast.walk(after) if isinstance(n, ast.stmt) and ast.dump(n) not in old_nodes]
    functions = [n for n in ast.walk(after) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and any(c in set(ast.walk(n)) for c in changed)]
    if writes_shared_state([n for n in changed if not any(n in set(ast.walk(f)) for f in functions)] + functions):
        return None, 'test_state'
    if not own:
        return imported, 'test_module'
    if change['structural'] or not change['functions']:
        return own | imported, 'test_module'
    targets = set()
    for qualname in change['functions']:
        method = qualname.split('.')[-1]
        loads = sum(isinstance(n, (ast.Attribute, ast.Name)) and getattr(n, 'attr', getattr(n, 'id', None)) == method
                    for tree in (before, after) for n in ast.walk(tree))
        matches = {i for i in own if ids[i].endswith('::' + method)}
        if loads or not method.startswith('test') or '<locals>' in qualname or not matches:
            return own | imported, 'test_module'
        targets |= matches
    return targets | imported, 'test_method'


def configuration_members(evidence, cls, base, attr, allow_dialect_import=False):
    children, _ = class_index(evidence)
    if cls not in family(base, children):
        return None
    members = family(cls, children)
    for member in members:
        assigned, generic = member + '@' + attr, member + '@__dict__'
        if assigned in evidence['W'] or generic in evidence['W']:
            return None
        if any(not allow_dialect_import or not owner.startswith('sqlglot/dialects/')
               for owner in evidence['I'].get(assigned, ())):
            return None
        if any(owner not in members for owner in evidence['I'].get(generic, ())):
            return None
    return members


def numeric_escape_tests(data, path, old, new, change):
    """Select numeric decoder users when a literal map's import-time keys stay fixed."""
    if change['attr'] != ATTRIBUTE or change['body_read'] or not path.startswith('sqlglot/dialects/'):
        return None
    evidence = data.get('classes')
    lines = data.get('line_evidence')
    if not evidence or not lines or DECODER not in lines['files']:
        return None
    cls = path + '::' + change['cls']
    if not numeric_radix_edit(old, new, change['cls']):
        return None
    # The pinned dialect initializer uses only key presence.
    members = configuration_members(
        evidence, cls, 'sqlglot/tokens.py::Tokenizer', ATTRIBUTE, allow_dialect_import=True,
    )
    if not members:
        return None

    sites = decoder_sites(data['sources'][DECODER])
    if len(sites) != 2:
        return None
    readers = set()
    for line, scope in sites:
        group = lines['files'][DECODER].get(str(line))
        if group is not None:
            readers.update(lines['groups'][group])
        else:
            # A byte decoder may never be entered in the pinned suite. Keep its
            # existing function evidence whenever exact line evidence is absent.
            readers.update(data['hits'].get(DECODER + '::' + scope, ()))
    if not readers or -1 in readers:
        return None
    for member in members:
        readers.update(tests_of(evidence['A'].get(member + '@__dict__')))
    return readers | set(lines['extra'])


def week_offset_tests(data, path, old, new, change):
    """Trace local arithmetic and generation that consumes a pinned scalar offset."""
    if change['attr'] != WEEK_OFFSET or change['body_read'] or not path.startswith('sqlglot/dialects/'):
        return None
    evidence = data.get('classes')
    lines = data.get('line_evidence')
    if not evidence or not lines or not week_offset_edit(old, new, change['cls']):
        return None
    cls = path + '::' + change['cls']
    members = configuration_members(evidence, cls, 'sqlglot/dialects/dialect.py::Dialect', WEEK_OFFSET)
    if not members:
        return None
    sites = week_offset_sites(data['sources'])
    if len(sites) != 5:
        return None
    readers = set()
    for filename, line in sites:
        group = lines['files'].get(filename, {}).get(str(line))
        if group is None:
            return None
        readers.update(lines['groups'][group])
    if not readers or -1 in readers:
        return None
    for member in members:
        readers.update(tests_of(evidence['A'].get(member + '@__dict__')))
    return readers | set(lines['extra'])


def load(tests):
    try:
        base = Path(__file__).with_name('evidence.gz').read_bytes()
        data = json.loads(gzip.decompress(base))
        if data['schema'] == 1 and data['pin'] == PIN and sorted(t['id'] for t in tests) == data['ids']:
            digest = hashlib.sha256(base).hexdigest()
            for filename, key in (('lines.gz', 'line_evidence'), ('predicates.gz', 'predicate_evidence'),
                                  ('structural.gz', 'structural_evidence'), ('tests.gz', 'test_evidence')):
                try:
                    auxiliary = json.loads(gzip.decompress(Path(__file__).with_name(filename).read_bytes()))
                    if (auxiliary['version'] == 1 and auxiliary['pin'] == PIN and auxiliary['ids'] == data['ids']
                            and auxiliary['base_digest'] == digest):
                        data[key] = auxiliary
                except (OSError, EOFError, ValueError, KeyError, TypeError, zlib.error):
                    pass
            return data
    except (OSError, EOFError, ValueError, KeyError, TypeError, zlib.error):
        pass
    return None


def statement_tests(old, new, path, evidence):
    files = evidence['files']
    if path not in files:
        return None
    spans = statement_spans(old, new)
    if not spans:
        return None
    lines = files[path]
    candidates = set(evidence['extra'])
    for start, end in spans:
        groups = {lines[str(n)] for n in range(start, end + 1) if str(n) in lines}
        if not groups:
            return None
        for group in groups:
            candidates.update(evidence['groups'][group])
    return candidates if -1 not in candidates else None


def generator_override_tests(data, path, old, new):
    """Retain receivers when a leaf generator changes one dispatch slot."""
    base_path = 'sqlglot/generator.py'
    evidence = data.get('classes')
    if not evidence or not path.startswith('sqlglot/generators/') or base_path not in data['sources']:
        return None
    override = literal_generator_override(old, new, data['sources'][base_path])
    if override is None:
        return None
    name, method = override
    cls, base = path + '::' + name, base_path + '::Generator'
    children, _ = class_index(evidence)
    if evidence['M'].get(cls) != [base] or children.get(cls):
        return None
    keys = tuple(owner + '@' + attr for owner in (cls, base) for attr in (method, '__dict__'))
    if any(key in evidence['I'] or key in evidence['W'] for key in keys):
        return None
    return tests_of(evidence['R'].get(cls)) or None


def decide(diff, data, mode='scope'):
    """Return stable IDs, or None to invoke full-suite fallback."""
    if data is None:
        return None, 'catalog'
    structural = data.get('structural_evidence', {})
    sources = data['sources']
    test_sources = structural.get('tests', {})
    if mode == 'scope' and test_sources:
        sources = sources | {path: record['source'] for path, record in test_sources.items()}
    modules = data.get('test_evidence', {}).get('sources', {}) if mode == 'scope' else {}
    if modules:
        sources = modules | sources
    try:
        updates = apply_patch(diff, sources)
    except (ValueError, IndexError):
        return None, 'unsupported_diff'
    hits = data['hits']
    chosen = set(hits.get('!untraced', []))
    if mode == 'scope':
        direct = data.get('line_evidence', {}).get('certified_direct_children', {})
        for index, footprint in direct.items():
            if updates.keys().isdisjoint(footprint):
                chosen.discard(int(index))
    code_changed = False
    statement_selected = False
    predicate_selected = False
    configuration_reason = None
    for path, new in updates.items():
        readers = hits.get(path, [])
        chosen.update(readers)
        if path.startswith('tests/fixtures/') and path.endswith('.sql'):
            # Fixture text, comments and metadata lines included, is observable only by
            # opening the file; shared or missing readers still fall back below.
            code_changed = True
            if not readers:
                return None, 'unobserved_fixture'
        elif path in test_sources:
            original = sources[path]
            try:
                edit = terminal_assertion(original, new) if len(updates) == 1 else None
            except (SyntaxError, ValueError, RecursionError):
                edit = None
            candidate = path + '::' + edit[0] if edit else None
            if (not edit or test_sources[path]['assertions'].get(edit[0]) != list(edit[1:])
                    or candidate not in data['ids']):
                if path not in modules:
                    return None, 'test_structure'
                found, reason = test_module_tests(data, path, original, new)
                if found is None:
                    return None, reason
                chosen.update(found)
                chosen.update(data.get('line_evidence', {}).get('extra', ()))
                configuration_reason = configuration_reason or reason
                code_changed = True
                continue
            chosen.update(hits.get('!untraced', ()))
            chosen.update(data.get('line_evidence', {}).get('extra', ()))
            if -1 in chosen:
                return None, 'shared_or_missing'
            return {candidate} | {data['ids'][i] for i in chosen}, 'test_assertion'
        elif path in modules:
            found, reason = test_module_tests(data, path, modules[path], new)
            if found is None:
                return None, reason
            chosen.update(found)
            chosen.update(data.get('line_evidence', {}).get('extra', ()))
            configuration_reason = configuration_reason or reason
            code_changed = code_changed or reason != 'comment_only'
        elif path.startswith('sqlglot/') and path.endswith('.py'):
            original = data['sources'][path]
            # Python ends lines only at \r\n, \r or \n; str.splitlines also splits at \x0c, \x85, ...
            if any(ENCODING_COOKIE.search(line) for text in (original, new)
                   for line in re.split(r'\r\n|\r|\n', text, maxsplit=2)[:2]):
                return None, 'encoding_cookie'
            try:
                compile(new, path, 'exec', dont_inherit=True)
                change = classify_change(original, new)
            except (SyntaxError, ValueError, RecursionError):
                return None, 'invalid_python'
            if change['ast_equal']:
                # Comment or layout only: bytecode differs at most in line numbers,
                # so only tests that read this source as text can observe it.
                continue
            if mode == 'scope' and without_docstrings(original) == without_docstrings(new):
                # Pinned sqlglot reads docstrings only to keep an Expr class's own __doc__,
                # and no collected test reads __doc__; treat docstring text like comments.
                continue
            code_changed = True
            skipped = set()
            if change['structural']:
                if mode == 'scope' and len(updates) == 1 and not is_core(path):
                    bindings = data.get('structural_evidence', {}).get('globals', {}).get(path, {})
                    readers = bindings.get(literal_binding(original, new)) if bindings else None
                    if readers:
                        keys = [path + '::' + reader for reader in readers]
                        if all(hits.get(key) for key in keys):
                            for key in keys:
                                chosen.update(hits[key])
                            chosen.update(hits.get(path + '::@importers', ()))
                            chosen.update(data.get('line_evidence', {}).get('extra', ()))
                            configuration_reason = 'module_scalar'
                            continue
                if mode == 'scope' and len(updates) == 1 and not change.get('class_attributes'):
                    override = generator_override_tests(data, path, original, new)
                    if override is not None:
                        chosen.update(override)
                        chosen.update(data.get('line_evidence', {}).get('extra', ()))
                        chosen.update(hits.get(path + '::@importers', ()))
                        configuration_reason = 'generator_override'
                        continue
                if mode == 'scope' and not is_core(path) and not change.get('class_attributes') \
                        and not change.get('members'):
                    found = module_binding_tests(data, path, original, new)
                    if found is not None:
                        chosen.update(found)
                        chosen.update(hits.get(path + '::@importers', ()))
                        chosen.update(data.get('line_evidence', {}).get('extra', ()))
                        configuration_reason = configuration_reason or 'module_binding'
                        continue
                members = change.get('members') if mode == 'scope' else None
                if members and not change.get('class_attributes'):
                    found, reason = member_tests(data, path, members)
                    if found is None:
                        return None, reason
                    chosen.update(found)
                    chosen.update(data.get('line_evidence', {}).get('extra', ()))
                    configuration_reason = configuration_reason or 'structure'
                    skipped = {record[1] + '.' + record[2] for record in members if record[0] == 'member'}
                if not members and (not change.get('class_attributes') or is_core(path)):
                    return None, 'structural_or_text'
                isolated = len(updates) == 1 and len(change.get('class_attributes') or ()) == 1 and not change['functions']
                found = set() if members and not change.get('class_attributes') else None
                if found is None and mode == 'scope' and isolated:
                    attribute = change['class_attributes'][0]
                    found = numeric_escape_tests(data, path, original, new, attribute)
                    if found is not None:
                        configuration_reason = 'numeric_values'
                    else:
                        found = week_offset_tests(data, path, original, new, attribute)
                        if found is not None:
                            configuration_reason = 'week_offset'
                if found is None:
                    found, reason = class_attribute_tests(data, path, change['class_attributes'], isolated)
                if found is None:
                    return None, reason
                chosen.update(found)
            elif not change['functions']:
                return None, 'structural_or_text'
            chosen.update(hits.get(path + '::@importers', ()))
            scopes = set()
            for name in change['functions']:
                if any(name == m or name.startswith(m + '.') for m in skipped):
                    continue
                key = path + '::' + name
                if key not in hits:
                    return None, 'unobserved_scope'
                scopes.update(hits[key])
            if mode in ('statement', 'scope') and not change['structural'] and -1 not in scopes:
                lines = data.get('line_evidence')
                statements = statement_tests(original, new, path, lines) if lines else None
                if statements is not None:
                    scopes = statements
                    chosen.update(lines['extra'])
                    statement_selected = True

                # Use agreement only for the same isolated expression edit. Imports,
                # source readers and ambiguous tests have already entered chosen.
                predicate = data.get('predicate_evidence')
                if (mode == 'scope' and len(updates) == 1 and len(change['functions']) == 1
                        and predicate and ('==' in diff or '!=' in diff)
                        and re.search(r'\bis\b', diff)
                        and (statements is not None or statement_spans(original, new))):
                    site = comparison_swap(original, new)
                    group = predicate['keys'].get(f'{path}:{site}') if site else None
                    if group is not None:
                        agreeing = set(predicate['groups'][group])
                        remaining = scopes - agreeing
                        if remaining != scopes:
                            scopes = remaining
                            chosen.update(predicate['extra'])
                            predicate_selected = True
            chosen.update(scopes)
            if mode == 'file':
                for key, ids in hits.items():
                    if key.startswith(path + '::'):
                        chosen.update(ids)
        else:
            return None, 'unknown'
    if -1 in chosen or (code_changed and not chosen):
        return None, 'shared_or_missing'
    reason = (configuration_reason or ( 'predicate' if predicate_selected else 'statement' if statement_selected
              else 'observed' if code_changed else 'comment_only'))
    return {data['ids'][i] for i in chosen}, reason
