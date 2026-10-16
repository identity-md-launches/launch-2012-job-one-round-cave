#!/usr/bin/env python3
"""Explain deadline slack offline; never execute task labels."""
import argparse
from decimal import Decimal, localcontext
from fractions import Fraction
import heapq
import importlib.util
import json
from pathlib import Path
import sys

# Reuse the inspected predecessor's exact input boundary and schedule checker.
_spec = importlib.util.spec_from_file_location(
    'slackmap_plancheck', Path(__file__).resolve().parents[1] / 'plancheck/plancheck.py')
pc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pc)


def decimal(value):
    """All model arithmetic is sums/differences of bounded finite decimals."""
    with localcontext() as ctx:
        ctx.prec = 512
        text = format(Decimal(value.numerator) / Decimal(value.denominator), 'f')
    return text.rstrip('0').rstrip('.') if '.' in text else text


def analyze(data, budget=None, plan=None, workers=None):
    tasks = pc.graph(data)
    deadline = None if budget is None else pc.number(budget, 'budget')
    if deadline is not None and deadline < 0:
        raise ValueError('budget must be nonnegative')
    deps = {name: set(row[1]) for name, row in tasks.items()}
    worker_edges = []
    if plan is None:
        if workers is not None:
            raise ValueError('workers requires a complete plan')
    else:
        if workers is None:
            raise ValueError('a complete plan requires external workers')
        checked = pc.check(data, plan, workers)
        if not checked['valid']:
            raise ValueError('invalid plan: ' + ', '.join(checked['violations']))
        groups = {}
        for row in plan['schedule']:
            groups.setdefault(row['worker'], []).append(
                (pc.number(row['start'], 'start'), row['task']))
        for worker in sorted(groups):
            order = sorted(groups[worker])
            for (_, before), (_, after) in zip(order, order[1:]):
                deps[after].add(before)
                worker_edges.append({'before': before, 'after': after, 'worker': worker})
    children = {name: set() for name in tasks}
    for name, parents in deps.items():
        for parent in parents:
            children[parent].add(name)
    degree = {name: len(parents) for name, parents in deps.items()}
    ready = [name for name, count in degree.items() if not count]
    heapq.heapify(ready)
    order, start, finish, predecessor = [], {}, {}, {}
    while ready:
        name = heapq.heappop(ready)
        order.append(name)
        parents = sorted(deps[name])
        parent = min(parents, key=lambda p: (-finish[p], p)) if parents else None
        predecessor[name] = parent
        start[name] = finish[parent] if parent is not None else Fraction(0)
        finish[name] = start[name] + tasks[name][0]
        for child in sorted(children[name]):
            degree[child] -= 1
            if degree[child] == 0:
                heapq.heappush(ready, child)
    if len(order) != len(tasks):
        raise ValueError('combined dependency/worker-order cycle')
    minimum = max(finish.values())
    target = minimum if deadline is None else deadline
    latest, natural_latest = {}, {}
    for name in reversed(order):
        latest[name] = min((latest[c] for c in children[name]), default=target) - tasks[name][0]
        natural_latest[name] = min((natural_latest[c] for c in children[name]), default=minimum) - tasks[name][0]
    end = min(tasks, key=lambda n: (-finish[n], n))
    witness = []
    while end is not None:
        witness.append(end)
        end = predecessor[end]
    rows = []
    for name in sorted(tasks):
        free = min((start[c] for c in children[name]), default=minimum) - finish[name]
        rows.append({'task': name, 'minutes': decimal(tasks[name][0]),
                     'earliest_start': decimal(start[name]), 'earliest_finish': decimal(finish[name]),
                     'latest_start': decimal(latest[name]),
                     'latest_finish': decimal(latest[name] + tasks[name][0]),
                     'total_float': decimal(latest[name] - start[name]),
                     'free_float': decimal(free),
                     'critical_to_minimum': natural_latest[name] == start[name]})
    return {'units': 'minutes', 'mode': 'fixed_worker_order' if plan is not None else 'dependencies_only',
            'minimum_finish_in_model': decimal(minimum), 'target_finish': decimal(target),
            'deadline_supplied': deadline is not None, 'deadline_feasible_in_model': minimum <= target,
            'deadline_slack': decimal(target - minimum), 'one_longest_path': list(reversed(witness)),
            'worker_order_edges': worker_edges, 'tasks': rows,
            'scope': ('Fixed assignment/order; input idle gaps may be removed. No order optimization.'
                      if plan is not None else
                      'Unlimited workers: dependency lower bound only, not finite-worker feasibility.'),
            'warning': 'Float is individual, not additive or permission to delay every task. Estimates are assumptions.'}


def demo():
    return {'tasks': [{'id': 'read', 'minutes': 2},
                      {'id': 'build', 'minutes': 5, 'after': ['read']},
                      {'id': 'fixtures', 'minutes': 3, 'after': ['read']},
                      {'id': 'check', 'minutes': 2, 'after': ['build', 'fixtures']}]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo', action='store_true')
    parser.add_argument('--tasks')
    parser.add_argument('--budget', type=Decimal)
    parser.add_argument('--plan')
    parser.add_argument('--workers', type=int)
    args = parser.parse_args()
    try:
        if args.demo == (args.tasks is not None):
            raise ValueError('choose exactly one of --demo or --tasks')
        data = demo() if args.demo else pc.read_json(args.tasks)
        plan = pc.read_json(args.plan) if args.plan is not None else None
        result = analyze(data, args.budget, plan, args.workers)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0 if result['deadline_feasible_in_model'] else 2
    except (ValueError, OSError, OverflowError, RecursionError) as exc:
        print('slackmap: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
