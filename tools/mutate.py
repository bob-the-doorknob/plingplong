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
