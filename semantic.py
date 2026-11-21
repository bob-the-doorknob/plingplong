"""Experimental AST change locality; text observability always remains separate."""
import ast


def classify_change(old: str, new: str) -> dict:
    """Locate changed bodies without executing code or asserting equivalence.

    shortcut: nested/control-flow definitions are attributed to their enclosing
    scope, add finer scopes only after real-source coverage validation.
    """
    result = dict(functions=[], structural=True, text_changed=old != new,
                  ast_equal=False, reason='parse_error')
    try:
        before, after = ast.parse(old), ast.parse(new)
    except (SyntaxError, ValueError, RecursionError):
        return result
    result['ast_equal'] = ast.dump(before) == ast.dump(after)

    def split(tree):
        bodies = {}
        scopes = set()
        duplicate = set()

        def visit(statements, prefix=''):
            nonlocal duplicate
            for node in statements:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    name = prefix + node.name
                    if name in scopes:
                        duplicate.add(name)
                    scopes.add(name)
                    if isinstance(node, ast.ClassDef):
                        visit(node.body, name + '.')
                    else:
                        bodies.setdefault(name, []).append(ast.dump(ast.Module(body=node.body, type_ignores=[])))
                        metadata = (ast.get_docstring(node, clean=False),
                                    any(isinstance(n, (ast.Yield, ast.YieldFrom)) for n in ast.walk(node)))
                        node.body = [ast.Expr(ast.Constant(metadata))]
        visit(tree.body)
        return bodies, ast.dump(tree), duplicate

    previous, old_structure, old_duplicate = split(before)
    current, new_structure, new_duplicate = split(after)
    result['functions'] = sorted(name for name in previous.keys() | current.keys()
                                 if previous.get(name) != current.get(name))
    duplicates = old_duplicate | new_duplicate
    if duplicates and (not result['functions'] or any(
            name == dup or name.startswith(dup + '.')
            for name in result['functions'] for dup in duplicates)):
        result['reason'] = 'duplicate_scope'
        return result
    result['structural'] = old_structure != new_structure
    result['reason'] = 'structural' if result['structural'] else 'bodies_or_text'
    return result
