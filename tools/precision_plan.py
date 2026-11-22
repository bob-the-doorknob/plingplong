"""Find source-closed dictionary and module reads in the pinned tree."""
import ast
from collections import defaultdict
import json
from pathlib import Path
import re
import sys

from structural import SCALARS, literal_mapping, named_literal


def location(node):
    return node.lineno, node.col_offset, node.end_lineno, node.end_col_offset


def function_body(node, parents):
    while node in parents:
        parent = parents[node]
        if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return parent if node in parent.body else None
        if isinstance(parent, ast.Lambda):
            return parent if node is parent.body else None
        if isinstance(parent, ast.ClassDef):
            return None
        node = parent


def receiver(node, parents):
    function = function_body(node, parents)
    if function:
        args = function.args.posonlyargs + function.args.args
        if args and args[0].arg in ('self', 'cls', 'dialect', 'tokenizer'):
            return args[0].arg
    return ''


def key_expression(node, parents):
    parent = parents.get(node)
    if isinstance(parent, ast.Subscript) and parent.value is node and isinstance(parent.ctx, ast.Load):
        return parent.slice
    if isinstance(parent, ast.Compare) and len(parent.ops) == 1 and parent.comparators[0] is node \
            and isinstance(parent.ops[0], (ast.In, ast.NotIn)):
        return parent.left
    if isinstance(parent, ast.Attribute) and parent.attr == 'get':
        call = parents.get(parent)
        if isinstance(call, ast.Call) and call.func is parent and len(call.args) in (1, 2) \
                and not call.keywords and not any(isinstance(arg, ast.Starred) for arg in call.args):
            return call.args[0]
    return None


def dictionary_sites(path, target, nodes, parents):
    if any(isinstance(node, ast.Name) and node.id in ('globals', 'locals', 'eval', 'exec', 'vars')
           for node in nodes):
        return []
    name = target.id
    sites = []
    for node in nodes:
        if isinstance(node, ast.Name) and node.id == name and node is not target:
            key = key_expression(node, parents) if isinstance(node.ctx, ast.Load) else None
            if key is None or function_body(key, parents) is None:
                return []
            sites.append((location(key), path, name, 'key', receiver(key, parents)))
        if (isinstance(node, ast.arg) and node.arg == name
                or isinstance(node, ast.alias) and (node.asname or node.name.split('.')[0]) in ('*', name)
                or isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name
                or isinstance(node, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar)) and node.name == name
                or isinstance(node, ast.MatchMapping) and node.rest == name
                or isinstance(node, (ast.Global, ast.Nonlocal)) and name in node.names):
            return []
    return sites


def package_sites(path, target, trees):
    name = target.id
    sites, uncertain = [], set()
    for file, (nodes, parents) in trees.items():
        aliases = set()
        for node in nodes:
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module == 'sqlglot' \
                    and any(item.name in (name, '*') for item in node.names):
                return [], set()
            if isinstance(node, ast.Import):
                aliases.update(a.asname or 'sqlglot' for a in node.names
                               if a.name == 'sqlglot' or not a.asname and a.name.startswith('sqlglot.'))
            if isinstance(node, ast.Constant) and node.value == 'sqlglot.' + name:
                if not file.startswith('tests/'):
                    return [], set()
                uncertain.add(file)
        for node in nodes:
            if file == path and isinstance(node, ast.Name) and node.id == name and node is not target:
                return [], set()
            if isinstance(node, ast.arg) and node.arg in aliases:
                return [], set()
            if isinstance(node, ast.Name) and node.id in aliases:
                parent = parents.get(node)
                if not isinstance(node.ctx, ast.Load) or not isinstance(parent, ast.Attribute) \
                        or parent.attr in ('__dict__', '__class__', '__getattribute__'):
                    return [], set()
                if parent.attr == name:
                    if not isinstance(parent.ctx, ast.Load):
                        return [], set()
                    sites.append((file, (location(parent), path, name, 'attribute', receiver(parent, parents))))
    return sites, uncertain


def make_plan(sources, guarded=None):
    trees = {}
    for path, source in sources.items():
        tree = ast.parse(source, filename=path)
        nodes = tuple(ast.walk(tree))
        trees[path] = tree, nodes, {child: node for node in nodes for child in ast.iter_child_nodes(node)}
    plan = defaultdict(list)
    for path, (tree, nodes, parents) in trees.items():
        if not path.startswith('sqlglot/'):
            continue
        for statement in tree.body:
            binding = named_literal(statement)
            if not binding:
                continue
            target, value = binding
            name = target.id
            if literal_mapping(value):
                token = re.compile(r'\b' + re.escape(name) + r'\b')
                if any(other != path and token.search(text) for other, text in sources.items()):
                    continue
                plan[path].extend(dictionary_sites(path, target, nodes, parents))
            elif path == 'sqlglot/__init__.py' and isinstance(value, ast.Constant) and type(value.value) in SCALARS:
                sites, uncertain = package_sites(path, target, {file: value[1:] for file, value in trees.items()})
                for file, site in sites:
                    plan[file].append(site)
                if sites and guarded is not None:
                    guarded.setdefault(path, {})[name] = sorted(uncertain)
    return {p: sorted(v) for p, v in sorted(plan.items()) if v}


if __name__ == '__main__':
    root = Path(sys.argv[1])
    source = {p.relative_to(root).as_posix(): p.read_text(encoding='utf-8')
              for folder in ('sqlglot', 'tests') for p in sorted((root / folder).rglob('*.py'))}
    guarded = {}
    print(json.dumps({'files': make_plan(source, guarded), 'guarded': guarded}))
