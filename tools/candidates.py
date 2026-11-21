"""Names assigned in sqlglot class bodies: the attributes whose runtime reads are recorded."""
import ast
import json
from pathlib import Path
import sys


def class_body_names(tree):
    names = set()

    def visit(body):
        for node in body:
            if isinstance(node, ast.ClassDef):
                visit(node.body)
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
            for target in targets:
                names.update(n.id for n in ast.walk(target) if isinstance(n, ast.Name))

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            visit(node.body)
    return names


root = Path(sys.argv[1])
names = set()
for path in sorted((root / 'sqlglot').rglob('*.py')):
    names |= class_body_names(ast.parse(path.read_text(encoding='utf-8')))
json.dump(sorted(n for n in names if not n.startswith('__')), sys.stdout)
