"""Recognize a single identity/equality swap, leaving operands and context intact."""
import ast

OPPOSITE = {ast.Is: ast.Eq, ast.Eq: ast.Is, ast.IsNot: ast.NotEq, ast.NotEq: ast.IsNot}


def supported(node):
    return (
        isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in OPPOSITE
        and all(isinstance(operand, (ast.Name, ast.Attribute))
                or (isinstance(operand, ast.Constant)
                    and (operand.value is None or operand.value is True or operand.value is False))
                for operand in (node.left, node.comparators[0]))
    )


def comparison_swap(old, new):
    before, after = ast.parse(old), ast.parse(new)
    mismatch = []
    for a, b in zip(ast.walk(before), ast.walk(after)):
        if supported(a) and supported(b) and type(a.ops[0]) is not type(b.ops[0]):
            if OPPOSITE[type(a.ops[0])] is not type(b.ops[0]):
                return None
            mismatch.append((a, b))
    if len(mismatch) != 1:
        return None
    a, b = mismatch[0]
    a.ops = b.ops
    if ast.dump(before) == ast.dump(after):
        return f'{a.lineno}:{a.col_offset}'
    return None
