#!/usr/bin/env python3
"""Offline checks of multi-round conservation, input agreement and CLI behavior."""
import copy
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
import rewardmerge as rm

rs, rr = rm.rs, rm.rr
META = rs.read_json(rr.ROOT / 'zto-mainnet.json')


def entry(label, units=7, rows=None):
    request = {'budget': rs.display_units(units, META['decimals']),
               'contributors': rows if rows is not None else
                   [{'id': 'a', 'weight': '1'}, {'id': 'b', 'weight': '2'}]}
    return {'id': label, 'request': request, 'report': rs.allocate(request, META)}


class MergeTests(unittest.TestCase):
    def test_exact_sum_changing_roster_and_weights(self):
        m = {'rounds': [entry('one'), entry('two', 11, [{'id': 'b', 'weight': '1'}, {'id': 'c', 'weight': '0'}])]}
        report = rm.merge(m, META)
        self.assertEqual(report['budget_units'], '18')
        self.assertEqual([(x['id'], x['units']) for x in report['allocations']], [('a', '2'), ('b', '16'), ('c', '0')])
        self.assertEqual(rm.verify(m, META, report)['report_sha256'], rr.digest(report))

    def test_seeded_conservation(self):
        rng = random.Random(2603)
        for _ in range(100):
            rounds = []
            expected = {}
            for j in range(rng.randint(1, 8)):
                rows = [{'id': chr(97 + k), 'weight': str(rng.randint(1, 100))}
                        for k in range(rng.randint(1, 12))]
                item = entry('round' + str(j), rng.randint(1, 10**25), rows)
                rounds.append(item)
                for row in item['report']['allocations']:
                    expected[row['id']] = expected.get(row['id'], 0) + int(row['units'])
            report = rm.merge({'rounds': rounds}, META)
            self.assertEqual({r['id']: int(r['units']) for r in report['allocations']}, expected)
            self.assertEqual(sum(expected.values()), int(report['budget_units']))

    def test_tampered_round_and_metadata(self):
        for field in ('units', 'amount', 'rounding_unit_awarded'):
            m = {'rounds': [entry('one')]}
            m['rounds'][0]['report']['allocations'][0][field] = 'changed'
            with self.assertRaises(rs.Invalid): rm.merge(m, META)
        m = {'rounds': [entry('one')]}
        meta = dict(META, block_number=META['block_number'] + 1)
        with self.assertRaises(rs.Invalid): rm.merge(m, meta)

    def test_tampered_summary(self):
        m = {'rounds': [entry('one')]}
        report = rm.merge(m, META)
        for field, value in [('budget_units', '8'), ('round_count', True), ('extra', 1)]:
            changed = dict(report, **{field: value})
            with self.assertRaises(rs.Invalid): rm.verify(m, META, changed)

    def test_round_ids_and_shapes(self):
        for m in ({'rounds': []}, {'rounds': [entry('one')] * 2},
                  {'rounds': [entry('bad label')]}, {'rounds': [entry('one')], 'extra': 1},
                  {'rounds': [entry(str(n)) for n in range(65)]}, {'rounds': [False]}):
            with self.assertRaises(rs.Invalid): rm.merge(m, META)

    def test_uint256_bound(self):
        item = entry('one', rs.UINT256_MAX)
        self.assertEqual(rm.merge({'rounds': [item]}, META)['budget_units'], str(rs.UINT256_MAX))
        with self.assertRaises(rs.Invalid): rm.merge({'rounds': [item, entry('two', 1)]}, META)

    def test_repeated_reports_remain_visible_and_counted(self):
        m = {'rounds': [entry('one'), entry('two')]}
        report = rm.merge(m, META)
        self.assertTrue(report['review_required'])
        self.assertEqual(report['repeated_reports'][0]['rounds'], ['one', 'two'])
        self.assertEqual(report['budget_units'], '14')

    def test_no_invented_addresses(self):
        report = rm.merge({'rounds': [entry('one')]}, META)
        self.assertFalse(report['all_recipients_supplied'])
        self.assertTrue(all('address' not in row for row in report['allocations']))

    def test_address_consistency_using_real_token_identifiers(self):
        # Known public contract identifiers exercise string identity only, never recipients.
        zto, imd = rs.TOKENS.values()
        def addressed(label, identifier, address):
            return entry(label, rows=[{'id': identifier, 'weight': '1', 'address': address}])
        first = addressed('one', 'a', zto)
        for second in (addressed('two', 'a', imd), addressed('two', 'b', zto), entry('two')):
            with self.assertRaises(rs.Invalid): rm.merge({'rounds': [first, second]}, META)
        result = rm.merge({'rounds': [first, addressed('two', 'a', zto.upper().replace('0X', '0x'))]}, META)
        self.assertEqual(result['allocations'][0]['address'], zto)

    def test_round_order_changes_provenance_not_totals(self):
        m = {'rounds': [entry('one'), entry('two', 9)]}
        before = rm.merge(m, META)
        after = rm.merge({'rounds': list(reversed(m['rounds']))}, META)
        self.assertEqual(before['allocations'], after['allocations'])
        self.assertEqual(before['round_receipts'], after['round_receipts'])
        self.assertNotEqual(before['manifest_sha256'], after['manifest_sha256'])

    def test_cli_files_exits_and_no_overwrite(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd() / 'test' / 'scratch') as folder:
            root = Path(folder)
            manifest = root / 'input.json'
            report = root / 'report.json'
            command = [sys.executable, '-B', str(Path(rm.__file__).resolve())]
            manifest.write_text(json.dumps({'rounds': [entry('one'), entry('two', 8)]}))
            def run(*args): return subprocess.run(command + list(args), capture_output=True, text=True)
            self.assertEqual(run('merge', '--manifest', str(manifest), '--output', str(report)).returncode, 0)
            self.assertEqual(run('verify', '--manifest', str(manifest), '--report', str(report)).returncode, 0)
            self.assertEqual(run('merge', '--manifest', str(manifest), '--output', str(report)).returncode, 2)
            manifest.write_text(json.dumps({'rounds': [entry('one'), entry('two')]}))
            self.assertEqual(run('merge', '--manifest', str(manifest)).returncode, 1)
            manifest.write_text('{"rounds":[],"rounds":[]}')
            self.assertEqual(run('merge', '--manifest', str(manifest)).returncode, 2)


if __name__ == '__main__':
    (Path.cwd() / 'test' / 'scratch').mkdir(parents=True, exist_ok=True)
    unittest.main()
