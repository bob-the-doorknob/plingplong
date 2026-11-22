"""Generate, label and score independent pinned-source mutations outside the image."""
import argparse
from collections import Counter, defaultdict
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
    'diff_default': ('signature', 'dev', [('sqlglot/diff.py',
        '    delta_only: bool = False,\n    **kwargs:', '    delta_only: bool = True,\n    **kwargs:')]),
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


# Separate validation cases preserve the frozen Phase 11 holdout.
PHASE12 = {
    'serde_meta_scalar': ('module_global', 'validation', [(SERDE, 'META = "m"', 'META = "c"')]),
    'serde_type_scalar': ('module_global', 'validation', [(SERDE, 'TYPE = "t"', 'TYPE = "v"')]),
    'error_underline_scalar': ('module_global', 'validation', [('sqlglot/errors.py',
        'ANSI_UNDERLINE = "\\033[4m"', 'ANSI_UNDERLINE = "\\033[8m"')]),
    'test_tail_literal': ('test_side', 'validation', [(TIME_TEST,
        'self.assertEqual(format_time("da", mapping), "db")',
        'self.assertEqual(format_time("da", mapping), "bad")')]),
    'expr_tail_count': ('test_side', 'validation', [('tests/test_expressions.py',
        'self.assertEqual(len(ast.expressions), 2)', 'self.assertEqual(len(ast.expressions), 3)')]),
    'test_tail_int': ('test_side', 'validation', [(TIME_TEST,
        'self.assertEqual(0, subsecond_precision("garbage"))',
        'self.assertEqual(1, subsecond_precision("garbage"))')]),
}
CASES.update(PHASE12)
# Phase 13 independent validation of member, signature, fixture-text and test-module rules.
PHASE13 = {
    'p13_postgres_method_removed': ('method_removed', 'p13', [('sqlglot/generators/postgres.py', '    def arraysize_sql(', '    def _disabled_arraysize_sql(')]),
    'p13_duckdb_decorated_removed': ('method_removed', 'p13', [('sqlglot/generators/duckdb.py', '    def reduce_sql(', '    def _disabled_reduce_sql(')]),
    'p13_postgres_parser_override': ('method_added', 'p13', [('sqlglot/parsers/postgres.py', '    def _parse_convert(',
                                     '    def _parse_bitwise(self):\n        return self._parse_term()\n\n    def _parse_convert(')]),
    'p13_normalize_default': ('signature', 'p13', [('sqlglot/optimizer/normalize.py', 'max_distance: int = 128', 'max_distance: int = 1')]),
    'p13_convert_default': ('signature', 'p13', [('sqlglot/parsers/postgres.py', 'safe: bool | None = None) -> exp.Expr | None:', 'safe: bool | None = True) -> exp.Expr | None:')]),
    'p13_fixture_execute_flag': ('fixture_comment', 'p13', [('tests/fixtures/optimizer/qualify_columns.sql', '# execute: false\n# schema: {"zz"', '# execute: true\n# schema: {"zz"')]),
    'p13_fixture_header_comment': ('fixture_comment', 'p13', [('tests/fixtures/optimizer/qualify_columns.sql', '-- Qualify columns', '-- Qualify every column')]),
    'p13_tokens_test_method': ('test_side', 'p13', [('tests/test_tokens.py', 'tokens = Tokenizer().tokenize("SHOW;")', 'tokens = Tokenizer().tokenize("SHOW")')]),
    'p13_hive_dateint_literal': ('module_global', 'p13', [('sqlglot/generators/hive.py', 'HIVE_DATEINT_FORMAT = "\'yyyyMMdd\'"', 'HIVE_DATEINT_FORMAT = "\'yyyyMMd\'"')]),
    'p13_snowflake_scale_literal': ('module_global', 'p13', [('sqlglot/typing/snowflake.py', 'MAX_SCALE = 37', 'MAX_SCALE = 36')]),
    'p13_canonicalize_import_alias': ('imports', 'p13', [('sqlglot/optimizer/canonicalize.py',
        'from sqlglot.helper import is_date_unit, is_iso_date, is_iso_datetime',
        'from sqlglot.helper import is_date_unit, is_iso_datetime as is_iso_date, is_iso_datetime')]),
    'p13_argtypes_nonleaf': ('class_constant', 'p13', [('sqlglot/expressions/constraints.py',
        'arg_types = {"this": False, "kind": True}', 'arg_types = {"this": True, "kind": True}')]),
    'p13_argtypes_rename': ('class_constant', 'p13', [('sqlglot/expressions/aggregate.py',
        'arg_types = {"this": True, "nulls_excluded": False}', 'arg_types = {"this": True, "nulls_excluded_alt": False}')]),
    'p13_bigquery_keywords_pop': ('class_constant', 'p13', [('sqlglot/dialects/bigquery.py',
        'KEYWORDS.pop("DIV")', 'KEYWORDS.pop("ISNULL")')]),
    'p13_clickhouse_keywords_pop': ('class_constant', 'p13', [('sqlglot/dialects/clickhouse.py',
        'KEYWORDS.pop("/*+")', 'KEYWORDS.pop("/*+", None)')]),
    'p13_docstring_text': ('docstring', 'p13', [('sqlglot/optimizer/unnest_subqueries.py',
        'Convert scalar subqueries into cross joins.', 'Convert scalar subqueries into joins.')]),
    'p13_class_docstring': ('docstring', 'p13', [('sqlglot/optimizer/qualify_tables.py',
        'Rewrite sqlglot AST to have fully qualified tables.', 'Rewrite the AST to have qualified tables.')]),
}
CASES.update(PHASE13)


