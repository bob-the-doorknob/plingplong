"""Generate, label and score independent pinned-source mutations outside the image."""
import argparse
from collections import defaultdict
import difflib
import hashlib
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / '.phase5' / 'generalization'
ARCHIVE = ROOT / '.phase5' / 'src.tar'
PIN = 'eb11aec4be8cb2122afe713a4816662c3f0fb2fa'
SHA256 = '578d90b1a8e1130094aaf0746117a596e6d94b63c9e4d38aa74f0fea61a37395'
CATALOG = ROOT / 'blast-radius-sample/sample/tests.json'

# An exact original anchor makes each edit reproducible. Leave holdout labels
# closed during implementation and compare them only after fixing the rule.
SERDE = 'sqlglot/serde.py'
TRIE = 'sqlglot/trie.py'
SQLITE = 'sqlglot/generators/sqlite.py'
EXECUTOR = 'sqlglot/executor/context.py'
INIT = 'sqlglot/__init__.py'
FIXTURE = 'tests/fixtures/optimizer/eliminate_joins.sql'
TIME_TEST = 'tests/test_time.py'
BUFFER = 'sqlglot/optimizer/eliminate_joins.py'
CASES = {
    'serde_body': ('function_body', 'dev', [(SERDE, '    i = 0\n    payloads:', '    i = 1\n    payloads:')]),
    'executor_guard': ('control_flow', 'dev', [(EXECUTOR, 'if self._table is None:', 'if self._table is not None:')]),
    'serde_global': ('module_global', 'dev', [(SERDE, 'INDEX = "i"', 'INDEX = "v"')]),
    'executor_columns_guard': ('control_flow', 'holdout', [(EXECUTOR,
        'return self.table.columns if self.tables else ()', 'return self.table.columns if not self.tables else ()')]),
    'pretty_global': ('module_global', 'holdout', [(INIT, 'pretty = False', 'pretty = True')]),
    'sqlite_class_flag': ('class_constant', 'dev', [('sqlglot/dialects/sqlite.py', 'TYPED_DIVISION = True', 'TYPED_DIVISION = False')]),
    'time_import': ('imports', 'holdout', [('sqlglot/time.py', 'TrieResult, in_trie, new_trie', 'TrieResult, new_trie as in_trie, new_trie')]),
    'trie_default': ('signature', 'dev', [(TRIE, 'trie: t.Optional[dict] = None', 'trie: t.Optional[dict] = False')]),
    'sqlite_override': ('method_added', 'dev', [(SQLITE, '    def trunc_sql(', '    def select_sql(self, expression):\n        return "SELECT 0"\n\n    def trunc_sql(')]),
    'sqlite_tail_override': ('method_added', 'dev', [(SQLITE, '',
        '\n    def select_sql(self, expression):\n        return "SELECT 0"\n')]),
    'dremio_where_override': ('method_added', 'holdout', [('sqlglot/generators/dremio.py', '',
        '\n    def where_sql(self, expression):\n        return "WHERE FALSE"\n')]),
    'oracle_group_override': ('method_added', 'holdout', [('sqlglot/generators/oracle.py', '',
        '\n    def group_sql(self, expression):\n        return "GROUP BY missing_column"\n')]),
    'sqlite_removed': ('method_removed', 'holdout', [(SQLITE, '    def trunc_sql(', '    def _disabled_trunc_sql(')]),
    'sqlite_class_added': ('class_added', 'holdout', [(SQLITE, '', '\n\nclass _AlternateSQLiteGenerator(SQLiteGenerator):\n    SUPPORTS_MEDIAN = True\n')]),
    'parser_entry': ('dict_entry', 'dev', [('sqlglot/parsers/bigquery.py', '"BIT_AND": exp.BitwiseAndAgg.from_arg_list', '"BIT_AND": exp.BitwiseOrAgg.from_arg_list')]),
    'fixture_sql': ('fixture', 'dev', [(FIXTURE, 'FROM x;\n\n# title:', 'FROM y;\n\n# title:')]),
    'fixture_comment': ('fixture_comment', 'holdout', [(FIXTURE, '# title: Remove left join', '# title: Remove LEFT join')]),
    'test_expected': ('test_side', 'dev', [(TIME_TEST, 'self.assertEqual(format_time("a", mapping), "b")', 'self.assertEqual(format_time("a", mapping), "c")')]),
    'test_expected_holdout': ('test_side', 'holdout', [('tests/test_serde.py', 'before.meta["x"] = 1', 'before.meta["x"] = 0')]),
    'two_files': ('multi_file', 'holdout', [(SERDE, '    i = 0\n    payloads:', '    i = 1\n    payloads:'),
                                          (TIME_TEST, 'self.assertEqual(format_time("", {}), None)', 'self.assertEqual(format_time("", {}), "")')]),
    'new_module': ('file_added', 'dev', [('sqlglot/_independent_probe.py', None, '"""An unused module."""\n')]),
    'removed_module': ('file_deleted', 'holdout', [('sqlglot/__main__.py', None, None)]),
    'renamed_module': ('file_renamed', 'holdout', [('sqlglot/__main__.py', None, 'sqlglot/_entry_probe.py')]),
    'source_comment': ('comment', 'dev', [(SERDE, '    i = 0\n    payloads:', '    # Start the serialized index at zero.\n    i = 0\n    payloads:')]),
    'dialect_registry': ('registry', 'dev', [('sqlglot/dialects/dax.py', 'class DAX(Dialect):', 'class DAX(Dialect):\n    key = "alternate_dax"')]),
    'eager_dependency': ('initialization', 'holdout', [(INIT, 'pretty = False', 'from sqlglot.dialects import postgres\n\npretty = False')]),
    'pool_fixture': ('subprocess', 'holdout', [(EXECUTOR, 'return self._table', 'return None')]),
    'join_no_final_lf': ('no_final_lf', 'dev', [(BUFFER, 'not _join_is_used(scope, join, alias)', '_join_is_used(scope, join, alias)')]),
    'trie_no_final_lf': ('no_final_lf', 'holdout', [(TRIE, 'if 0 in current:', 'if 1 in current:')]),
    'time_zero_context': ('zero_context', 'holdout', [('sqlglot/time.py', 'return "".join(mapping.get(chars, chars) for chars in chunks)', 'return "".join(mapping.get(chars, chars) for chars in reversed(chunks))')]),
    'serde_crlf': ('line_endings', 'holdout', [(SERDE, '    i = 0\n    payloads:', '    i = 1\n    payloads:')]),
}


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def archive():
    if digest(ARCHIVE.read_bytes()) != SHA256:
        raise ValueError('source archive does not match pinned revision')
    source = tarfile.open(ARCHIVE)
    if source.pax_headers.get('comment') != PIN:
        source.close()
        raise ValueError('source archive commit mismatch')
    return source


