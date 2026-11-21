import atexit
import builtins
import enum
import json
import linecache
import os
import sys
import tempfile
import types
import importlib._bootstrap as bootstrap

SRC = '/src/'
context = os.environ.get('BR_OWNER', '*')
seen = set()
log = None

# Class attribute evidence. Records written to the event log:
#   R <class>                   a test read any attribute of an instance or of the class
#   A <defining class>@<name>   a test read a class-body attribute provided by that class
#   W <class>@<name>            a test wrote or deleted a class attribute
#   I <defining class>@<name> <consumer>
#                               an import-time read while building <consumer>, or
#                               <module> outside any class body or metaclass
#   C cache                     the test changed sqlglot module globals or class-level containers
# Only instrumented classes carry evidence: classes built by sqlglot code whose
# metaclass is type or a sqlglot metaclass, plus their subclasses.
epoch = object()
busy = [False]
candidates = frozenset()
build_stack = []
registry = []
class_keys = {}
defining_cache = {}
receiver_epoch = {}
attribute_epoch = {}
traced_metas = {}
traced_set = set()
plain_of = {}
hooked = set()
CONTAINERS = {dict, list, set}
last_snapshot = None
last_test = None
LINE_ONLY = os.environ.get('BR_LINES') == '1'
line_hits = {}
current_lines = set()


def line_event(code, line, disable=getattr(getattr(sys, 'monitoring', None), 'DISABLE', None)):
    path = code.co_filename
    if path.startswith('/src/sqlglot/'):
        current_lines.add((path[5:], line))
    return disable


def flush_lines():
    for path, line in current_lines:
        line_hits.setdefault(path, {}).setdefault(line, set()).add(context)
    current_lines.clear()


def dump_lines():
    flush_lines()
    with open(f'/tmp/lines/{os.getpid()}.json', 'w') as f:
        json.dump({p: {n: sorted(ids) for n, ids in lines.items()}
                   for p, lines in line_hits.items()}, f)



def record(key):
    pair = (context, key)
    if pair not in seen:
        seen.add(pair)
        log.write(context + '\t' + key + '\n')


def entry(code, offset):
    path = code.co_filename
    if path.startswith('/src/sqlglot/'):
        record(path[5:] + '::' + code.co_qualname)
    return sys.monitoring.DISABLE


def audit(event, args):
    if event == 'open' and isinstance(args[0], (str, bytes)):
        path = os.path.abspath(os.fsdecode(args[0]))
        if path.startswith(('/src/sqlglot/', '/src/tests/fixtures/')):
            record(path[5:])
    elif event in ('subprocess.Popen', 'os.system', 'os.fork'):
        record('!untraced')


def class_key(cls):
    # Keyed by id: sqlglot metaclasses define Python __hash__/__eq__, which would
    # run (and be traced) on every lookup. The stored class keeps the id valid.
    cached = class_keys.get(id(cls))
    key = cached and cached[0]
    if key is None:
        get = type.__getattribute__
        module_name = get(cls, '__module__')
        path = getattr(sys.modules.get(module_name), '__file__', None) or ''
        where = path[len(SRC):] if path.startswith(SRC) else '?' + str(module_name)
        key = where + '::' + get(cls, '__qualname__')
        class_keys[id(cls)] = (key, cls)
    return key


def defining(cls, name):
    key = (id(cls), name)
    found = defining_cache.get(key, defining_cache)
    if found is defining_cache:
        found = None
        get = type.__getattribute__
        for klass in get(cls, '__mro__'):
            if name in get(klass, '__dict__'):
                found = class_key(klass)
                break
        defining_cache[key] = found
    return found


def note_read(cls, name, on_class):
    busy[0] = True
    try:
        generic = on_class and name == '__dict__'
        if context == '*':
            if name[:2] != '__' or generic:
                where = class_key(cls) if generic else defining(cls, name)
                if where is not None:
                    record('I\t' + where + '@' + name + '\t' + (build_stack[-1] if build_stack else '<module>'))
            return
        if receiver_epoch.get(id(cls)) is not epoch:
            receiver_epoch[id(cls)] = epoch
            record('R\t' + class_key(cls))
        if generic or name in candidates:
            key = (id(cls), name)
            if attribute_epoch.get(key) is not epoch:
                attribute_epoch[key] = epoch
                where = class_key(cls) if generic else defining(cls, name)
                if where is not None:
                    record('A\t' + where + '@' + name)
    finally:
        busy[0] = False


def note_write(cls, name):
    defining_cache.clear()
    if context != '*' and not busy[0]:
        busy[0] = True
        try:
            record('W\t' + class_key(cls) + '@' + name)
        finally:
            busy[0] = False


class TracingMeta(type):
    """Mixin metaclass reporting class-level reads and writes; cooperative with sqlglot metaclasses."""

    def __getattribute__(cls, name):
        value = type.__getattribute__(cls, name)
        if not busy[0]:
            note_read(cls, name, True)
        return value

    def __setattr__(cls, name, value):
        super().__setattr__(name, value)
        note_write(cls, name)

    def __delattr__(cls, name):
        super().__delattr__(name)
        note_write(cls, name)

    def __new__(mcls, *args, **kwargs):
        cls = super().__new__(mcls, *args, **kwargs)
        registry.append(cls)
        return cls


traced_set.add(TracingMeta)
plain_of[TracingMeta] = type


