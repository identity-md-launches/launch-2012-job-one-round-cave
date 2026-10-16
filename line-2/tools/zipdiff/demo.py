#!/usr/bin/env python3
"""Offline comparison of repackaged and deliberately changed real public data."""
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile
from zipdiff import compare
from safezip import local_path


def main():
    source = local_path(Path(__file__).resolve().parents[1] / 'safezip/imd-openapi.json')
    with source.open('rb') as reader:
        payload = reader.read(65537)
    if hashlib.sha256(payload).hexdigest() != 'be142840c010710cb2a5b9e5c73e71d8e79ec4054c15661699d60bfa627be96a':
        raise ValueError('bundled public capture differs')
    scratch = local_path('test/scratch')
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch, prefix='zipdiff-demo-') as temporary:
        root = Path(temporary)
        def pack(name, compression, data):
            path = root / name
            with zipfile.ZipFile(path, 'w', compression=compression) as archive:
                archive.writestr('docs/imd/openapi.json', data)
            return path, hashlib.sha256(path.read_bytes()).hexdigest()
        original, old_hash = pack('original.zip', zipfile.ZIP_STORED, payload)
        repacked, repacked_hash = pack('repacked.zip', zipfile.ZIP_DEFLATED, payload)
        # Hypothetical edit to a disposable copy; the public capture stays intact.
        changed_payload = bytearray(payload)
        changed_payload[len(payload) // 2] ^= 1
        revised, new_hash = pack('revised.zip', zipfile.ZIP_DEFLATED, changed_payload)
        same = compare(original, repacked, before_sha256=old_hash,
                       after_sha256=repacked_hash, nodes=3, seconds=10)
        changed = compare(original, revised, before_sha256=old_hash,
                          after_sha256=new_hash, nodes=3, seconds=10)
        assert same['trees_equal'] and not same['archive_bytes_equal']
        assert changed['counts']['content_changed'] == 1 and changed['byte_delta'] == 0
        print(json.dumps({'ok': True, 'network_used': False,
                          'source': 'https://api.imd.fun/openapi.json',
                          'source_bytes': len(payload),
                          'repacked': same, 'hypothetical_same_size_edit': changed}, indent=2))


if __name__ == '__main__':
    main()
