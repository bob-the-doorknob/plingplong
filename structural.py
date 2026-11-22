"""Bound structural edits using source-derived evidence."""
import ast

SCALARS = (bool, int, str, bytes)
SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda,
          ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def literal_binding(old, new):
    before, after = ast.parse(old), ast.parse(new)
    if len(before.body) != len(after.body):
        return None
    changes = [(a, b) for a, b in zip(before.body, after.body) if ast.dump(a) != ast.dump(b)]
    if len(changes) != 1:
        return None
    a, b = changes[0]
    if not (isinstance(a, ast.Assign) and isinstance(b, ast.Assign)
            and len(a.targets) == 1 and isinstance(a.targets[0], ast.Name)
            and isinstance(a.value, ast.Constant) and isinstance(b.value, ast.Constant)
            and type(a.value.value) in SCALARS and type(a.value.value) is type(b.value.value)):
        return None
    b.value = a.value
    return a.targets[0].id if ast.dump(a) == ast.dump(b) else None


def global_readers(source, name):
    """Only direct runtime loads of a unique module scalar binding are bounded."""
    tree = ast.parse(source)
    targets = [node.targets[0] for node in tree.body if isinstance(node, ast.Assign)
               and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
               and node.targets[0].id == name and isinstance(node.value, ast.Constant)]
    if len(targets) != 1:
        return None
    loads = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if node.id in {'globals', 'locals', 'vars', 'eval', 'exec'}:
                return None
            if node.id == name and node is not targets[0]:
                if not isinstance(node.ctx, ast.Load):
                    return None
                loads.add(node)
        if isinstance(node, (ast.Global, ast.Nonlocal)) and name in node.names:
            return None
        if isinstance(node, ast.alias) and (node.asname or node.name.split('.')[0]) in (name, '*'):
            return None
    readers = set()
    for fn in tree.body:
        if not isinstance(fn, ast.FunctionDef) or fn.decorator_list:
            continue
        pending = list(fn.body)
        while pending:
            node = pending.pop()
            if node in loads:
                loads.remove(node)
                readers.add(fn.name)
            if not isinstance(node, SCOPES):
                pending.extend(ast.iter_child_nodes(node))
    if loads or not readers:
        return None
    if any(sum(getattr(n, 'name', None) == reader for n in tree.body) != 1 for reader in readers):
        return None
    return readers
