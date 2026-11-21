"""Pinned SQLGlot numeric escape configuration and decoder dependency."""
import ast

ATTRIBUTE = 'NUMERIC_ESCAPES'
DECODER = 'sqlglot/tokenizer_core.py'


def _assignment(source, class_name):
    statements = ast.parse(source).body
    for part in class_name.split('.'):
        matches = [node for node in statements if isinstance(node, ast.ClassDef) and node.name == part]
        if len(matches) != 1:
            return None
        statements = matches[0].body
    values = [node.value for node in statements if isinstance(node, ast.Assign) and len(node.targets) == 1
              and isinstance(node.targets[0], ast.Name) and node.targets[0].id == ATTRIBUTE]
    if len(values) != 1 or not isinstance(values[0], ast.Dict):
        return None
    try:
        result = ast.literal_eval(values[0])
    except (ValueError, TypeError):
        return None
    if len(result) != len(values[0].keys):
        return None
    for key, value in result.items():
        if (type(key) is not str or len(key) != 1 or type(value) is not tuple or len(value) != 4
                or any(type(component) is not int for component in value) or not 2 <= value[0] <= 36):
            return None
    return result


def numeric_radix_edit(old, new, class_name):
    before, after = _assignment(old, class_name), _assignment(new, class_name)
    if not before or not after or list(before) != list(after):
        return False
    changed = [key for key in before if before[key] != after[key]]
    return len(changed) == 1 and before[changed[0]][1:] == after[changed[0]][1:]


def decoder_sites(source):
    """Locate the pinned decoder's reads of tuple values rather than map keys."""
    tree = ast.parse(source)
    cls = next((node for node in tree.body
                if isinstance(node, ast.ClassDef) and node.name == 'TokenizerCore'), None)
    if cls is None:
        return []
    sites = []
    for method in cls.body:
        if not isinstance(method, ast.FunctionDef):
            continue
        for node in ast.walk(method):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == 'get' and isinstance(node.func.value, ast.Attribute)
                    and node.func.value.attr == 'numeric_escapes'
                    and isinstance(node.func.value.value, ast.Name) and node.func.value.value.id == 'self'):
                sites.append((node.lineno, 'TokenizerCore.' + method.name))
    return sites
