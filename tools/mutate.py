"""Independent full-suite mutations in disposable Linux container filesystems."""
import difflib
import os
from pathlib import Path
import subprocess
import sys
import tarfile

case = sys.argv[1]
path, old, new = {
    'fixture': ('tests/fixtures/optimizer/eliminate_joins.sql', 'FROM x;', 'FROM obviously_wrong;'),
    'function': ('sqlglot/serde.py', 'payloads.append(payload)', 'payloads.append({})'),
    'lambda': ('sqlglot/generators/sqlite.py', 'self.func("RANDOM", e.this)', 'self.func("RANDOMIZE", e.this)'),
    'nested': ('sqlglot/dialects/dialect.py',
               'group=seq_get(args, 2) or exp.Literal.number(dialect.REGEXP_EXTRACT_DEFAULT_GROUP)',
               'group=seq_get(args, 3) or exp.Literal.number(dialect.REGEXP_EXTRACT_DEFAULT_GROUP)'),
    'block_fixture': ('tests/fixtures/optimizer/qualify_columns.sql', 'SELECT x."a" AS "a" FROM x AS x;',
                      'SELECT x."b" AS "a" FROM x AS x;'),
}[case]
root = Path('/tmp/mutation')
root.mkdir()
with tarfile.open('/repo/.phase5/src.tar') as archive:
    archive.extractall(root,filter='data')
os.chdir(root)
p = Path(path)
before = p.read_text()
assert old in before
after = before.replace(old,new,1)
patch = f'diff --git a/{path} b/{path}\n' + ''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='a/'+path,tofile='b/'+path))
Path('/repo/.phase5/'+case+'.patch').write_text(patch)
p.write_text(after)
os.environ.update(BR_MUTATION=case, PYTHONPATH="/repo/tools:" + str(root))
raise SystemExit(subprocess.call([sys.executable,'-m','pytest','-q','-p','mutation_report','--tb=no','tests']))
