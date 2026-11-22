"""Independent full-suite mutations in disposable Linux container filesystems."""
import ast
import difflib
import os
from pathlib import Path
import subprocess
import sys
import tarfile

REPLACEMENTS = {
    'fixture': [('tests/fixtures/optimizer/eliminate_joins.sql', 'FROM x;', 'FROM obviously_wrong;')],
    'function': [('sqlglot/serde.py', 'payloads.append(payload)', 'payloads.append({})')],
    'lambda': [('sqlglot/generators/sqlite.py', 'self.func("RANDOM", e.this)', 'self.func("RANDOMIZE", e.this)')],
    'nested': [('sqlglot/dialects/dialect.py',
                'group=seq_get(args, 2) or exp.Literal.number(dialect.REGEXP_EXTRACT_DEFAULT_GROUP)',
                'group=seq_get(args, 3) or exp.Literal.number(dialect.REGEXP_EXTRACT_DEFAULT_GROUP)')],
    'block_fixture': [('tests/fixtures/optimizer/qualify_columns.sql', 'SELECT x."a" AS "a" FROM x AS x;',
                       'SELECT x."b" AS "a" FROM x AS x;')],
}
# Class-level attribute values: dialect, tokenizer, parser, generator settings and
# expression arg_types, plus two base classes in core files that must fall back.
ATTRIBUTES = {
    'attr_duckdb_null_ordering': ('sqlglot/dialects/duckdb.py', '    NULL_ORDERING = "nulls_are_last"', '    NULL_ORDERING = "nulls_are_small"'),
    'attr_postgres_index_offset': ('sqlglot/dialects/postgres.py', '    INDEX_OFFSET = 1\n', '    INDEX_OFFSET = 0\n'),
    'attr_bigquery_log_base': ('sqlglot/dialects/bigquery.py', '    LOG_BASE_FIRST = False', '    LOG_BASE_FIRST = True'),
    'attr_hive_date_format': ('sqlglot/dialects/hive.py', '    DATE_FORMAT = "\'yyyy-MM-dd\'"', '    DATE_FORMAT = "\'yyyy-MM\'"'),
    'attr_mysql_tokenizer_quotes': ('sqlglot/dialects/mysql.py', '        QUOTES = ["\'", \'"\']', '        QUOTES = ["\'"]'),
    'attr_hive_tokenizer_escapes': ('sqlglot/dialects/hive.py', '        STRING_ESCAPES = ["\\\\"]', '        STRING_ESCAPES = ["\\\\", "\'"]'),
    'attr_hive_invalid_escapes': ('sqlglot/dialects/hive.py', '        STRING_ESCAPES = ["\\\\"]', '        STRING_ESCAPES = None'),
    'attr_postgres_parser_json': ('sqlglot/parsers/postgres.py', '    JSON_ARROWS_REQUIRE_JSON_TYPE = True', '    JSON_ARROWS_REQUIRE_JSON_TYPE = False'),
    'attr_hive_parser_log': ('sqlglot/parsers/hive.py', '    LOG_DEFAULTS_TO_LN = True', '    LOG_DEFAULTS_TO_LN = False'),
    'attr_bigquery_parser_functions': ('sqlglot/parsers/bigquery.py', '"BIT_AND": exp.BitwiseAndAgg.from_arg_list,', '"BIT_AND": exp.BitwiseOrAgg.from_arg_list,'),
    'attr_duckdb_transforms': ('sqlglot/generators/duckdb.py', 'exp.ArraySum: rename_func("LIST_SUM"),', 'exp.ArraySum: rename_func("LIST_TOTAL"),'),
    'attr_hive_generator_decode': ('sqlglot/generators/hive.py', '    SUPPORTS_DECODE_CASE = False', '    SUPPORTS_DECODE_CASE = True'),
    'attr_lateral_arg_types': ('sqlglot/expressions/query.py', 'class Lateral(Expression, UDTF):\n    arg_types = {\n        "this": True,\n        "view": False,',
                               'class Lateral(Expression, UDTF):\n    arg_types = {\n        "this": True,\n        "view": True,'),
    'attr_approx_quantiles_arg_types': ('sqlglot/expressions/aggregate.py', 'class ApproxQuantiles(Expression, AggFunc):\n    arg_types = {"this": True, "expression": False}',
                                        'class ApproxQuantiles(Expression, AggFunc):\n    arg_types = {"this": True, "expression": True}'),
    'base_parser_flag': ('sqlglot/parser.py', '    SUPPORTS_DIRECTED_JOIN = True', '    SUPPORTS_DIRECTED_JOIN = False'),
    'base_generator_flag': ('sqlglot/generator.py', '    IGNORE_NULLS_IN_FUNC = False', '    IGNORE_NULLS_IN_FUNC = True'),
}
REPLACEMENTS.update({case: [edit] for case, edit in ATTRIBUTES.items()})
# Comment-only edits. The first three cases cover sources that tests read as
# text (linecache through warnings, read_text of sqlglot/typing). Parser,
# generator and optimizer files were drawn with random.Random(20261121).
TYPING = ['__init__', 'bigquery', 'clickhouse', 'databricks', 'duckdb', 'hive', 'mysql', 'postgres',
          'presto', 'redshift', 'snowflake', 'spark', 'spark2', 'sqlite', 'tsql']
