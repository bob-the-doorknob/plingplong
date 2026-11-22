"""Experimental AST change locality; text observability always remains separate."""
import ast
import difflib

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


def _assigned_name(node):
    """Target of a single-name class-level assignment with a value, else None."""
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        return node.targets[0].id
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
        return node.target.id
    return None


def _bindings(body, name):
    count = 0
    for node in (n for statement in body for n in ast.walk(statement)):
        if isinstance(node, ast.Name) and node.id == name and not isinstance(node.ctx, ast.Load):
            count += 1
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name:
            count += 1
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            count += sum((alias.asname or alias.name).split('.')[0] == name for alias in node.names)
    return count


def _body_reads(body, name):
    """Over-approximate class-scope reads of name: function and lambda bodies are placeholders."""
    return any(isinstance(n, ast.Name) and n.id == name and isinstance(n.ctx, ast.Load)
               for statement in body for n in ast.walk(statement))


def _literal_kind(node):
    try:
        return type(ast.literal_eval(node))
    except (ValueError, TypeError):
        return None


def _boolean_schema_edit(before, after):
    """Recognize a plain class whose only change is a required-argument flag."""
    if any(node.decorator_list or node.keywords or len(node.body) != 1 for node in (before, after)):
        return False
    if len(before.bases) != 1 or not isinstance(before.bases[0], ast.Name) or before.bases[0].id != 'Expression':
        return False
    first, second = before.body[0], after.body[0]
    if any(_assigned_name(node) != 'arg_types' or not isinstance(node.value, ast.Dict)
           for node in (first, second)):
        return False
    for node in (first, second):
        if not all(isinstance(key, ast.Constant) and type(key.value) is str
                   for key in node.value.keys):
            return False
        if not all(isinstance(value, ast.Constant) and type(value.value) is bool
                   for value in node.value.values):
            return False
    return [key.value for key in first.value.keys] == [key.value for key in second.value.keys]


def _class_attribute_changes(old_body, new_body, prefix='', in_class=False):
    if len(old_body) != len(new_body):
        return None
    changes = []
    for a, b in zip(old_body, new_body):
        if ast.dump(a) == ast.dump(b):
            continue
        if isinstance(a, ast.ClassDef) and isinstance(b, ast.ClassDef) and a.name == b.name and all(
                ast.dump(ast.Tuple(elts=getattr(a, f, []), ctx=ast.Load()))
                == ast.dump(ast.Tuple(elts=getattr(b, f, []), ctx=ast.Load()))
                for f in ('bases', 'keywords', 'decorator_list', 'type_params')):
            inner = _class_attribute_changes(a.body, b.body, prefix + a.name + '.', True)
            if inner is None:
                return None
            if len(inner) == 1 and _boolean_schema_edit(a, b):
                inner[0]['boolean_schema'] = True
            changes.extend(inner)
            continue
        name = _assigned_name(a) if in_class else None
        if (not name or name.startswith('__') or name != _assigned_name(b)
                or (isinstance(a, ast.AnnAssign) != isinstance(b, ast.AnnAssign))
                or (isinstance(a, ast.AnnAssign) and (ast.dump(a.annotation), a.simple) != (ast.dump(b.annotation), b.simple))
                or _bindings(old_body, name) != 1 or _bindings(new_body, name) != 1):
            return None
        kind = _literal_kind(a.value)
        if kind is not None and _literal_kind(b.value) is not kind:
            return None
        changes.append(dict(cls=prefix[:-1], attr=name,
                            body_read=_body_reads(old_body, name) or _body_reads(new_body, name)))
    return changes


SAFE_DECORATORS = frozenset({'staticmethod', 'classmethod', 'property'})


def _literal(node):
    try:
        ast.literal_eval(node)
        return True
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return False


def _annotations(node):
    arguments = node.args
    return [ast.dump(arg.annotation) if arg.annotation else None
            for arg in arguments.posonlyargs + arguments.args + arguments.kwonlyargs
            + [a for a in (arguments.vararg, arguments.kwarg) if a]] + [ast.dump(node.returns) if node.returns else None]


