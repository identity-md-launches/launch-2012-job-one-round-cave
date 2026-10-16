# ZipDiff

Review what would change before extracting a replacement ZIP. ZipDiff checks two
approved archives and compares their complete extracted paths and file bytes,
without creating an extraction or running any archive content. It reports added,
removed, changed-content and changed-type paths, plus byte and node totals.
Python 3.9+ standard library only; it imports the shipped sibling
`../safezip/safezip.py`. No installation, network, secrets or environment access.

From the repository root, run this one command:

```sh
python3 -B line-2/tools/zipdiff/demo.py
```

Tried here: the demo repackaged the bundled real public IMD OpenAPI capture
(23,132 bytes) from stored to deflated compression. The ZIP hashes differed, but
all three extracted nodes matched. A deliberate one-byte change in another
copy then produced exactly one `content_changed` finding, despite identical
file size. The source capture is unchanged. This is an offline replay of
historical public data, not a fresh API observation or an actual upstream change.
The source and provenance are shipped in `../safezip/imd-openapi.json` and
`../safezip/sample-source.json`. The demo creates disposable ZIPs only in
`test/scratch/` and cleans them up. It approves only the demo ZIPs it just made.

## Compare your own archives

First use SafeZip's inspect command on each archive, review its inventory, and
retain each reported `archive_sha256`. Then supply those actual digests:

```sh
python3 -B line-2/tools/zipdiff/zipdiff.py old.zip candidate.zip --before-sha256 OLD_APPROVED_DIGEST --after-sha256 NEW_APPROVED_DIGEST --nodes 500 --seconds 10
```

The uppercase words are command documentation, not supplied digest values.
Both digests are mandatory and must be 64 hexadecimal characters. The CLI does
not derive and silently approve them. Python callers use
`compare(before, after, before_sha256=old_digest, after_sha256=new_digest, ...)`.

Exit **0** means equal extracted trees; **1** means valid archives with changes;
**2** means refused input, corruption, exhausted budget or I/O error. Successful
comparisons have `ok: true`, even when trees differ. Errors have `ok: false` and
an error string. Malformed CLI syntax uses argparse's stderr/exit 2. Python API
policy failures raise `Rejected`; underlying I/O/ZIP errors can propagate.

Paths are compared with exact spellings, in sorted order. A case-only rename is
a removal and an addition. Every implicit parent and explicit empty directory
counts; spelling a parent explicitly does not change the extracted tree. A file
replaced by a directory is `type_changed`, with its added children listed too.
Each change contains before/after kind and, for files, size and SHA-256; a missing
side is null. `unchanged_nodes` includes directories. `archive_bytes_equal`
compares whole-ZIP hashes; `trees_equal` compares the paths and file hashes.
Neither field compares ZIP metadata. No rename inference or semantic text diff.

SafeZip rechecks **both complete payloads**, even for identical archive hashes,
including CRCs, safe paths, compression restrictions and collisions. It captures
bounded ZIP bytes so the approval and content checks use the same snapshot.
All SafeZip budgets are forwarded: `--entries` (1000), `--nodes` (32000),
`--archive-bytes` (33554432), `--file-bytes` (16777216), `--total-bytes`
(67108864), `--ratio` (200). Each limit applies independently to **each archive**.
The comparison can list at most twice the node limit. It retains both bounded
inventories, not both decompressed trees. Optional `--seconds` is one cooperative
monotonic deadline across both inspections and comparison, not two full budgets.

## Checks and boundaries

```sh
python3 -B line-2/tools/zipdiff/selftest.py
```

Observed: **16 tests passed**, covering repacking, empty trees/directories,
implicit parents, content and type changes, case renames, deterministic output,
mandatory approvals, corruption despite approval, unsafe paths and symlinks,
budgets on both inputs, a shared deadline without sleeping, no writes and the
three CLI outcomes. All 44 SafeZip and 16 ZipAudit tests also passed.

Both paths must be within the current workspace, with no symlink components.
The tool is for a cooperative workspace, not hostile concurrent filesystem
mutation. Metadata, permissions, timestamps, archive comments and compression
layout are ignored when comparing trees; extraction does not restore them.
Hash equality assumes SHA-256 collision resistance. An equal tree is not an
execution approval, proof of authorship or guarantee of harmless content.
Requiring an approved digest does not decide whether a new release is acceptable.

The ZIP parser runs before entry/node limits and uses additional memory; byte
bounds are not hard RAM limits. The deadline is cooperative and cannot interrupt
one blocking I/O, ZIP parsing, sorting, decompression or hashing call. Report
serialization is outside the deadline. Default limits bound output but can still
produce a large report; choose a smaller node limit for interactive review.
No archive is recursively opened, extracted, sent or executed; no coin is needed.
