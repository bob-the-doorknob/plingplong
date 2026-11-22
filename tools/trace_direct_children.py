"""Record complete file footprints for direct, isolated Python subprocesses."""
import atexit
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import trace_events

ROOT = Path('/tmp/direct-children')
TOKEN = 'BR_DIRECT_TOKEN'
launches = {}
uncertain = set()
read_paths = set()


def instrumented_python(argv, positional, options):
    return (
        not positional and not options.get('shell') and options.get('executable') is None
        and options.get('env') is None
        and isinstance(argv, (list, tuple)) and len(argv) == 3
        and all(isinstance(value, str) for value in argv) and argv[1] == '-c'
        and os.path.realpath(shutil.which(argv[0]) or '') == os.path.realpath(sys.executable)
    )


def source_path(target):
    path = os.path.realpath(os.fsdecode(target))
    if not path.startswith('/src/'):
        return None
    if path.endswith('.pyc'):
        try:
            path = importlib.util.source_from_cache(path)
        except ValueError:
            return None
    return path[5:]


def start():
    token = os.environ.get(TOKEN)

    def audit(event, args):
        if event == 'open' and token and isinstance(args[0], (str, bytes)):
            path = source_path(args[0])
            if path:
                read_paths.add(path)
        elif event in ('os.system', 'os.exec', 'os.fork', 'os.forkpty'):
            uncertain.add(trace_events.context)

    sys.addaudithook(audit)
    constructor = subprocess.Popen.__init__
    wait = subprocess.Popen.wait

    def launch(process, args, *positional, **options):
        owner = trace_events.context
        if token or '::' not in owner or not instrumented_python(args, positional, options):
            uncertain.add(owner)
            return constructor(process, args, *positional, **options)
        key = f'{os.getpid()}-{len(launches)}'
        record = launches[key] = {'owner': owner, 'pid': None, 'status': None}
        options['env'] = dict(os.environ, **{TOKEN: key, 'BR_OWNER': owner})
        constructor(process, args, *positional, **options)
        process._blast_radius_direct = key
        record['pid'] = process.pid

    def wait_logged(process, *args, **options):
        status = wait(process, *args, **options)
        key = getattr(process, '_blast_radius_direct', None)
        if key in launches:
            launches[key]['status'] = status
        return status

    def finish():
        report = dict(token=token, order=os.environ.get('BR_REVERSE', '0'),
                      launches=launches, uncertain=sorted(uncertain), paths=sorted(read_paths))
        (ROOT / f'{os.getpid()}.json').write_text(json.dumps(report))

    subprocess.Popen.__init__ = launch
    subprocess.Popen.wait = wait_logged
    atexit.register(finish)
