#!/usr/bin/env python3
"""Verify and total bounded independent ZTO allocation rounds, without payments."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import sys

SPEC = importlib.util.spec_from_file_location(
    'rewardreceipt', Path(__file__).resolve().parents[1] / 'rewardreceipt' / 'rewardreceipt.py')
rr = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rr)
rs = rr.rs
MAX_ROUNDS = 64


def merge(manifest, metadata):
    """Recompute each allocation before aggregating; never infer missing recipients."""
    rs.require(isinstance(manifest, dict) and set(manifest) == {'rounds'},
               'manifest must contain exactly rounds')
    rounds = manifest['rounds']
    rs.require(isinstance(rounds, list) and 1 <= len(rounds) <= MAX_ROUNDS,
               'rounds must contain between 1 and 64 entries')
    ids, people, recipients, hashes = set(), {}, {}, {}
    receipts, total = [], 0
    for entry in rounds:
        rs.require(isinstance(entry, dict) and set(entry) == {'id', 'request', 'report'},
                   'each round must contain exactly id, request and report')
        label = entry['id']
        rs.require(isinstance(label, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', label),
                   'round id must be 1-64 ASCII letters, digits, dots, underscores or hyphens')
        rs.require(label not in ids, 'duplicate round id: ' + label)
        ids.add(label)
        receipt = rr.verify(entry['request'], entry['report'], metadata)
        hashes.setdefault(receipt['report_sha256'], []).append(label)
        total += int(entry['report']['budget_units'])
        rs.require(total <= rs.UINT256_MAX, 'combined budget exceeds uint256')
        receipts.append({'id': label, 'receipt': receipt})
        for row in entry['report']['allocations']:
            identifier, recipient = row['id'], row.get('address')
            if identifier in people:
                rs.require(people[identifier]['address'] == recipient,
                           'recipient or address presence changed for contributor: ' + identifier)
            else:
                rs.require(len(people) < rs.MAX_CONTRIBUTORS,
                           'combined roster exceeds 1000 contributors')
                rs.require(recipient is None or recipient not in recipients,
                           'one recipient address appears under different contributor ids')
                if recipient is not None:
                    recipients[recipient] = identifier
                people[identifier] = {'address': recipient, 'units': 0, 'rounds': []}
            people[identifier]['units'] += int(row['units'])
            people[identifier]['rounds'].append(label)
    allocations = []
    for identifier, person in sorted(people.items()):
        row = {'id': identifier, 'units': str(person['units']),
               'amount': rs.display_units(person['units'], metadata['decimals']),
               'rounds': sorted(person['rounds'])}
        if person['address'] is not None:
            row['address'] = person['address']
        allocations.append(row)
    assert sum(int(row['units']) for row in allocations) == total
    repeated = [{'report_sha256': digest, 'rounds': sorted(labels)}
                for digest, labels in sorted(hashes.items()) if len(labels) > 1]
    result = {
        'schema': 'rewardmerge-v1',
        'token': receipts[0]['receipt']['token'],
        'manifest_sha256': rr.digest(manifest),
        'metadata_sha256': rr.digest(metadata),
        'round_count': len(rounds),
        'budget_units': str(total),
        'budget_amount': rs.display_units(total, metadata['decimals']),
        'unallocated_units': '0',
        'all_recipients_supplied': all('address' in row for row in allocations),
        'allocations': allocations,
        'round_receipts': sorted(receipts, key=lambda item: item['id']),
        'repeated_reports': repeated,
        'review_required': bool(repeated),
        'scope': 'sum of verified independent allocations; repeated reports counted once per round label; no entitlement, identity, balance or payment verified',
    }
    rs.require(len((json.dumps(result, indent=2, ensure_ascii=True) + '\n').encode()) <= rs.MAX_BYTES,
               'merged report exceeds 256-KiB limit; use fewer rounds or contributors')
    return result


def verify(manifest, metadata, report):
    expected = merge(manifest, metadata)
    rs.require(rr.canonical_bytes(report) == rr.canonical_bytes(expected),
               'merged report differs from complete recomputation')
    return {'schema': 'rewardmerge-verification-v1', 'result': 'verified cumulative allocation arithmetic',
            'report_sha256': rr.digest(report), 'budget_units': expected['budget_units'],
            'review_required': expected['review_required'], 'scope': expected['scope']}


def demo():
    metadata = rs.read_json(rr.ROOT / 'zto-mainnet.json')
    first = rs.read_json(rr.ROOT / 'example.json')
    second = {'budget': '2', 'contributors': [{'id': 'review', 'weight': '2'},
                                             {'id': 'build', 'weight': '1'}]}
    manifest = {'rounds': [{'id': label, 'request': request, 'report': rs.allocate(request, metadata)}
                           for label, request in [('first', first), ('second', second)]]}
    report = merge(manifest, metadata)
    return {'merged': report, 'verification': verify(manifest, metadata, report)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('demo')
    for name in ('merge', 'verify'):
        cmd = sub.add_parser(name)
        cmd.add_argument('--manifest', required=True)
        cmd.add_argument('--metadata', default=str(rr.ROOT / 'zto-mainnet.json'))
        cmd.add_argument('--output', help='new workspace JSON file; refuses overwrite')
        if name == 'verify':
            cmd.add_argument('--report', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'demo':
            result = demo()
            warning = result['merged']['review_required']
        else:
            manifest = rs.read_json(args.manifest)
            metadata = rs.read_json(args.metadata)
            if args.command == 'merge':
                result = merge(manifest, metadata)
            else:
                result = verify(manifest, metadata, rs.read_json(args.report))
            warning = result['review_required']
        rs.write_json(result, getattr(args, 'output', None))
        return 1 if warning else 0
    except (rs.Invalid, OSError, ValueError, OverflowError, RecursionError) as exc:
        print('rewardmerge: ' + (str(exc) if isinstance(exc, rs.Invalid) else type(exc).__name__), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
