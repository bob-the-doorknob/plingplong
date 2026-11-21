"""Record numbered parent IDs, including failed subtests, only for mutation evaluation."""
import json
import os
from pathlib import Path
failures = set()

def pytest_runtest_logreport(report):
    if report.failed:
        failures.add(report.nodeid)

def pytest_sessionfinish(session, exitstatus):
    output = Path('/repo/.phase5') / os.environ['BR_MUTATION']
    output.with_suffix('.json').write_text(json.dumps(sorted(failures)))
    output.with_suffix('.exit').write_text(str(int(exitstatus)))
