# Slackmap

Find the estimates that control a job's finish and the individual time reserves
around the others. This extends the line's offline work planning with exact
critical-path analysis and per-task earliest/latest start windows. Python 3.9+,
standard library only. No task label is executed, no clock wait is involved,
and no network, environment, wallet, key or payment is used.

Run from the repository root:

```sh
python3 -B line-1/tools/slackmap/slackmap.py --demo --budget 10
```

Observed in round 26: the example's minimum dependency finish is **9 minutes**;
`read → build → check` is one longest path. With a 10-minute deadline, `build`
has 1 minute of total float and `fixtures` has 3 minutes. Fixtures has 2 minutes
of free float: it can finish 2 minutes later without moving check's earliest
start. These are caller estimates, not measured work. A deadline of 8 returns
exit **2**, negative deadline slack and negative float on the longest path.

For your own graph, use the same JSON shape as Workplan and Plancheck:

```sh
python3 -B line-1/tools/slackmap/slackmap.py --tasks line-1/tools/plancheck/tasks.json --budget 10
```

The top level contains only `tasks`, a list of 1–500 tasks, each with `id`,
positive numeric `minutes`, and optional distinct prerequisite ids in `after`.
Duplicate ids/JSON keys, unknown fields/dependencies, cycles and invalid numbers
are rejected. Each input must be an ordinary workspace-local file, at most
100,000 bytes; numeric limits are 100 decimal digits and exponent magnitude 100.
This uses the unchanged `../plancheck/plancheck.py` validator/reader: keep that
folder alongside Slackmap. No dependency installation is needed.

## Include worker ordering

A dependency graph alone assumes unlimited workers. To account for contention
in a **complete valid schedule**, supply the schedule and authoritative worker
count:

```sh
python3 -B line-1/tools/slackmap/slackmap.py --tasks line-1/tools/plancheck/tasks.json --plan line-1/tools/plancheck/plan.json --workers 2 --budget 10
```

Slackmap first checks task coverage, exact durations, dependency timing and
worker nonoverlap with Plancheck, ignoring producer feasibility/optimality claims.
It then adds an edge from each task to the next task on the same worker.
The resulting minimum finish is achievable for **that fixed assignment and
order**; its earliest task times appear in the report. Original idle gaps may
be removed, and the result can finish earlier than the supplied schedule.
There are no release dates, appointments or calendars in this model. This is
not a search over better worker assignments/orders, and a missed deadline in
this mode does not prove all other assignments miss it. Partial Replan
segments and completed/running history are deliberately unsupported.

## Read the report

- All minute values are exact decimal **strings**, avoiding binary-float drift.
- `minimum_finish_in_model` is the longest path in the analyzed graph.
  In dependency-only mode it is a lower bound, not a finite-worker schedule.
- `target_finish` is the external budget, or the minimum finish if omitted.
  `deadline_feasible_in_model` is limited to the mode described above.
- `earliest_start/finish` describe the forward schedule from minute zero.
  `latest_start/finish` describe a backward schedule from the target finish;
  negative latest starts expose an impossible target rather than being clamped.
- `total_float` is latest start minus earliest start. Positive float is a task's
  individual delay allowance against the target. Float allowances are **not
  additive**; spending one task's allowance may consume another's.
- `free_float` is the delay before moving any direct successor's earliest start,
  measured against the model's minimum finish for terminal tasks, not the budget.
- `critical_to_minimum` flags every zero-float task against the minimum finish,
  even when a larger budget gives all tasks positive deadline float.
  `one_longest_path` is one deterministic witness, not every critical branch.
- `worker_order_edges` exposes every added serial constraint, including ones
  already implied by dependencies.

Exit **0** means the target fits the analyzed model, **2** means it does not,
and **1** means invalid data (stderr error, no partial report). Argument syntax
errors use argparse's exit 2. Estimates, uninterrupted worker availability and
finish-to-start dependencies remain assumptions; there is no execution or
real-world deadline guarantee. The CLI writes only stdout/stderr.

## Checks performed

```sh
python3 -B line-1/tools/slackmap/selftest.py
```

Observed: **9 tests passed**, including independent exhaustive path enumeration
on 120 seeded graphs and per-task duration perturbations verifying float at and
one minute beyond its boundary. Tests also cover tied critical branches,
disconnected tasks, exact 0.1+0.2 and widely separated decimal magnitudes,
negative slack, a 500-task chain, input permutation stability and immutability,
invalid inputs, bounded/duplicate-key file refusal, CLI exit codes and fixed
worker ordering with removable idle gaps. Workplan and both Optplan demos are
analyzed, then their derived earliest schedules pass the independent Plancheck.
Disposable fixtures stay in `test/scratch/slackmap/`. These local checks are
observations, not independent certification.
