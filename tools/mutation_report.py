"""Record numbered parent IDs, including failed subtests, only for mutation evaluation."""
import json
import os
failures = set()

def pytest_runtest_logreport(report):
    if report.failed:
        failures.add(report.nodeid)

def pytest_sessionfinish(session, exitstatus):
    with open('/repo/.phase5/'+os.environ['BR_MUTATION']+'.json','w') as f:
        json.dump(sorted(failures),f)
