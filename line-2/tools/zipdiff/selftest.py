#!/usr/bin/env python3
"""Offline adversarial comparisons, confined to disposable workspace paths."""
import hashlib
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile
from zipdiff import compare, Rejected


class DiffTests(unittest.TestCase):
    def setUp(self):
        Path('test/scratch').mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir='test/scratch', prefix='zipdiff-test-')
        self.root = Path(self.tmp.name)
        self.a = self.root / 'a.zip'
        self.b = self.root / 'b.zip'

    def tearDown(self):
        self.tmp.cleanup()

    def pack(self, path, members, compression=zipfile.ZIP_STORED):
        with zipfile.ZipFile(path, 'w', compression=compression) as archive:
            for name, data in members:
                archive.writestr(name, data)
        return self.digest(path)

    def digest(self, path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def check(self, **options):
        return compare(self.a, self.b, before_sha256=self.digest(self.a),
                       after_sha256=self.digest(self.b), **options)

    def pair(self, old, new):
        self.pack(self.a, old)
        self.pack(self.b, new)

    def test_identical_empty_archives(self):
        self.pair([], [])
        result = self.check()
        self.assertTrue(result['trees_equal'])
        self.assertTrue(result['archive_bytes_equal'])
        self.assertEqual(result['before_nodes'], 0)

    def test_repack_and_explicit_parents_are_same_tree(self):
        self.pack(self.a, [('a/b', b'hello'), ('zero', b'')])
        self.pack(self.b, [('zero', b''), ('a/', b''), ('a/b', b'hello')], zipfile.ZIP_DEFLATED)
        result = self.check()
        self.assertTrue(result['trees_equal'])
        self.assertFalse(result['archive_bytes_equal'])
        self.assertEqual(result['unchanged_nodes'], 3)

    def test_same_size_content_change(self):
        self.pair([('x', b'old')], [('x', b'new')])
        result = self.check()
        self.assertEqual(result['byte_delta'], 0)
        self.assertEqual(result['counts']['content_changed'], 1)
        self.assertNotEqual(result['changes'][0]['before']['sha256'],
                            result['changes'][0]['after']['sha256'])

    def test_added_removed_and_empty_directories(self):
        self.pair([('gone/', b''), ('keep', b'')], [('new/deep/file', b'abc'), ('keep', b'')])
        result = self.check()
        self.assertEqual(result['counts'], dict(added=3, removed=1, type_changed=0, content_changed=0))
        self.assertEqual(result['byte_delta'], 3)
        self.assertEqual(result['unchanged_nodes'], 1)
        self.assertEqual([x['path'] for x in result['changes']], ['gone', 'new', 'new/deep', 'new/deep/file'])

    def test_type_swap_both_directions(self):
        for old, new in [([('x', b'abc')], [('x/y', b'')]),
                         ([('x/y', b'')], [('x', b'abc')])]:
            self.pair(old, new)
            result = self.check()
            self.assertEqual(result['counts']['type_changed'], 1)
            self.assertEqual(result['changes'][0]['path'], 'x')

    def test_case_rename_is_removal_plus_addition(self):
        self.pair([('Name', b'x')], [('name', b'x')])
        result = self.check()
        self.assertEqual(result['counts']['added'], 1)
        self.assertEqual(result['counts']['removed'], 1)

    def test_missing_or_invalid_approval_before_read(self):
        for value in (None, '', 'x'*64, True, 1):
            with mock.patch('zipdiff.process') as process:
                with self.assertRaises(Rejected):
                    compare(self.a, self.b, before_sha256='a'*64, after_sha256=value)
                process.assert_not_called()

    def test_digest_mismatch_either_side_and_uppercase(self):
        self.pair([('a', b'a')], [('b', b'b')])
        a, b = self.digest(self.a), self.digest(self.b)
        for old, new in [(b, b), (a, a)]:
            with self.assertRaisesRegex(Rejected, 'approved digest'):
                compare(self.a, self.b, before_sha256=old, after_sha256=new)
        self.assertTrue(compare(self.a, self.b, before_sha256=a.upper(), after_sha256=b.upper())['ok'])

    def test_corruption_even_with_matching_approval(self):
        self.pair([('x', b'payload')], [('x', b'payload')])
        raw = bytearray(self.b.read_bytes())
        raw[raw.index(b'payload')] ^= 1
        self.b.write_bytes(raw)
        with self.assertRaises(zipfile.BadZipFile):
            self.check()

    def test_unsafe_archive_either_side(self):
        info = zipfile.ZipInfo('link')
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        for members in [[('../outside', b'x')], [(info, b'target')], [('A', b''), ('a', b'')]]:
            for bad in (self.a, self.b):
                self.pair([('ok', b'')], [('ok', b'')])
                self.pack(bad, members)
                with self.assertRaises(Rejected):
                    self.check()

    def test_each_archive_limits(self):
        for big in (self.a, self.b):
            self.pair([], [])
            self.pack(big, [('a/b/c', b'1234'), ('zero', b'')])
            for options in ({'nodes': 3}, {'entries': 1}, {'file_bytes': 3},
                            {'total_bytes': 3}, {'archive_bytes': 1}, {'nodes': True}):
                with self.subTest(big=big, options=options), self.assertRaises(Rejected):
                    self.check(**options)
        self.check(nodes=4, entries=2, file_bytes=4, total_bytes=4)

    def test_symlink_and_outside_paths(self):
        self.pair([], [])
        digest = self.digest(self.a)
        link = self.root / 'alias'
        link.symlink_to('a.zip')
        for path in (link, '../never-read.zip'):
            with self.assertRaises(Rejected):
                compare(path, self.b, before_sha256=digest, after_sha256=digest)

    def test_one_deadline_covers_both_archives(self):
        self.pair([], [])
        import zipdiff
        original = zipdiff.process
        now = [0]
        def inspect(*args, **kwargs):
            result = original(*args, **kwargs)
            now[0] += 6
            return result
        with mock.patch('zipdiff.time.monotonic', side_effect=lambda: now[0]), \
                mock.patch('zipdiff.process', side_effect=inspect):
            with self.assertRaisesRegex(Rejected, 'comparison time budget'):
                self.check(seconds=10)

    def test_invalid_time_before_read(self):
        for seconds in (True, 0, -1, float('inf'), float('nan'), '1', 10**1000):
            with mock.patch('zipdiff.process') as process:
                with self.assertRaises(Rejected):
                    compare(self.a, self.b, before_sha256='a'*64, after_sha256='b'*64, seconds=seconds)
                process.assert_not_called()

    def test_no_writes_and_negative_delta(self):
        self.pair([('x', b'long')], [('x', b'a')])
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        self.assertEqual(self.check()['byte_delta'], -3)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})

    def test_cli_equal_changed_rejected(self):
        script = str(Path(__file__).with_name('zipdiff.py'))
        for new, code in [([('x', b'old')], 0), ([('x', b'new')], 1), ([('../bad', b'')], 2)]:
            self.pair([('x', b'old')], new)
            result = subprocess.run([sys.executable, '-B', script, str(self.a), str(self.b),
                                     '--before-sha256', self.digest(self.a),
                                     '--after-sha256', self.digest(self.b)], capture_output=True, text=True)
            self.assertEqual(result.returncode, code, result.stderr)
            self.assertEqual(json.loads(result.stdout)['ok'], code != 2)
            self.assertNotIn('Traceback', result.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
