#!/usr/bin/env python3
"""Compare the bounded extracted trees of two approved ZIPs without extracting."""
import argparse
import json
import math
from pathlib import Path
import re
import sys
import time
import zipfile
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'safezip'))
from safezip import Rejected, process


def compare(before, after, *, before_sha256, after_sha256, seconds=None,
            entries=1000, nodes=32000, archive_bytes=33554432,
            file_bytes=16777216, total_bytes=67108864, ratio=200):
    """Check both payloads and return deterministic path/content changes.

    Limits apply independently to each ZIP; seconds covers the whole comparison.
    Digests must be caller-approved; no archive data is executed or extracted.
    """
    for digest in (before_sha256, after_sha256):
        if not isinstance(digest, str) or re.fullmatch(r'[0-9a-fA-F]{64}', digest) is None:
            raise Rejected('two approved SHA-256 digests are required')
    if seconds is not None:
        try:
            valid = (not isinstance(seconds, bool) and isinstance(seconds, (int, float))
                     and math.isfinite(seconds) and seconds > 0)
        except OverflowError:
            valid = False
        if not valid:
            raise Rejected('seconds must be a finite positive number')
    started = time.monotonic()

    def checkpoint():
        if seconds is not None and time.monotonic() - started >= seconds:
            raise Rejected('comparison time budget exceeded')
        return False

    limits = dict(entries=entries, nodes=nodes, archive_bytes=archive_bytes,
                  file_bytes=file_bytes, total_bytes=total_bytes, ratio=ratio)
    # SafeZip checkpoints invoke this same deadline during both snapshots,
    # inventories and decompressions, so the second archive gets no new budget.
    first = process(before, expected_sha256=before_sha256, cancelled=checkpoint, **limits)
    second = process(after, expected_sha256=after_sha256, cancelled=checkpoint, **limits)

    def tree(report):
        result = {}
        for entry in report['entries']:
            checkpoint()
            parts = entry['path'].split('/')
            for length in range(1, len(parts)):
                result.setdefault('/'.join(parts[:length]), {'kind': 'directory'})
            result[entry['path']] = ({'kind': 'directory'} if entry['kind'] == 'directory'
                                     else {k: entry[k] for k in ('kind', 'bytes', 'sha256')})
        return result

    old, new = tree(first), tree(second)
    changes = []
    unchanged = 0
    counts = {kind: 0 for kind in ('added', 'removed', 'type_changed', 'content_changed')}
    checkpoint()
    for path in sorted(old.keys() | new.keys()):
        checkpoint()
        left, right = old.get(path), new.get(path)
        if left == right:
            unchanged += 1
            continue
        kind = ('added' if left is None else 'removed' if right is None else
                'type_changed' if left['kind'] != right['kind'] else 'content_changed')
        counts[kind] += 1
        changes.append({'path': path, 'change': kind, 'before': left, 'after': right})
    checkpoint()
    return {'ok': True, 'mode': 'compare', 'content_checked': True,
            'before_sha256': first['archive_sha256'], 'after_sha256': second['archive_sha256'],
            'archive_bytes_equal': first['archive_sha256'] == second['archive_sha256'],
            'trees_equal': not changes, 'before_nodes': len(old), 'after_nodes': len(new),
            'before_bytes': first['total_bytes'], 'after_bytes': second['total_bytes'],
            'byte_delta': second['total_bytes'] - first['total_bytes'],
            'unchanged_nodes': unchanged, 'counts': counts, 'changes': changes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before')
    parser.add_argument('after')
    parser.add_argument('--before-sha256', required=True)
    parser.add_argument('--after-sha256', required=True)
    parser.add_argument('--seconds', type=float)
    for name, default in [('entries', 1000), ('nodes', 32000),
                          ('archive-bytes', 33554432), ('file-bytes', 16777216),
                          ('total-bytes', 67108864), ('ratio', 200)]:
        parser.add_argument('--' + name, type=int, default=default)
    try:
        result = compare(**vars(parser.parse_args()))
    except (ValueError, OSError, zipfile.BadZipFile, NotImplementedError,
            RuntimeError, EOFError, zlib.error) as error:
        print(json.dumps({'ok': False, 'error': str(error)}, ensure_ascii=True))
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0 if result['trees_equal'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