def lf_lines(text):
    parts = text.split('\n')
    return [part + '\n' for part in parts[:-1]] + ([parts[-1]] if parts[-1] else [])


def git_diff(path, before, after, context=3):
    header = f'diff --git a/{path} b/{path}\n'
    if before is None:
        header += 'new file mode 100644\n'
    if after is None:
        header += 'deleted file mode 100644\n'
    lines = difflib.unified_diff(
        lf_lines(before or ''), lf_lines(after or ''),
        '/dev/null' if before is None else f'a/{path}',
        '/dev/null' if after is None else f'b/{path}', n=context)
    return header + ''.join(line if line.endswith('\n') else line + '\n\\ No newline at end of file\n'
                            for line in lines)


def generate(case, root):
    category, split, recipes = CASES[case]
    patch, paths = [], []
    for name, original, replacement in recipes:
        file = root / name
        before = file.read_bytes().decode('utf-8') if file.exists() else None
        paths.append(name)
        if category == 'file_renamed':
            file.rename(root / replacement)
            paths.append(replacement)
            patch.append(f'diff --git a/{name} b/{replacement}\nsimilarity index 100%\n'
                         f'rename from {name}\nrename to {replacement}\n')
            continue
        if original is None:
            after = replacement
        elif original == '':
            after = before + replacement
        else:
            if original not in before:
                raise ValueError((case, name, original))
            after = before.replace(original, replacement, 1)
        if category == 'no_final_lf':
            after = after.rstrip('\n')
        elif category == 'line_endings':
            after = after.replace('\n', '\r\n')
        if before == after:
            raise ValueError((case, name, 'unchanged'))
        patch.append(git_diff(name, before, after, context=0 if category == 'zero_context' else 3))
        if after is None:
            file.unlink()
        else:
            file.write_bytes(after.encode())
    return ''.join(patch).encode(), paths


