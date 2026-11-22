"""Patch reconstruction and selection against the pinned, read-only evidence."""
import base64
import difflib
import gzip
import hashlib
import json
import re
import zlib
from pathlib import Path

from impact import changed_files
from semantic import classify_change, statement_spans
from predicate import comparison_swap
from numeric import (ATTRIBUTE, DECODER, WEEK_OFFSET, decoder_sites, numeric_radix_edit,
                     week_offset_edit, week_offset_sites)

PIN = 'eb11aec4be8cb2122afe713a4816662c3f0fb2fa'


def apply_patch(diff, sources):
    paths = changed_files(diff, require_code=False)
    if not paths or not paths <= sources.keys():
        raise ValueError('unknown path, textual edit or unsupported diff')
    lines = diff.splitlines(keepends=True)
    i = 0
    patched = {}
    while i < len(lines):
        path = lines[i].split()[2][2:]
        if path in patched or path not in paths:
            raise ValueError('repeated file')
        original = sources[path].splitlines(keepends=True)
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
                if kind != '+':
                    if cursor >= len(original) or original[cursor] != value:
                        raise ValueError('context mismatch')
                    cursor += 1
                if kind != '-':
                    result.append(value)
                i += 1
            if i < len(lines) and not lines[i].startswith(('diff --git ', '@@')):
                raise ValueError('unsupported hunk trailer')
        patched[path] = ''.join(result + original[cursor:])
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
            if stable_registry_key and key == cls + '@key':
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
                isolated and change.get('boolean_schema') and path.startswith('sqlglot/expressions/')
                and evidence['M'][cls] == ['sqlglot/expressions/core.py::Expression']
                and not children.get(cls)
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
            for filename, key in (('lines.gz', 'line_evidence'), ('predicates.gz', 'predicate_evidence')):
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


def decide(diff, data, mode='scope'):
    """Return stable IDs, or None to invoke full-suite fallback."""
    if data is None:
        return None, 'catalog'
    try:
        updates = apply_patch(diff, data['sources'])
    except (ValueError, IndexError):
        return None, 'unsupported_diff'
    hits = data['hits']
    chosen = set(hits.get('!untraced', []))
    code_changed = False
    statement_selected = False
    predicate_selected = False
    configuration_reason = None
    for path, new in updates.items():
        readers = hits.get(path, [])
        chosen.update(readers)
        if path.startswith('tests/fixtures/') and path.endswith('.sql'):
            code_changed = True
            if touches_block_comment(data['sources'][path], new) or (
                    sql_without_comments(data['sources'][path]) == sql_without_comments(new)):
                return None, 'fixture_text'
            if not readers:
                return None, 'unobserved_fixture'
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
            code_changed = True
            if change['structural']:
                if not change.get('class_attributes') or is_core(path):
                    return None, 'structural_or_text'
                isolated = len(updates) == 1 and len(change['class_attributes']) == 1 and not change['functions']
                found = None
                if mode == 'scope' and isolated:
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