PHASE14 = {
    'p14_test_order': ('shared_state', 'p14', [(TIME_TEST,
        '    def test_canonical_time_format_vocabulary(self):',
        '        type(self)._phase14_seen = True\n\n    def test_canonical_time_format_vocabulary(self):'),
        (TIME_TEST, '    def test_subsecond_precision(self):',
         '    def test_subsecond_precision(self):\n        self.assertFalse(getattr(type(self), "_phase14_seen", False))')]),
    'p14_teardown': ('teardown', 'p14', [(TIME_TEST,
        'class TestTime(unittest.TestCase):',
        'class TestTime(unittest.TestCase):\n    def tearDown(self):\n        raise RuntimeError("teardown failure")\n')]),
    'p14_trie_terminal': ('optimizer_input', 'p14', [(TRIE,
        'if 0 in current:', 'if 0 not in current:')]),
}
CASES.update(PHASE14)


PHASE15 = {
    'p15_cli_usage': ('entrypoint_edit', 'p15', [('sqlglot/__main__.py',
        'description="Transpile SQL"', 'description="Translate SQL"')]),
    'p15_cli_rename': ('file_renamed', 'p15', [('sqlglot/__main__.py', None, 'sqlglot/_sql_command.py')]),
    'p15_private_dremio': ('class_added', 'p15', [('sqlglot/generators/dremio.py', '',
        '\n\nclass _CompatibilityGenerator(DremioGenerator):\n    TRY_SUPPORTED = True\n')]),
    'p15_rebound_dremio': ('class_rebound', 'p15', [('sqlglot/generators/dremio.py', '',
        '\n\nclass DremioGenerator(DremioGenerator):\n    def select_sql(self, expression):\n        return "SELECT 0"\n')]),
}
CASES.update(PHASE15)

PHASE16 = {
    'p16_postgres_factor': ('mapping_value', 'p16dev', [('sqlglot/generators/postgres.py',
        '"DAY": " / 86400",', '"DAY": " / 86000",')]),
    'p16_trunc_format': ('mapping_value', 'p16dev', [('sqlglot/dialects/dialect.py',
        '"MI": "MINUTE",', '"MI": "SECOND",')]),
    'p16_hive_factor': ('mapping_value', 'p16', [('sqlglot/generators/hive.py',
        '"HOUR": " / 3600",', '"HOUR": " / 3610",')]),
    'p16_tsql_format': ('mapping_value', 'p16', [('sqlglot/generators/tsql.py',
        '"WEEKISO": "ISO_WEEK",', '"WEEKISO": "WEEK",')]),
    'p16_root_parse_format': ('mapping_value', 'p16', [('sqlglot/dialects/dialect.py',
        '"YYYY": "YEAR",\n    "YEAR": "YEAR",', '"YYYY": "MONTH",\n    "YEAR": "YEAR",')]),
    'p16_root_generate_format': ('mapping_value', 'p16', [('sqlglot/dialects/dialect.py',
        '"HOUR": "HH",\n    "MINUTE": "MI",', '"HOUR": "HH",\n    "MINUTE": "HH",')]),
}
CASES.update(PHASE16)


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
    originals, updates = {}, {}
    for name, original, replacement in recipes:
        file = root / name
        before = file.read_bytes().decode('utf-8') if file.exists() else None
        originals.setdefault(name, before)
        if name not in paths:
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
        updates[name] = after
        if after is None:
            file.unlink()
        else:
            file.write_bytes(after.encode())
    patch.extend(git_diff(name, originals[name], value, context=0 if category == 'zero_context' else 3)
                 for name, value in updates.items() if value != originals[name])
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