class Outcomes:
    def __init__(self):
        self.collected = []
        self.failed = set()
        self.finished = set()
        self.skipped = set()
        self.errors = []

    def pytest_collection_finish(self, session):
        self.collected = sorted(item.nodeid for item in session.items)

    def pytest_collectreport(self, report):
        if report.failed:
            self.errors.append(report.nodeid)

    def pytest_runtest_logreport(self, report):
        if report.failed:
            self.failed.add(report.nodeid)
        if report.skipped:
            self.skipped.add(report.nodeid)
        if report.when == 'teardown':
            self.finished.add(report.nodeid)


def label(case):
    import pytest
    if sys.version_info[:2] != (3, 13) or pytest.__version__ != '9.2.0':
        raise ValueError('label with the locked trace image')
    os.environ['SKIP_INTEGRATION'] = '0'
    REPORTS.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='sqlglot-') as tmp, archive() as source:
        root = Path(tmp)
        source.extractall(root, filter='data')
        patch, paths = generate(case, root) if case != 'baseline' else (b'', [])
        (REPORTS / f'{case}.patch').write_bytes(patch)
        os.chdir(root)
        sys.path.insert(0, str(root))
        os.environ['PYTHONPATH'] = str(root)
        outcomes = Outcomes()
        start = time.perf_counter()
        try:
            status = int(pytest.main(['-q', '--tb=no', 'tests'], plugins=[outcomes]))
        finally:
            os.chdir(ROOT)
    data = dict(sha256=digest(patch), catalog_sha256=digest(CATALOG.read_bytes()), archive_sha256=SHA256,
                paths=paths, exit=status, collected=outcomes.collected, finished=sorted(outcomes.finished),
                errors=outcomes.errors, failed=sorted(outcomes.failed), skipped=sorted(outcomes.skipped),
                wall=time.perf_counter() - start)
    (REPORTS / f'{case}.json').write_text(json.dumps(data), encoding='utf-8')
    # Pytest exit 1 is expected when independently producing failures.
    return status


def complete_label(label, patch, catalog, catalog_digest):
    names = {test['id'] for test in catalog['tests']}
    skipped = set(catalog['skipped'])
    return bool(
        label and label.get('catalog_sha256') == catalog_digest and label.get('archive_sha256') == SHA256
        and label['sha256'] == digest(patch) and label['exit'] in (0, 1)
        and bool(label['failed']) == (label['exit'] == 1) and not label['errors']
        and set(label['collected']) == names | skipped and names <= set(label['finished'])
        and set(label['failed']) <= names and set(label['skipped']) == skipped
    )