COMMENTS = {
    'comment_dialect': ['sqlglot/dialects/dialect.py'],
    'comment_typing': [f'sqlglot/typing/{name}.py' for name in TYPING],
    'comment_tokens': ['sqlglot/tokens.py'],
    'comment_core': ['sqlglot/__init__.py', 'sqlglot/expressions/core.py', 'sqlglot/parser.py'],
    'comment_trino_parser': ['sqlglot/parsers/trino.py'],
    'comment_dune_generator': ['sqlglot/generators/dune.py'],
    'comment_isolate_table_selects': ['sqlglot/optimizer/isolate_table_selects.py'],
    'comment_mixed': ['sqlglot/generator.py'],
}
REPLACEMENTS.update({
    'registry_trigger_event': [('sqlglot/expressions/ddl.py',
        'class TriggerEvent(Expression):\n    arg_types = {"this": True, "columns": False}',
        'class TriggerEvent(Expression):\n    arg_types = {"this": True, "columns": True}')],
    'registry_in_place': [('sqlglot/expressions/ddl.py',
        'class TriggerReferencing(Expression):',
        'TriggerEvent.required_args.add("columns")\n\n\nclass TriggerReferencing(Expression):')],
    'registry_clone': [('sqlglot/expressions/ddl.py',
        'class Clone(Expression):\n    arg_types = {"this": True, "shallow": False, "copy": False}',
        'class Clone(Expression):\n    arg_types = {"this": True, "shallow": True, "copy": False}')],
})
REPLACEMENTS.update({
    'statement_range_condition': [('sqlglot/helper.py', 'if start <= last_end:', 'if start < last_end:')],
    'statement_executor_guard': [('sqlglot/executor/context.py', 'if self._table is None:', 'if self._table is not None:')],
    'statement_optimizer_boolean': [('sqlglot/optimizer/eliminate_joins.py', 'if name in left_tables and name not in right_tables:', 'if name in left_tables or name not in right_tables:')],
})
REPLACEMENTS.update({
    'predicate_column_identity': [('sqlglot/optimizer/merge_subqueries.py', 'if table_column.name == conflict:', 'if table_column.name is conflict:')],
    'predicate_type_identity': [('sqlglot/optimizer/annotate_types.py', 'if e.name == expression.expression.name:', 'if e.name is expression.expression.name:')],
})
REPLACEMENTS.update({
    'numeric_spark_unicode': [('sqlglot/dialects/spark.py', '"u": (16, 4, 4, 0xFFFF)', '"u": (15, 4, 4, 0xFFFF)')],
    'numeric_postgres_octal': [('sqlglot/dialects/postgres.py', '"0": (8, 1, 3, 0o777)', '"0": (7, 1, 3, 0o777)')],
    'numeric_duckdb_hex': [('sqlglot/dialects/duckdb.py', '"x": (16, 1, 2, 0xFF)', '"x": (10, 1, 2, 0xFF)')],
})
REPLACEMENTS.update({
    'numeric_snowflake_hex': [('sqlglot/dialects/snowflake.py', '"x": (16, 2, 2, 0xFF)', '"x": (8, 2, 2, 0xFF)')],
    'numeric_clickhouse_hex': [('sqlglot/dialects/clickhouse.py', '"x": (16, 2, 2, 0xFF)', '"x": (8, 2, 2, 0xFF)')],
})
REPLACEMENTS.update({
    'week_oracle_offset': [('sqlglot/dialects/oracle.py', '    WEEK_OFFSET = -1', '    WEEK_OFFSET = 2')],
    'week_bigquery_offset': [('sqlglot/dialects/bigquery.py', '    WEEK_OFFSET = -1', '    WEEK_OFFSET = 3')],
    'week_teradata_zero': [('sqlglot/dialects/teradata.py', '    WEEK_OFFSET = -1', '    WEEK_OFFSET = 0')],
})
REPLACEMENTS.update({
    'boolean_guard_canonicalize': [('sqlglot/optimizer/canonicalize.py', 'if isinstance(node, exp.Add) and node.type and node.type.this in exp.DataType.TEXT_TYPES:', 'if isinstance(node, exp.Add) and node.type or node.type.this in exp.DataType.TEXT_TYPES:')],
})
REPLACEMENTS['comment_mixed'] = REPLACEMENTS['function']


def add_comments(text):
    """Insert a comment on line 1 and one inside the function body nearest the middle."""
    tree = ast.parse(text)
    lines = text.splitlines(True)
    body = [s for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            for s in node.body] or tree.body
    middle = len(lines) // 2
    statement = min(body, key=lambda s: (abs(s.lineno - middle), s.lineno))
    lines.insert(statement.lineno - 1, ' ' * statement.col_offset + '# mutation: comment inside a body\n')
    lines.insert(0, '# mutation: comment on line 1\n')
    result = ''.join(lines)
    assert ast.dump(ast.parse(result)) == ast.dump(tree)
    return result


case = sys.argv[1]
root = Path('/tmp/mutation')
root.mkdir()
with tarfile.open('/repo/.phase5/src.tar') as archive:
    archive.extractall(root, filter='data')
os.chdir(root)
edits = {}
for path in COMMENTS.get(case, []):
    edits[path] = add_comments(Path(path).read_text())
for path, old, new in REPLACEMENTS.get(case, []):
    before = edits.get(path, Path(path).read_text())
    assert old in before
    edits[path] = before.replace(old, new, 1)
assert edits, case
patch = ''
for path, after in edits.items():
    before = Path(path).read_text()
    patch += f'diff --git a/{path} b/{path}\n' + ''.join(difflib.unified_diff(
        before.splitlines(True), after.splitlines(True), fromfile='a/' + path, tofile='b/' + path))
    Path(path).write_text(after)
Path('/repo/.phase5/' + case + '.patch').write_text(patch)
os.environ.update(BR_MUTATION=case, PYTHONPATH="/repo/tools:" + str(root))
raise SystemExit(subprocess.call([sys.executable, '-m', 'pytest', '-q', '-p', 'mutation_report', '--tb=no', 'tests']))