def _header_change(a, b, postponed):
    """True when two same-name definitions differ only in safely evaluated header parts."""
    if (type(a) is not type(b) or a.name != b.name or ast.dump(ast.Module(body=a.body, type_ignores=[]))
            != ast.dump(ast.Module(body=b.body, type_ignores=[]))
            or [ast.dump(d) for d in a.decorator_list] != [ast.dump(d) for d in b.decorator_list]
            or getattr(a, 'type_params', None) or getattr(b, 'type_params', None)):
        return False
    # Without postponed evaluation an annotation runs when the definition runs.
    if not postponed and _annotations(a) != _annotations(b):
        return False
    old_defaults = {ast.dump(d) for d in a.args.defaults + a.args.kw_defaults if d is not None}
    # A new default is evaluated when the definition runs; only literals cannot raise.
    return all(_literal(d) for d in b.args.defaults + b.args.kw_defaults
               if d is not None and ast.dump(d) not in old_defaults)


def _new_member(node, postponed):
    """A method whose definition can be added or removed without import-time effects."""
    if not isinstance(node, FUNCTIONS) or node.name.startswith('__') or getattr(node, 'type_params', None):
        return False
    arguments = node.args
    annotated = node.returns is not None or any(
        arg.annotation is not None for arg in arguments.posonlyargs + arguments.args + arguments.kwonlyargs
        + [a for a in (arguments.vararg, arguments.kwarg) if a])
    if not (postponed or not annotated) or not all(
            _literal(d) for d in arguments.defaults + arguments.kw_defaults if d is not None):
        return False
    # Other decorators run at class creation; the caller must prove them pure.
    return tuple(ast.unparse(d) for d in node.decorator_list
                 if not (isinstance(d, ast.Name) and d.id in SAFE_DECORATORS))


def _member_changes(old_body, new_body, postponed, prefix='', in_class=False):
    """Header edits of existing definitions and method additions or removals, else None.

    Every other statement must be identical. Records are ('header', qualname)
    or ('member', class qualname, method name).
    """
    a, b = [ast.dump(s) for s in old_body], [ast.dump(s) for s in new_body]
    changes = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == 'equal':
            continue
        olds = {getattr(s, 'name', None): s for s in old_body[i1:i2]}
        news = {getattr(s, 'name', None): s for s in new_body[j1:j2]}
        if None in olds or None in news or len(olds) != i2 - i1 or len(news) != j2 - j1:
            return None
        for name in olds.keys() | news.keys():
            x, y = olds.get(name), news.get(name)
            if x is not None and y is not None:
                if isinstance(x, ast.ClassDef) and isinstance(y, ast.ClassDef) and all(
                        ast.dump(ast.Tuple(elts=getattr(x, f, []), ctx=ast.Load()))
                        == ast.dump(ast.Tuple(elts=getattr(y, f, []), ctx=ast.Load()))
                        for f in ('bases', 'keywords', 'decorator_list', 'type_params')):
                    inner = _member_changes(x.body, y.body, postponed, prefix + name + '.', True)
                    if inner is None:
                        return None
                    changes.extend(inner)
                elif isinstance(x, FUNCTIONS) and _header_change(x, y, postponed):
                    changes.append(('header', prefix + name))
                elif (in_class and (before := _new_member(x, postponed)) is not False
                      and (after := _new_member(y, postponed)) is not False):
                    # A redefined method changes attribute lookup on its class.
                    changes.append(('member', prefix[:-1], name, tuple(dict.fromkeys(before + after))))
                else:
                    return None
            elif in_class and (decorators := _new_member(x or y, postponed)) is not False:
                changes.append(('member', prefix[:-1], name, decorators))
            else:
                return None
    return changes


def _postponed(tree):
    return any(isinstance(n, ast.ImportFrom) and n.module == '__future__'
               and any(alias.name == 'annotations' for alias in n.names) for n in tree.body)


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

    def ambiguous(name):
        return any(name == dup or name.startswith(dup + '.') for dup in duplicates)

    structural = old_structure != new_structure
    # Structural edits explained entirely by class-level assignment values, with
    # unchanged names, bases, keywords, decorators and statements elsewhere.
    attributes = _class_attribute_changes(before.body, after.body) if structural else None
    if attributes and any(ambiguous(change['cls']) for change in attributes):
        attributes = None
    members = None
    if structural and not attributes and _postponed(before) == _postponed(after):
        members = _member_changes(before.body, after.body, _postponed(before)) or None
        if members and any(ambiguous(change[1]) for change in members):
            members = None
    if any(ambiguous(name) for name in result['functions']) or (
            duplicates and not result['functions'] and not attributes and not members):
        result['reason'] = 'duplicate_scope'
        return result
    result['structural'] = structural
    result['reason'] = 'structural' if structural else 'bodies_or_text'
    result['class_attributes'] = attributes or None
    result['members'] = members
    return result