def traced(meta):
    """The tracing counterpart of meta; traced(M) subclasses traced(B) for every metaclass base B."""
    if meta is type:
        return TracingMeta
    result = traced_metas.get(meta)
    if result is None:
        bases = tuple(traced(b) for b in meta.__bases__ if isinstance(b, type) and issubclass(b, type))
        result = type.__new__(type, 'Traced' + meta.__name__, bases + (meta,), {'__module__': meta.__module__})
        traced_metas[meta] = result
        traced_set.add(result)
        plain_of[result] = meta
    return result


def hook_instances(cls):
    original = type.__getattribute__(cls, '__getattribute__')

    def __getattribute__(self, name):
        value = original(self, name)
        if not busy[0]:
            note_read(type(self), name, False)
        return value

    type.__setattr__(cls, '__getattribute__', __getattribute__)
    hooked.add(id(cls))


def most_derived(metas):
    winner = type
    for meta in metas:
        if issubclass(meta, winner):
            winner = meta
        elif not issubclass(winner, meta):
            return None
    return winner


def build_class(func, name, *bases, **kwargs):
    filename = func.__code__.co_filename
    sqlglot = filename.startswith('/src/sqlglot/')
    resolved = types.resolve_bases(bases)
    metas = [type(b) for b in resolved]
    explicit = kwargs.get('metaclass')
    if ((sqlglot or any(m in traced_set for m in metas))
            and not any(isinstance(b, type) and issubclass(b, type) for b in resolved)
            and (explicit is None or isinstance(explicit, type))):
        winner = most_derived([plain_of.get(m, m) for m in ([explicit] if explicit else []) + metas])
        if winner is not None and not issubclass(winner, enum.EnumMeta):
            kwargs['metaclass'] = traced(winner)
    build_stack.append(filename[len(SRC):] + '::' + func.__qualname__ if filename.startswith(SRC) else '<module>')
    try:
        cls = original_build_class(func, name, *bases, **kwargs)
    finally:
        build_stack.pop()
    if sqlglot and type(cls) in traced_set and not any(id(k) in hooked for k in type.__getattribute__(cls, '__mro__')):
        hook_instances(cls)
    return cls


original_build_class = builtins.__build_class__


def snapshot():
    state = {}
    for name, module in list(sys.modules.items()):
        if name == 'sqlglot' or name.startswith('sqlglot.'):
            for key, value in list(vars(module).items()):
                if type(value) is not types.ModuleType:
                    state[(name, key)] = (id(value), len(value) if type(value) in CONTAINERS else -1)
    get = type.__getattribute__
    for cls in registry:
        if class_key(cls).startswith('sqlglot/'):
            for key, value in list(get(cls, '__dict__').items()):
                if type(value) in CONTAINERS:
                    state[(id(cls), key)] = (id(value), len(value))
    return state


def boundary(nodeid):
    """Compare sqlglot globals and class containers with the previous test boundary."""
    global last_snapshot, last_test
    if LINE_ONLY:
        return
    busy[0] = True
    try:
        current = snapshot()
        if last_snapshot is not None and last_test is not None:
            owners = {key[0] for key in last_snapshot}
            if any(current.get(key) != value for key, value in last_snapshot.items()) or any(
                    key[0] in owners for key in current.keys() - last_snapshot.keys()):
                log.write(last_test + '\tC\tcache\n')
        last_snapshot, last_test = current, nodeid
    finally:
        busy[0] = False


def dump_classes():
    busy[0] = True
    bases = {}
    for cls in registry:
        bases.setdefault(class_key(cls), set()).update(class_key(b) for b in type.__getattribute__(cls, '__bases__'))
    os.makedirs('/tmp/classes', exist_ok=True)
    with open(f'/tmp/classes/{os.getpid()}.json', 'w') as f:
        json.dump({key: sorted(value) for key, value in bases.items()}, f)


def start():
    global log, candidates
    log = tempfile.NamedTemporaryFile(mode='w', dir='/tmp/events', delete=False, buffering=1)
    try:
        with open('/tmp/candidates.json') as f:
            candidates = frozenset(json.load(f))
    except OSError:
        pass
    original_load = bootstrap._load_unlocked
    def shared_import(spec):
        global context, epoch
        if LINE_ONLY:
            flush_lines()
        previous = context, epoch
        context, epoch = '*', object()
        sys.monitoring.restart_events()
        try:
            return original_load(spec)
        finally:
            if LINE_ONLY:
                flush_lines()
            context, epoch = previous
            sys.monitoring.restart_events()
    bootstrap._load_unlocked = shared_import
    if LINE_ONLY:
        os.makedirs('/tmp/line-started', exist_ok=True)
        with open(f'/tmp/line-started/{os.getpid()}.json', 'w') as f:
            json.dump(dict(owner=context, order=os.environ.get('BR_REVERSE', '0')), f)
        m = sys.monitoring
        m.use_tool_id(3, 'blast-radius-lines')
        m.register_callback(3, m.events.LINE, line_event)
        m.set_events(3, m.events.LINE)
        atexit.register(dump_lines)
        return
    builtins.__build_class__ = build_class
    atexit.register(dump_classes)
    sys.addaudithook(audit)
    m = sys.monitoring
    m.use_tool_id(3, 'blast-radius')
    m.register_callback(3, m.events.PY_START, entry)
    m.set_events(3, m.events.PY_START)


def owner(name):
    global context, epoch
    if LINE_ONLY:
        flush_lines()
    context = name
    epoch = object()
    # Every reader of a source file opens it again rather than hitting the cache.
    linecache.clearcache()
    # Pool workers can outlive a test. Attribute child observations to its file.
    os.environ['BR_OWNER'] = name.split('::')[0]
    sys.monitoring.restart_events()