def summarize(checkout, split):
    sys.path.insert(0, str(checkout.resolve()))
    from hybrid import decide, load
    from selector import schedule
    from score import evaluate_run

    catalog_bytes = CATALOG.read_bytes()
    catalog = json.loads(catalog_bytes)
    catalog_digest = digest(catalog_bytes)
    lookup = {t['id']: t for t in catalog['tests']}
    durations = {t['number']: round(t['seconds'] * 1000) for t in lookup.values()}
    durations_by_id = {name: durations[t['number']] for name, t in lookup.items()}
    names = durations_by_id.keys()
    baseline = json.loads((REPORTS / 'baseline.json').read_text(encoding='utf-8'))
    if not complete_label(baseline, b'', catalog, catalog_digest) or baseline['exit'] != 0:
        raise ValueError('baseline did not complete with the organizer catalog')
    start = time.process_time()
    data = load(catalog['tests'])
    if not data:
        raise ValueError('selector evidence does not match organizer manifest')
    rows, decisions, answers, missing = [], [], {}, []
    for case, (category, group, _) in CASES.items():
        if split != 'all' and group != split:
            continue
        patch_path = REPORTS / f'{case}.patch'
        patch = patch_path.read_bytes() if patch_path.exists() else b''
        if not patch:
            missing.append(case)
            continue
        ids, reason = decide(patch.decode('utf-8'), data)
        selected = names if ids is None else ids
        packed = schedule([lookup[name] for name in selected])
        decisions.append((case, category, group, patch, selected, reason, packed))
    cpu = time.process_time() - start
    totals = defaultdict(int)
    for case, category, group, patch, selected, reason, packed in decisions:
        label_path = REPORTS / f'{case}.json'
        label = json.loads(label_path.read_text(encoding='utf-8')) if label_path.exists() else None
        complete = complete_label(label, patch, catalog, catalog_digest)
        failures = set(label['failed']) if complete else None
        misses = sorted(failures - selected) if complete else None
        payload = dict(commit=case, workers=packed)
        cost = max((sum(durations[n] for n in worker) for worker in packed), default=0) + 2000*len(packed)
        longest = min(selected, key=lambda name: (-durations_by_id[name], name), default=None)
        reduced = schedule([lookup[name] for name in selected if name != longest])
        reduced_cost = max((sum(durations[n] for n in w) for w in reduced), default=0) + 2000*len(reduced)
        print(json.dumps(dict(case=case, category=category, split=group,
                              paths=label['paths'] if label else [r[0] for r in CASES[case][2]],
                              label='complete' if complete else 'inconclusive', reason=reason,
                              errors=label['errors'] if label else [], selected=len(selected),
                              full=len(selected) == len(names), ci_ms=cost, longest=longest,
                              longest_marginal_ms=cost-reduced_cost, verification='offline_full_suite',
                              failing=sorted(failures) if complete else None, missed=misses)))
        if complete:
            rows.append(json.dumps(payload))
            answers[case] = {'failing': sorted(lookup[name]['number'] for name in failures)}
            totals[category] += cost
    result = evaluate_run('\n'.join(rows).encode(), catalog['tests'], answers)
    print(json.dumps(dict(result=result, completed=len(rows), scored=len(decisions), missing=missing, cpu_s=cpu,
                          category_ci_ms=dict(sorted(totals.items())))))
    return int(bool(missing) or len(rows) != len(decisions) or not result['ok'] or bool(result['missed_commits']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['list', 'generate', 'label', 'score'])
    parser.add_argument('case', nargs='?')
    parser.add_argument('--checkout', type=Path, default=ROOT)
    parser.add_argument('--split', choices=['dev', 'holdout', 'all'], default='all')
    args = parser.parse_args()
    if args.action == 'list':
        print('\n'.join(['baseline', *CASES]))
    elif args.action == 'generate':
        REPORTS.mkdir(parents=True, exist_ok=True)
        for case in CASES:
            with tempfile.TemporaryDirectory() as tmp, archive() as source:
                source.extractall(tmp, filter='data')
                patch, _ = generate(case, Path(tmp))
                (REPORTS / f'{case}.patch').write_bytes(patch)
    elif args.action == 'label':
        return label(args.case)
    else:
        return summarize(args.checkout, args.split)


if __name__ == '__main__':
    raise SystemExit(main())
