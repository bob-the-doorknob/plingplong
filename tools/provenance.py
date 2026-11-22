"""Verify a local Docker image against a Git tree and record its diagnostic run."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

FILES = ('selector.py', 'hybrid.py', 'semantic.py', 'impact.py', 'numeric.py', 'predicate.py',
         'evidence.gz', 'lines.gz', 'predicates.gz')


def output(*args):
    return subprocess.check_output(args)


def main(commit, image, patches):
    sha = output('git', 'rev-parse', commit).decode().strip()
    image_id = output('docker', 'image', 'inspect', image, '--format', '{{.Id}}').decode().strip()
    flags = ('docker', 'run', '--rm', '--platform', 'linux/amd64', '--network', 'none',
             '--cpus', '2', '--memory', '4096m', '--memory-swap', '4096m', '--pids-limit', '256',
             '--read-only', '--tmpfs', '/tmp:rw,size=64m,mode=1777', '--cap-drop', 'ALL',
             '--security-opt', 'no-new-privileges', '--user', '65534:65534', '-e', 'HOME=/tmp')
    packaged = output(*flags, image_id, 'python', '-c',
                      'import hashlib,pathlib,sys\nprint(sys.version.split()[0])\n'
                      'for name in sys.argv[1:]:\n print(hashlib.sha256(pathlib.Path("/app",name).read_bytes()).hexdigest())',
                      *FILES).decode().splitlines()
    digests = {file: sha256(output('git', 'cat-file', 'blob', f'{sha}:{file}')).hexdigest() for file in FILES}
    if packaged[1:] != list(digests.values()):
        raise SystemExit('image contents differ from Git blobs')
    catalog = Path('blast-radius-sample/sample/tests.json').resolve()
    payload = output(*flags, '-v', f'{Path(patches).resolve()}:/data/commits:ro',
                     '-v', f'{catalog}:/data/tests.json:ro', image_id)
    print(json.dumps(dict(commit=sha, image=image_id, python=packaged[0], files=digests,
                          patches={p.name: sha256(p.read_bytes()).hexdigest() for p in sorted(Path(patches).glob('*.patch'))},
                          catalog=sha256(catalog.read_bytes()).hexdigest(),
                          output=sha256(payload).hexdigest()), indent=2))


if __name__ == '__main__':
    main(*sys.argv[1:])