def literal_generator_override(old, new, base_source):
    """Find one added, side-effect-free override of an existing generator method."""
    if not new.startswith(old):
        return None
    before, after = ast.parse(old), ast.parse(new)
    if not before.body or not after.body:
        return None
    a, b = before.body[-1], after.body[-1]
    if not isinstance(a, ast.ClassDef) or not isinstance(b, ast.ClassDef) or not b.body:
        return None
    method = b.body[-1]
    if (not isinstance(method, ast.FunctionDef) or _bindings(a.body, method.name)
            or _body_reads(a.body, method.name) or b.decorator_list or b.keywords
            or [ast.unparse(base) for base in b.bases] != ['generator.Generator']
            or getattr(b, 'type_params', ()) or not method.name.endswith('_sql')
            or method.name.startswith('_') or method.decorator_list or method.returns
            or getattr(method, 'type_params', ()) or len(method.body) != 1):
        return None
    args = method.args
    if ([arg.arg for arg in args.args] != ['self', 'expression'] or args.posonlyargs or args.kwonlyargs
            or args.vararg or args.kwarg or args.defaults or any(arg.annotation for arg in args.args)):
        return None
    statement = method.body[0]
    if not (isinstance(statement, ast.Return) and isinstance(statement.value, ast.Constant)
            and type(statement.value.value) is str):
        return None
    b.body.remove(method)
    if ast.dump(before) != ast.dump(after):
        return None
    for cls in ast.parse(base_source).body:
        if (isinstance(cls, ast.ClassDef) and cls.name == 'Generator'
                and not (cls.bases or cls.decorator_list or cls.keywords)):
            if _bindings(cls.body, '__init_subclass__'):
                return None
            if any(isinstance(m, ast.FunctionDef) and m.name == method.name and not m.decorator_list
                   for m in cls.body):
                return b.name, method.name
    return None


def _boolean_operands(node):
    if isinstance(node, ast.BoolOp):
        return [operand for value in node.values for operand in _boolean_operands(value)]
    return [ast.dump(node)]


def statement_spans(old, new):
    """Return original executable spans for aligned literal and operator edits."""
    spans = set()
    targets = {
        ast.If: 'test', ast.While: 'test', ast.For: 'iter', ast.AsyncFor: 'iter',
        ast.Return: 'value', ast.Assign: 'value', ast.AnnAssign: 'value',
        ast.Expr: 'value', ast.Raise: 'exc',
    }
    operators = (ast.operator, ast.unaryop, ast.boolop, ast.cmpop)

    def align(before, after, in_function=False, anchor=None):
        if isinstance(before, operators) and isinstance(after, operators):
            if type(before) is type(after):
                return True
            if anchor is None:
                return False
            spans.add(anchor)
            return True
        if type(before) is not type(after):
            return False
        if isinstance(before, list):
            return len(before) == len(after) and all(
                align(a, b, in_function, anchor) for a, b in zip(before, after)
            )
        if not isinstance(before, ast.AST):
            return before == after
        if isinstance(before, ast.Constant):
            if type(before.value) is type(after.value) and before.value == after.value:
                # Preserve signed zero and other representation changes.
                if ast.dump(before) == ast.dump(after):
                    return True
            if anchor is None or type(before.value) is not type(after.value):
                return False
            spans.add(anchor)
            return True
        if (anchor is not None and isinstance(before, ast.BoolOp)
                and (type(before.op) is not type(after.op) or len(before.values) != len(after.values))
                and _boolean_operands(before) == _boolean_operands(after)):
            # Regrouping can change short-circuit order only after the original
            # enclosing statement is reached.
            spans.add(anchor)
            return True
        if isinstance(before, (ast.Lambda,) + OPAQUE):
            return ast.dump(before) == ast.dump(after)
        if isinstance(before, FUNCTIONS) and (
                ast.get_docstring(before, clean=False) != ast.get_docstring(after, clean=False)):
            return False
        for name, child in ast.iter_fields(before):
            inside = in_function
            span = anchor
            if isinstance(before, FUNCTIONS + (ast.ClassDef,)):
                inside = isinstance(before, FUNCTIONS) and name == 'body'
                span = None
            elif inside and targets.get(type(before)) == name and isinstance(child, ast.expr):
                # Start at the statement header to cover a condition's short-circuit paths.
                span = (before.lineno, child.end_lineno)
            if not align(child, getattr(after, name), inside, span):
                return False
        return True

    return spans if align(ast.parse(old), ast.parse(new)) and spans else None
