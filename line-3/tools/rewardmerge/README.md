# RewardMerge

RewardMerge totals exact contributor allocations across independent ZTO reward rounds. It first recomputes every supplied RewardSplit report with RewardReceipt, then sums its integer units. Contributors may join, leave or have different weights between rounds. Rounding remains local to each original round: the tool never pools budgets and reallocates them.

From the repository root, using only Python's standard library and the existing sibling tools:

```sh
python3 -B line-3/tools/rewardmerge/rewardmerge.py demo
```

Tried here: the offline demo returned 0 and verified exactly **3000000000000000000 atomic ZTO units (3 ZTO)** across two illustrative rounds. The first allocates 1 ZTO equally to build, research and review; the second allocates 2 ZTO to build and review with weights 1:2. The cumulative units are build `1000000000000000001`, research `333333333333333333`, review `1666666666666666666`. No recipient addresses are supplied or invented. The inherited real Ethereum ZTO metadata capture is used, rather than a new chain request.

For real inputs, make a workspace JSON manifest with exactly one `rounds` array. Each entry has exactly `id` (your unique round label), `request` (the complete original RewardSplit request object), and `report` (the complete saved RewardSplit allocation object). Embed the objects themselves, rather than filenames. Every report must have used the same token metadata capture.

```sh
python3 -B line-3/tools/rewardmerge/rewardmerge.py merge --manifest ROUNDS.json --output TOTAL.json
python3 -B line-3/tools/rewardmerge/rewardmerge.py verify --manifest ROUNDS.json --report TOTAL.json
```

Both commands accept `--metadata PATH`, defaulting to the included ZTO capture. Output defaults to stdout; `--output PATH` creates a new workspace file and refuses overwrites. Verification compares the entire report to a fresh recomputation, including per-round receipts, contributor membership, input hashes and warnings. JSON object key order and whitespace do not affect hashes; array order and value types do. Reordering rounds retains totals and sorted receipt lists but changes the manifest hash.

A contributor ID must retain exactly the same normalized address, including address presence, across every appearance. An address cannot appear under two IDs. Address-free manifests are supported. This protects input consistency; it does not establish ownership or identity. Zero-unit rows are retained. Round labels use the same 1–64 ASCII identifier alphabet as contributor IDs.

**Repeated identical allocation reports are counted once for each distinct round label and flagged in `repeated_reports`.** Some recurring rounds legitimately have identical allocations; accidental duplication looks the same. Review these warnings against your own round records. Equivalent work entered under different labels or slightly different requests may evade this warning. There is no payment ledger or automatic double-payment prevention.

Limits: 1–64 rounds, at most 1000 distinct contributors in their union, combined budget at most uint256, 256 KiB per input file and per merged output. A large report is refused with an error rather than truncated. Allocation validation, exact decimal strings, deterministic ties and workspace-only JSON reading are inherited from RewardSplit. Keep the `line-3/tools/` sibling tree together. No network, installed package, wallet or secret is needed.

Exits: **0** verified arithmetic with no identical-report warning; **1** verified arithmetic requiring repeated-report review; **2** invalid input, inconsistent addresses, overflow, limit violation or I/O failure. A verification exit 0 does not establish entitlement, work quality, available balance, authorization or payment. Hashes are unsigned; the token capture is a historical observation.

```sh
python3 -B line-3/tools/rewardmerge/selftest.py
```

All 11 tests passed, including 100 seeded multi-round conservation cases, roster/weight changes, zero shares, uint256 limits, report and metadata tampering, repeated reports, round ordering, address consistency, duplicate JSON keys and file-based CLI exits/overwrite refusal. Address tests use the two real public token contract identifiers only as string-validation fixtures; they are never payment instructions. Nothing signs, sends, pays or posts.
