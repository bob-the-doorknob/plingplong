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

def _assertion_literal(method):
    if (not isinstance(method, ast.FunctionDef) or not method.name.startswith('test_')
            or method.decorator_list or not method.body):
        return None
    last = method.body[-1]
    if not isinstance(last, ast.Expr) or not isinstance(last.value, ast.Call):
        return None
    call = last.value
    if ast.unparse(call.func) != 'self.assertEqual' or call.keywords or len(call.args) != 2:
        return None
    literals = [i for i, arg in enumerate(call.args) if isinstance(arg, ast.Constant)]
    if literals != [1]:
        return None
    index = literals[0]
    value = call.args[index]
    if type(value.value) not in SCALARS or value.lineno != value.end_lineno:
        return None
    return call, index, value


def plain_test_class(node):
    if not (isinstance(node, ast.ClassDef) and not (node.decorator_list or node.keywords)
            and [ast.unparse(base) for base in node.bases] == ['unittest.TestCase']):
        return False
    if any(isinstance(n, ast.Attribute) and n.attr in
           {'addTypeEqualityFunc', '_type_equality_funcs', '__dict__'} for n in ast.walk(node)):
        return False
    return all((isinstance(m, ast.FunctionDef) and m.name.startswith('test_'))
               or (isinstance(m, ast.Assign) and ast.unparse(m) == 'maxDiff = None') for m in node.body)


def terminal_assertion(old, new):
    """Recognize a single same-type literal edit to an ordinary terminal assertion."""
    before, after = ast.parse(old), ast.parse(new)
    for a, b in zip(before.body, after.body):
        if not plain_test_class(a) or not isinstance(b, ast.ClassDef):
            continue
        for first, second in zip(a.body, b.body):
            prev, curr = _assertion_literal(first), _assertion_literal(second)
            if not prev or not curr or prev[1] != curr[1]:
                continue
            call, _, value = prev
            updated, i, replacement = curr
            if ast.dump(value) == ast.dump(replacement) or type(value.value) is not type(replacement.value):
                continue
            updated.args[i] = value
            if ast.dump(before) != ast.dump(after):
                return None
            # Preserve all source bytes other than the isolated literal, including line layout.
            def mask(text, node):
                lines = text.encode('utf-8').split(b'\n')
                line = lines[node.lineno - 1]
                lines[node.lineno - 1] = line[:node.col_offset] + line[node.end_col_offset:]
                return b'\n'.join(lines)

            if mask(old, value) == mask(new, replacement):
                return a.name + '::' + first.name, call.lineno, type(value.value).__name__
            return None
    return None

def passive_generator_class(old, new, generator_source):
    """Recognize an appended private class whose plain creation runs no user hooks."""
    if not new.startswith(old):
        return None
    before, after = ast.parse(old), ast.parse(new)
    if len(after.body) != len(before.body) + 1:
        return None
    addition = after.body.pop()
    if (not isinstance(addition, ast.ClassDef) or addition.decorator_list or addition.keywords
            or getattr(addition, 'type_params', ()) or not addition.name.startswith('_')
            or addition.name.startswith('__') or len(addition.bases) != 1
            or not isinstance(addition.bases[0], ast.Name)
            or ast.dump(before) != ast.dump(after)):
        return None
    for stmt in addition.body:
        if isinstance(stmt, ast.Pass):
            continue
        if not (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name) and not stmt.targets[0].id.startswith('__')
                and isinstance(stmt.value, ast.Constant)
                and (stmt.value.value is None or type(stmt.value.value) in SCALARS)):
            return None
    name = addition.bases[0].id

    def plain_base(module, name, bases):
        definitions = [node for node in ast.walk(module)
                       if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                       and node.name == name]
        if len(definitions) != 1:
            return False
        cls = definitions[0]
        return (cls in module.body and isinstance(cls, ast.ClassDef) and not cls.decorator_list
                and not cls.keywords and not getattr(cls, 'type_params', ())
                and [ast.unparse(base) for base in cls.bases] == bases
                and not any(isinstance(n, ast.Name) and n.id == name and isinstance(n.ctx, ast.Store)
                            for n in ast.walk(module))
                and '__init_subclass__' not in ast.unparse(cls))

    if plain_base(before, name, ['generator.Generator']) and plain_base(ast.parse(generator_source), 'Generator', []):
        return addition.name, name
    return None
