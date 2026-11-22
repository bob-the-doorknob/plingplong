"""Validate both direct-child process ledgers before narrowing uncertainty."""
import json
from pathlib import Path


def complete_footprints(root, owner_indexes, historical_uncertain, startup, executed):
    reports = {int(path.stem): json.loads(path.read_text()) for path in Path(root).glob('*.json')}
    missing = set()
    observed = {}

    for report in reports.values():
        order = report['order']
        for owner in report['uncertain']:
            missing.update(historical_uncertain if owner == '*' else owner_indexes.get(owner, ()))
        for token, launch in report['launches'].items():
            owner = launch['owner']
            indexes = owner_indexes.get(owner, set()) & historical_uncertain
            for index in indexes:
                pid = str(launch['pid'])
                child = reports.get(launch['pid'], {})
                paths = set(child.get('paths', ()))
                started = startup.get(pid + '.json', {})
                observed_files = executed.get(pid, set())
                if (launch['status'] != 0 or child.get('token') != token
                        or child.get('order') != order or child.get('uncertain')
                        or started.get('owner') != owner or started.get('order') != order
                        or 'sqlglot/__init__.py' not in observed_files
                        or not observed_files <= paths):
                    missing.add(index)
                    continue
                by_order = observed.setdefault(index, {})
                by_order.setdefault(order, set()).update(paths)

    return {str(index): sorted(by_order['0'] | by_order['1'])
            for index, by_order in sorted(observed.items())
            if index not in missing and by_order.keys() == {'0', '1'}}
