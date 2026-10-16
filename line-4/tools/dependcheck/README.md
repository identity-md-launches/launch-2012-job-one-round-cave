# DependCheck

Identify potential OpenAPI 3.1 breaks when one property starts requiring another.
Python 3.9+; standard library only; offline, with no installation required.
Run from the repository root:

```sh
python3 -B line-4/tools/dependcheck/dependcheck.py demo
```

The demo uses the bundled real public IMD OpenAPI capture. It adds two illustrative
optional request properties in memory, then proposes `clientReference` requiring
`clientContext`. It reports **one potential break and one retained review** over
five operations, with exit 0. This is a hypothetical change, not an observed change
to the service. No described API operation is called.

Compare two actual local descriptions:

```sh
python3 -B line-4/tools/dependcheck/dependcheck.py compare line-4/tools/apidelta/imd-openapi.json line-4/tools/apidelta/imd-openapi.json
```

Replace the two paths with your old and proposed descriptions. Identical captures
give zero findings and exit 0. Paths must resolve inside the current working
directory. File comparison includes SHA-256 hashes of both inputs.

| Exit | Meaning |
| --- | --- |
| 0 | No detected breakage, or successful demo |
| 1 | Potential breaking change |
| 2 | Invalid/unsupported input, resource limit, or file error |
| 3 | Unresolved review findings without a breaking finding |

## Presence rules

For `dependentRequired: {"a": ["b"]}`, presence of `a` requires presence of `b`.
It does not require `a` unconditionally, or require `a` when only `b` is supplied.
The [JSON Schema reference](https://json-schema.org/understanding-json-schema/reference/conditionals#dependentRequired)
describes this keyword.

DependCheck compares these implications in the correct direction: old requests
must remain acceptable to the new API, and new responses must satisfy old clients'
presence rules. It computes transitive closure, including unconditional `required`
properties. Adding `a → c` when `a → b → c` already holds does not create a new
dependency finding. Self-dependencies, empty lists and cycles terminate normally.
One finding per trigger lists the additional obligations, with escaped pointer
locations. Nested schemas and local references use the inherited traversal.

The rule runs when both descriptions are OpenAPI 3.1.x; 3.0 and cross-version
keyword changes retain generic reviews. If both schemas explicitly exclude objects,
it does not emit dependency breaks. Changed dependencies still retain the inherited
generic review, including equivalent or relaxed rules. Every earlier ApiDelta,
BoundCheck, MultipleCheck, ConstCheck and UniqueCheck rule remains active.

## Scope and limits

This is conservative subset analysis, not a complete schema validator or runtime
compatibility proof. A flagged presence pattern may be impossible because of
`additionalProperties`, `maxProperties`, `const`, enums, property schemas or
composition. Those interactions, `dependentSchemas`, legacy `dependencies`,
conditional schemas, custom dialect semantics and read/write annotations need
human review. No interpretation is performed on unused components, and identical
schemas can bypass semantic validation. Existing tools may conservatively flag a
redundant unconditional `required` change even when dependency closure implies it.

For visited dependency graphs: maximum 256 distinct names (including `required`)
and 1,024 directed edges per schema; excess returns exit 2. Values must be arrays
of unique strings. The existing loader's 1 MiB / 50,000 node / 80 depth limits,
20,000 schema visits, 2,000 findings, duplicate-key rejection and local-reference
restrictions also apply. No environment, configuration, account or secret is read.
The tool imports its five sibling tools from this repository; keep those folders
with it. There is no network code in its runtime.

## What happened when tried

- All **11 new tests passed**, including 6,144 finite presence-model comparisons,
  request/response direction, transitive and cyclic rules, required seeds,
  references, nesting, escaped names, malformed constraints, graph limits,
  inherited findings and CLI exits.
- All **92 inherited tests passed** across the five earlier tools.
- A read-only GET of the public IMD description with User-Agent
  `Pepeolithic-DependCheck/26.0` matched the saved capture: five compared
  operations, zero findings. The dated response hash and byte count are in
  `../../live-check-26.json`; this observation is not a live compatibility promise.

Run the regression suite:

```sh
python3 -B line-4/tools/dependcheck/selftest.py
```

No API quote, payment, token balance, signature or transaction is needed.
