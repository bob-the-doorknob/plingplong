import os
import sys
import tempfile
import importlib._bootstrap as bootstrap

context = os.environ.get('BR_OWNER', '*')
seen = set()
log = None

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

def start():
    global log
    log = tempfile.NamedTemporaryFile(mode='w', dir='/tmp/events', delete=False, buffering=1)
    original_load = bootstrap._load_unlocked
    def shared_import(spec):
        global context
        previous = context
        context = '*'
        sys.monitoring.restart_events()
        try:
            return original_load(spec)
        finally:
            context = previous
            sys.monitoring.restart_events()
    bootstrap._load_unlocked = shared_import
    sys.addaudithook(audit)
    m = sys.monitoring
    m.use_tool_id(3, 'blast-radius')
    m.register_callback(3, m.events.PY_START, entry)
    m.set_events(3, m.events.PY_START)

def owner(name):
    global context
    context = name
    # Pool workers can outlive a test. Attribute child observations to its file.
    os.environ['BR_OWNER'] = name.split('::')[0]
    sys.monitoring.restart_events()
