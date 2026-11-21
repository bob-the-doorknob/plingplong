"""Patch reconstruction and selection against the pinned, read-only evidence."""
import difflib
import gzip
import json
import re
import zlib
from pathlib import Path

from impact import changed_files
from semantic import classify_change

PIN = 'eb11aec4be8cb2122afe713a4816662c3f0fb2fa'


def apply_patch(diff, sources):
    paths = changed_files(diff)
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


def load(tests):
    try:
        data = json.loads(gzip.decompress(Path(__file__).with_name('evidence.gz').read_bytes()))
        if data['schema'] == 1 and data['pin'] == PIN and sorted(t['id'] for t in tests) == data['ids']:
            return data
    except (OSError, EOFError, ValueError, KeyError, TypeError, zlib.error):
        pass
    return None


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
    for path, new in updates.items():
        readers = hits.get(path, [])
        chosen.update(readers)
        if path.startswith('tests/fixtures/') and path.endswith('.sql'):
            if touches_block_comment(data['sources'][path], new) or (
                    sql_without_comments(data['sources'][path]) == sql_without_comments(new)):
                return None, 'fixture_text'
            if not readers:
                return None, 'unobserved_fixture'
        elif path.startswith('sqlglot/') and path.endswith('.py'):
            try:
                compile(new, path, 'exec', dont_inherit=True)
                change = classify_change(data['sources'][path], new)
            except (SyntaxError, ValueError, RecursionError):
                return None, 'invalid_python'
            if change['structural'] or not change['functions']:
                return None, 'structural_or_text'
            chosen.update(hits.get(path + '::@importers', ()))
            for name in change['functions']:
                key = path + '::' + name
                if key not in hits:
                    return None, 'unobserved_scope'
                chosen.update(hits[key])
            if mode == 'file':
                for key, ids in hits.items():
                    if key.startswith(path + '::'):
                        chosen.update(ids)
        else:
            return None, 'unknown'
    if -1 in chosen or not chosen:
        return None, 'shared_or_missing'
    return {data['ids'][i] for i in chosen}, 'observed'
