"""Experimental AST change locality; text observability always remains separate."""
import ast

FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
# Comprehensions and generator expressions are left inside their enclosing
# body; compound statements are only split inside function bodies.
OPAQUE = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
BLOCKS = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.TryStar,
          ast.With, ast.AsyncWith, ast.Match)


def _yields(node):
    return any(isinstance(n, (ast.Yield, ast.YieldFrom)) for n in ast.walk(node))


def _split(tree):
    """Replace every code-object body with a placeholder, keyed by co_qualname.

    Inner bodies are extracted first, so an outer body only holds its own code
    plus placeholders for nested definitions. Definition-time expressions
    (decorators, defaults, annotations, bases) stay in the enclosing body.
    """
    bodies, scopes, duplicate, parents = {}, set(), set(), {}

    def walk(node, prefix, owner, in_function):
        if getattr(node, 'type_params', None) or isinstance(node, OPAQUE):
            return
        if isinstance(node, ast.ClassDef):
            for child in node.decorator_list + node.bases + node.keywords:
                walk(child, prefix, owner, in_function)
            name = prefix + node.name
            if name in scopes:
                duplicate.add(name)
            scopes.add(name)
            for child in node.body:
                walk(child, name + '.', owner, in_function)
            return
        if isinstance(node, FUNCTIONS + (ast.Lambda,)):
            returns = getattr(node, 'returns', None)
            for child in getattr(node, 'decorator_list', []) + [node.args] + ([returns] if returns else []):
                walk(child, prefix, owner, in_function)
            if isinstance(node, ast.Lambda):
                name = prefix + '<lambda>'
                walk(node.body, name + '.<locals>.', name, True)
                bodies.setdefault(name, []).append(ast.dump(node.body))
                node.body = ast.Constant(_yields(node.body))
            else:
                name = prefix + node.name
                if name in scopes:
                    duplicate.add(name)
                scopes.add(name)
                for child in node.body:
                    walk(child, name + '.<locals>.', name, True)
                bodies.setdefault(name, []).append(
                    ast.dump(ast.Module(body=node.body, type_ignores=[])))
                metadata = (ast.get_docstring(node, clean=False),
                            any(_yields(child) for child in node.body))
                node.body = [ast.Expr(ast.Constant(metadata))]
            parents.setdefault(name, owner)
            return
        if isinstance(node, BLOCKS) and not in_function:
            return
        for child in ast.iter_child_nodes(node):
            walk(child, prefix, owner, in_function)

    for statement in tree.body:
        walk(statement, '', None, False)
    return bodies, ast.dump(tree), duplicate, parents


def scope_names(source: str) -> set[str]:
    """Qualified names of the code objects split out of source."""
    return set(_split(ast.parse(source))[0])


def classify_change(old: str, new: str) -> dict:
    """Locate changed bodies without executing code or asserting equivalence.

    Each changed name is the co_qualname of the innermost code object whose own
    body changed. Lambdas sharing a qualname are reported once; evidence for
    that qualname covers all of them. A nested scope that exists on only one
    side is reached only through its enclosing function, which then changed.
    """
    result = dict(functions=[], structural=True, text_changed=old != new,
                  ast_equal=False, reason='parse_error')
    try:
        before, after = ast.parse(old), ast.parse(new)
    except (SyntaxError, ValueError, RecursionError):
        return result
    result['ast_equal'] = ast.dump(before) == ast.dump(after)

    previous, old_structure, old_duplicate, old_parents = _split(before)
    current, new_structure, new_duplicate, new_parents = _split(after)
    changed = {name for name in previous.keys() | current.keys()
               if previous.get(name) != current.get(name)}
    parents = old_parents | new_parents
    result['functions'] = sorted(
        name for name in changed
        if (name in previous and name in current) or parents.get(name) not in changed)
    duplicates = old_duplicate | new_duplicate
    if duplicates and (not result['functions'] or any(
            name == dup or name.startswith(dup + '.')
            for name in result['functions'] for dup in duplicates)):
        result['reason'] = 'duplicate_scope'
        return result
    result['structural'] = old_structure != new_structure
    result['reason'] = 'structural' if result['structural'] else 'bodies_or_text'
    return result
