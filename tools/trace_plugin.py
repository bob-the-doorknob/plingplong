import json
import pytest
import trace_events as trace

def pytest_collection_finish(session):
    with open('/tmp/collected.json','w') as f:
        json.dump([i.nodeid for i in session.items], f)

@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    trace.boundary(item.nodeid)
    trace.owner(item.nodeid.split('::')[0])

@pytest.hookimpl(tryfirst=True)
def pytest_runtest_call(item):
    trace.owner(item.nodeid)

@pytest.hookimpl(tryfirst=True)
def pytest_runtest_teardown(item):
    trace.owner(item.nodeid.split('::')[0])
import os

def pytest_collection_modifyitems(items):
    if os.environ.get('BR_REVERSE') == '1':
        items.reverse()

passed = set()
failed = set()
def pytest_runtest_logreport(report):
    if report.failed:
        failed.add(report.nodeid)
    if report.when == 'call' and report.passed:
        passed.add(report.nodeid)

def pytest_sessionfinish(session, exitstatus):
    trace.boundary(None)
    if exitstatus in (0, 1):
        with open('/tmp/pass'+os.environ.get('BR_REVERSE','0')+'.json','w') as f:
            json.dump(dict(passed=sorted(passed), failed=sorted(failed)), f)
