#!/usr/bin/env python3
"""Exercise the four lines together on saved public bytes, without sending anything."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parent.parent


def main():
    if Path.cwd().resolve() != ROOT:
        raise SystemExit('run from repository root')
    scratch = ROOT / 'test/scratch'
    scratch.mkdir(parents=True, exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory(prefix='gathering26-', dir=scratch) as directory:
        work = Path(directory)
        archives = []
        for label, source in [('old', 'shared/api_bundle/imd-openapi.json'),
                              ('new', 'gathering/imd-openapi-current-26.json')]:
            archive_path = work / (label + '.zip')
            with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_STORED if label == 'old' else zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('openapi.json', (ROOT / source).read_bytes())
                archive.writestr('inert-note.txt', 'public API description only\n')
            archives.append((str(archive_path.relative_to(ROOT)),
                             hashlib.sha256(archive_path.read_bytes()).hexdigest()))
        old, new = archives
        unpacked = str((work / 'unpacked').relative_to(ROOT))
        report = str((work / 'allocation.json').relative_to(ROOT))
        batch = str((work / 'batch.json').relative_to(ROOT))
        window = str((work / 'window.json').relative_to(ROOT))
        plan = str((work / 'plan.json').relative_to(ROOT))
        planning_tasks = 'line-1/tools/optplan/idle-example.json'
        produced = subprocess.run([sys.executable, '-B', 'line-1/tools/optplan/optplan.py',
                                   '--input', planning_tasks, '--workers', '2'],
                                  capture_output=True, text=True, check=True, timeout=30)
        (work / 'plan.json').write_text(produced.stdout)
        request = 'line-3/tools/rewardsplit/example.json'
        metadata = 'line-3/tools/rewardsplit/zto-mainnet.json'
        # Two illustrative independent rounds: use the actual shipped allocator,
        # original address-free roster and historical real ZTO metadata.
        import importlib.util
        spec = importlib.util.spec_from_file_location('gathering_merge', ROOT / 'line-3/tools/rewardmerge/rewardmerge.py')
        rm = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rm)
        token = rm.rs.read_json(metadata)
        first = rm.rs.read_json(request)
        second = dict(first, budget='2')
        rounds = [{'id': label, 'request': req, 'report': rm.rs.allocate(req, token)}
                  for label, req in [('first', first), ('second', second)]]
        manifest = str((work / 'rounds.json').relative_to(ROOT))
        repeated = str((work / 'repeated.json').relative_to(ROOT))
        merged = str((work / 'merged.json').relative_to(ROOT))
        Path(manifest).write_text(json.dumps({'rounds': rounds}))
        Path(repeated).write_text(json.dumps({'rounds': [rounds[0], dict(rounds[0], id='again')]}))
        jobs = [
            ('fixed worker order slack at deadline', 'line-1/tools/slackmap/slackmap.py',
             ['--tasks', planning_tasks, '--plan', plan, '--workers', '2', '--budget', '16'], 0),
            ('fixed worker order rejects short budget', 'line-1/tools/slackmap/slackmap.py',
             ['--tasks', planning_tasks, '--plan', plan, '--workers', '2', '--budget', '15'], 2),
            ('compare repacked fresh public description trees', 'line-2/tools/zipdiff/zipdiff.py',
             [old[0], new[0], '--before-sha256', old[1], '--after-sha256', new[1], '--seconds', '10'], 0),
            ('merge independent ZTO rounds', 'line-3/tools/rewardmerge/rewardmerge.py',
             ['merge', '--manifest', manifest, '--metadata', metadata, '--output', merged], 0),
            ('verify cumulative ZTO units', 'line-3/tools/rewardmerge/rewardmerge.py',
             ['verify', '--manifest', manifest, '--metadata', metadata, '--report', merged], 0),
            ('flag repeated ZTO allocation without hiding totals', 'line-3/tools/rewardmerge/rewardmerge.py',
             ['merge', '--manifest', repeated, '--metadata', metadata], 1),
            ('independently validate intentional waiting', 'line-1/tools/plancheck/plancheck.py',
             ['--tasks', planning_tasks, '--plan', plan, '--workers', '2', '--budget', '16'], 0),
            ('reject external deadline despite optimality claim', 'line-1/tools/plancheck/plancheck.py',
             ['--tasks', planning_tasks, '--plan', plan, '--workers', '2', '--budget', '15'], 2),
            ('scan consecutive ZTO budgets', 'line-3/tools/rewardwindow/rewardwindow.py',
             ['scan', '--request', request, '--metadata', metadata, '--steps', '3', '--output', window], 0),
            ('verify complete ZTO window', 'line-3/tools/rewardwindow/rewardwindow.py',
             ['verify', '--request', request, '--metadata', metadata, '--report', window], 0),

            ('exact plan', 'line-1/tools/optplan/optplan.py', ['--demo', '--workers', '2'], 0),
            ('approved ZIP extraction', 'line-2/tools/safezip/safezip.py',
             ['extract', new[0], unpacked, '--sha256', new[1], '--seconds', '10'], 0),
            ('audit extracted public description', 'line-2/tools/zipaudit/zipaudit.py',
             [new[0], unpacked, '--sha256', new[1], '--seconds', '10', '--nodes', '2'], 0),
            ('exact ZTO allocation', 'line-3/tools/rewardsplit/rewardsplit.py',
             ['allocate', '--input', request, '--metadata', metadata, '--output', report], 0),
            ('verified receipt', 'line-3/tools/rewardreceipt/rewardreceipt.py',
             ['verify', '--request', request, '--metadata', metadata, '--report', report], 0),
            ('build review batches', 'line-3/tools/rewardbatch/rewardbatch.py',
             ['build', '--request', request, '--report', report, '--metadata', metadata,
              '--batch-size', '2', '--output', batch], 0),
            ('verify review batches', 'line-3/tools/rewardbatch/rewardbatch.py',
             ['verify', '--request', request, '--report', report, '--metadata', metadata,
              '--bundle', batch], 0),
            ('budget paradox warning', 'line-3/tools/rewardcompare/rewardcompare.py', ['demo'], 1),
            ('fresh public API comparison', 'line-4/tools/dependcheck/dependcheck.py',
             ['compare', 'shared/api_bundle/imd-openapi.json', 'gathering/imd-openapi-current-26.json'], 0),
            ('approved shared ZIP comparison', 'shared/api_bundle/api_bundle.py',
             [old[0], new[0], '--old-sha256', old[1], '--new-sha256', new[1],
              '--seconds', '10', '--nodes', '2'], 0),
            ('reject too-small shared node budget', 'shared/api_bundle/api_bundle.py',
             [old[0], new[0], '--nodes', '1'], 2),
        ]
        for label, script, args, expected in jobs:
            command = [sys.executable, '-B', script, *args]
            completed = subprocess.run(command, cwd=ROOT, capture_output=True,
                                       text=True, timeout=30)
            results.append(dict(label=label, command=command, expected_exit=expected,
                                exit=completed.returncode,
                                passed=completed.returncode == expected,
                                stdout=completed.stdout, stderr=completed.stderr))
        if (work / 'unpacked/openapi.json').read_bytes() != (ROOT / 'gathering/imd-openapi-current-26.json').read_bytes():
            raise AssertionError('extracted public description differs from capture')
        allocation = json.loads((work / 'allocation.json').read_text())
        if sum(int(row['units']) for row in allocation['allocations']) != 10**18:
            raise AssertionError('ZTO allocation failed conservation')
        by_label = {r['label']: r for r in results}
        warning = json.loads(by_label['budget paradox warning']['stdout'])
        if warning['contributors_moving_against_budget'] != ['d', 'e']:
            raise AssertionError('illustrative budget paradox was not flagged')
        bundle = json.loads(by_label['approved shared ZIP comparison']['stdout'])
        if bundle['operations_compared'] != 5 or bundle['findings']:
            raise AssertionError('unchanged public API comparison differed')
        slack = json.loads(by_label['fixed worker order slack at deadline']['stdout'])
        assert slack['minimum_finish_in_model'] == '16' and slack['deadline_slack'] == '0'
        diff = json.loads(by_label['compare repacked fresh public description trees']['stdout'])
        assert diff['trees_equal'] and not diff['archive_bytes_equal']
        total = json.loads(Path(merged).read_text())
        assert sum(int(r['units']) for r in total['allocations']) == 3 * 10**18
        assert not total['all_recipients_supplied'] and not total['review_required']
        repeated_total = json.loads(by_label['flag repeated ZTO allocation without hiding totals']['stdout'])
        assert repeated_total['review_required'] and int(repeated_total['budget_units']) == 2 * 10**18
        batches = json.loads((work / 'batch.json').read_text())
        assert batches['batch_count'] == 2
        assert sum(int(b['units']) for b in batches['batches']) == 10**18
        assert [r for b in batches['batches'] for r in b['allocations']] == allocation['allocations']
    (ROOT / 'gathering/integration-results-26.json').write_text(json.dumps(results, indent=2) + '\n')
    for row in results:
        print(('PASS' if row['passed'] else 'FAIL'), row['label'], 'exit', row['exit'])
    return 0 if all(row['passed'] for row in results) else 1


if __name__ == '__main__':
    sys.exit(main())
