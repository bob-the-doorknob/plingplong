"""Pinned SQLGlot numeric escape configuration and decoder dependency."""
import ast

ATTRIBUTE = 'NUMERIC_ESCAPES'
WEEK_OFFSET = 'WEEK_OFFSET'
DECODER = 'sqlglot/tokenizer_core.py'


def _class_value(source, class_name, attribute):
    statements = ast.parse(source).body
    for part in class_name.split('.'):
        matches = [node for node in statements if isinstance(node, ast.ClassDef) and node.name == part]
        if len(matches) != 1:
            return None
        statements = matches[0].body
    values = [node.value for node in statements if isinstance(node, ast.Assign) and len(node.targets) == 1
              and isinstance(node.targets[0], ast.Name) and node.targets[0].id == attribute]
    return values[0] if len(values) == 1 else None


def _assignment(source, class_name):
    value = _class_value(source, class_name, ATTRIBUTE)
    if not isinstance(value, ast.Dict):
        return None
    try:
        result = ast.literal_eval(value)
    except (ValueError, TypeError):
        return None
    if len(result) != len(value.keys):
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

def week_offset_edit(old, new, class_name):
    offsets = []
    for source in (old, new):
        try:
            offset = ast.literal_eval(_class_value(source, class_name, WEEK_OFFSET))
        except (ValueError, TypeError):
            return False
        if type(offset) is not int or not 0 < abs(offset) <= 6:
            return False
        offsets.append(offset)
    return offsets[0] != offsets[1]


def week_offset_sites(sources):
    """Find every pinned source line consuming a week offset."""
    return [(path, node.lineno)
            for path, source in sources.items() if path.endswith('.py') and WEEK_OFFSET in source
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Attribute) and node.attr == WEEK_OFFSET
            and isinstance(node.ctx, ast.Load)]