def cost_attribution(selected, failures, lookup, durations, cost, schedule):
    def packed_cost(ids):
        workers = schedule([lookup[name] for name in ids])
        return max((sum(durations[n] for n in worker) for worker in workers), default=0) + 2000*len(workers)

    oracle = packed_cost(failures)
    marginal = {}
    avoidable = sorted(selected - failures)
    for name in avoidable:
        duration = durations[lookup[name]['number']]
        if duration not in marginal:
            marginal[duration] = cost - packed_cost(selected - {name})
    top = sorted(((name, marginal[durations[lookup[name]['number']]]) for name in avoidable),
                 key=lambda pair: (-pair[1], -durations[lookup[pair[0]]['number']], pair[0]))
    return dict(oracle_ms=oracle, oracle_gap_ms=cost-oracle, avoidable_top=top[:5])


def summarize(checkout, split, attribution=False):
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
    costs = Counter()
    full = Counter()
    expensive_picks = Counter()
    expensive = sorted(names, key=lambda name: (-durations_by_id[name], name))[:5]
    audit = []
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
        row = dict(case=case, category=category, split=group,
                              paths=label['paths'] if label else [r[0] for r in CASES[case][2]],
                              label='complete' if complete else 'inconclusive', reason=reason,
                              errors=label['errors'] if label else [], label_exit=label['exit'] if label else None,
                              selected=len(selected),
                              full=len(selected) == len(names), ci_ms=cost, longest=longest,
                              longest_marginal_ms=cost-reduced_cost, runtime_verification=False,
                              failing=sorted(failures) if complete else None, missed=misses)
        if attribution:
            if complete:
                row.update(cost_attribution(selected, failures, lookup, durations, cost, schedule))
            audit.append(row)
        else:
            print(json.dumps(row))
        if complete:
            rows.append(json.dumps(payload))
            answers[case] = {'failing': sorted(lookup[name]['number'] for name in failures)}
            totals[category] += cost
            costs[category] += 1
            full[category] += len(selected) == len(names)
            expensive_picks.update(name for name in expensive if name in selected)
    for row in sorted(audit, key=lambda r: (-r.get('oracle_gap_ms', -1), r['case'])):
        print(json.dumps(row))
    result = evaluate_run('\n'.join(rows).encode(), catalog['tests'], answers)
    print(json.dumps(dict(result=result, completed=len(rows), scored=len(decisions), missing=missing, cpu_s=cpu,
                          category_ci_ms=dict(sorted(totals.items())), category_counts=dict(costs),
                          category_full=dict(full), expensive_picks=dict(expensive_picks))))
    return int(bool(missing) or len(rows) != len(decisions) or not result['ok'] or bool(result['missed_commits']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['list', 'generate', 'label', 'score'])
    parser.add_argument('case', nargs='?', choices=['baseline', *CASES])
    parser.add_argument('--checkout', type=Path, default=ROOT)
    parser.add_argument('--split', choices=['all', *sorted({split for _, split, _ in CASES.values()})], default='all')
    parser.add_argument('--attribution', action='store_true')
    args = parser.parse_args()
    if args.action == 'list':
        print('\n'.join(['baseline', *CASES]))
    elif args.action == 'generate':
        if args.case == 'baseline':
            parser.error('baseline has no patch')
        REPORTS.mkdir(parents=True, exist_ok=True)
        for case in [args.case] if args.case else CASES:
            with tempfile.TemporaryDirectory() as tmp, archive() as source:
                source.extractall(tmp, filter='data')
                patch, _ = generate(case, Path(tmp))
                (REPORTS / f'{case}.patch').write_bytes(patch)
    elif args.action == 'label':
        if not args.case:
            parser.error('label requires a case name')
        return label(args.case)
    else:
        return summarize(args.checkout, args.split, args.attribution)


if __name__ == '__main__':
    raise SystemExit(main())
