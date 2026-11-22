"""Stable structural comparisons for the experimental verifier."""
from enum import Enum
from hashlib import sha256
import json
import math
from types import CodeType, FunctionType, ModuleType


def qualified(value):
    return value.__module__, value.__qualname__


def fingerprint(root, project=None):
    refs, objects = {}, []

    def encode(value):
        kind = type(value)
        if value is None or kind in (str, bool, int):
            return kind.__name__, value
        if kind is float and not math.isnan(value):
            return 'float', value.hex()
        if kind is bytes:
            return 'bytes', value.hex()
        if isinstance(value, Enum):
            return 'enum', qualified(kind), value.name
        if isinstance(value, type):
            return 'class-reference', qualified(value)
        if kind is ModuleType:
            return 'module-reference', value.__name__
        key = id(value)
        if key in refs:
            return 'ref', refs[key]
        index = refs[key] = len(objects)
        # Keep projected scratch containers alive until the walk completes.
        objects.append([value, None])
        if kind is dict:
            state = [(encode(k), encode(v)) for k, v in value.items()]
        elif kind in (tuple, list):
            state = [encode(v) for v in value]
        elif kind in (set, frozenset):
            # Preserve observed order. Identity-hashed members may prevent equivalence across runs.
            state = [encode(v) for v in value]
        elif kind is CodeType:
            state = encode((value.co_code, value.co_consts, value.co_names, value.co_varnames,
                            value.co_freevars, value.co_cellvars, value.co_exceptiontable,
                            value.co_flags, value.co_argcount, value.co_posonlyargcount,
                            value.co_kwonlyargcount, value.co_stacksize))
        elif kind is FunctionType:
            state = encode((qualified(value), value.__code__, value.__defaults__, value.__kwdefaults__,
                            tuple(cell.cell_contents for cell in value.__closure__ or ()), value.__dict__))
        elif project is not None:
            state = encode(project(value))
        else:
            raise TypeError(kind)
        objects[index][1] = (qualified(kind), state)
        return 'ref', index

    address = encode(root)
    payload = json.dumps([address, [pair[1] for pair in objects]], separators=(',', ':'), allow_nan=False)
    return sha256(payload.encode('utf-8')).hexdigest()
