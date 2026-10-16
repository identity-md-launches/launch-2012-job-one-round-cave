#!/usr/bin/env python3
"""Offline adversarial and independent-oracle checks for Slackmap."""
import copy
from decimal import Decimal
from fractions import Fraction
import itertools
import json
from pathlib import Path
import random
import subprocess
import sys
import unittest

import slackmap as sm

HERE = Path(__file__).resolve().parent
SCRATCH = Path('test/scratch/slackmap')


def rows(result):
    return {r['task']: r for r in result['tasks']}


def oracle(data):
    # Independent exponential path enumeration, not a forward/backward pass.
    tasks = {r['id']: r for r in data['tasks']}
    paths = []
    def visit(path):
        paths.append(path)
        for name, row in tasks.items():
            if path[-1] in row.get('after', []):
                visit(path + [name])
    for name in tasks:
        visit([name])
    weights = [(p, sum(tasks[n]['minutes'] for n in p)) for p in paths]
    longest = max(w for _, w in weights)
    through = {n: max(w for p, w in weights if n in p) for n in tasks}
    return longest, through


class Checks(unittest.TestCase):
    def test_demo_and_deadline(self):
        result = sm.analyze(sm.demo(), 10)
        r = rows(result)
        self.assertEqual(result['minimum_finish_in_model'], '9')
        self.assertEqual(result['one_longest_path'], ['read', 'build', 'check'])
        self.assertEqual(r['fixtures']['total_float'], '3')
        self.assertEqual(r['fixtures']['free_float'], '2')
        self.assertEqual(r['build']['total_float'], '1')
        self.assertFalse(r['fixtures']['critical_to_minimum'])
        missed = sm.analyze(sm.demo(), 8)
        self.assertFalse(missed['deadline_feasible_in_model'])
        self.assertEqual(rows(missed)['build']['total_float'], '-1')

    def test_decimal_and_extremes(self):
        data = {'tasks': [{'id': 'a', 'minutes': Decimal('0.1')},
                          {'id': 'b', 'minutes': Decimal('0.2'), 'after': ['a']}]}
        self.assertEqual(sm.analyze(data)['minimum_finish_in_model'], '0.3')
        data['tasks'][0]['minutes'] = Decimal('1e100')
        data['tasks'][1]['minutes'] = Decimal('1e-100')
        result = sm.analyze(data)
        expected = Fraction(10**100) + Fraction(1, 10**100)
        self.assertEqual(Fraction(result['minimum_finish_in_model']), expected)
        self.assertEqual(sm.decimal(Fraction(0)), '0')

    def test_all_critical_branches(self):
        data = {'tasks': [{'id': 'a', 'minutes': 2}, {'id': 'b', 'minutes': 2},
                          {'id': 'end', 'minutes': 1, 'after': ['a', 'b']},
                          {'id': 'isolated', 'minutes': 1}]}
        r = rows(sm.analyze(data))
        self.assertEqual([n for n in r if r[n]['critical_to_minimum']], ['a', 'b', 'end'])
        self.assertEqual(r['isolated']['free_float'], '2')

    def test_oracle_and_float_sensitivity(self):
        rng = random.Random(73726)
        for _ in range(120):
            n = rng.randint(1, 7)
            data = {'tasks': [{'id': str(i), 'minutes': rng.randint(1, 8),
                              'after': [str(j) for j in range(i) if rng.random() < .3]}
                             for i in range(n)]}
            expected, through = oracle(data)
            result = sm.analyze(data)
            self.assertEqual(int(result['minimum_finish_in_model']), expected)
            for row in result['tasks']:
                slack = expected - through[row['task']]
                self.assertEqual(int(row['total_float']), slack)
                self.assertEqual(row['critical_to_minimum'], slack == 0)
                # Each task's individual float absorbs precisely this much
                # duration growth without extending the model finish.
                changed = copy.deepcopy(data)
                task = next(r for r in changed['tasks'] if r['id'] == row['task'])
                task['minutes'] += slack
                self.assertEqual(int(sm.analyze(changed)['minimum_finish_in_model']), expected)
                task['minutes'] += 1
                self.assertEqual(int(sm.analyze(changed)['minimum_finish_in_model']), expected + 1)

    def test_fixed_worker_order(self):
        data = {'tasks': [{'id': 'a', 'minutes': 3}, {'id': 'b', 'minutes': 2}]}
        plan = {'workers': 1, 'finish': 12, 'schedule': [
            {'task': 'a', 'worker': 1, 'start': 5, 'finish': 8},
            {'task': 'b', 'worker': 1, 'start': 10, 'finish': 12}]}
        original = copy.deepcopy((data, plan))
        self.assertEqual(sm.analyze(data)['minimum_finish_in_model'], '3')
        fixed = sm.analyze(data, 4, plan, 1)
        self.assertEqual(fixed['minimum_finish_in_model'], '5')
        self.assertFalse(fixed['deadline_feasible_in_model'])
        self.assertEqual(fixed['one_longest_path'], ['a', 'b'])
        self.assertEqual((data, plan), original)
        plan['schedule'][1]['start'] = 7
        with self.assertRaisesRegex(ValueError, 'invalid plan'):
            sm.analyze(data, plan=plan, workers=1)

    def test_rejects_invalid_inputs(self):
        for data in [{'tasks': []}, {'tasks': [{'id': 'x', 'minutes': 1, 'after': ['x']}]},
                     {'tasks': [{'id': 'x', 'minutes': True}]},
                     {'tasks': [{'id': 'x', 'minutes': 1, 'after': ['absent']}]},
                     {'tasks': [{'id': 'x', 'minutes': 1}]*2}]:
            with self.assertRaises(ValueError):
                sm.analyze(data)
        for budget in [True, -1, Decimal('NaN'), Decimal('Infinity')]:
            with self.assertRaises(ValueError):
                sm.analyze(sm.demo(), budget)
        with self.assertRaises(ValueError):
            sm.analyze(sm.demo(), workers=2)
        with self.assertRaises(ValueError):
            sm.analyze(sm.demo(), plan={})

    def test_max_chain_and_determinism(self):
        data = {'tasks': [{'id': str(i), 'minutes': 1,
                          'after': [str(i-1)] if i else []} for i in range(500)]}
        self.assertEqual(sm.analyze(data)['minimum_finish_in_model'], '500')
        data = sm.demo()
        original = copy.deepcopy(data)
        expected = sm.analyze(data)
        self.assertEqual(data, original)
        for perm in itertools.permutations(data['tasks']):
            self.assertEqual(sm.analyze({'tasks': list(perm)}), expected)

    def test_integrates_existing_planners(self):
        for name in ['workplan', 'optplan']:
            spec = sm.importlib.util.spec_from_file_location(name, HERE.parent / name / (name + '.py'))
            module = sm.importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            cases = [module.demo()]
            if name == 'optplan':
                cases.append(module.idle_demo())
            for data in cases:
                plan = module.plan(data, 2) if name == 'workplan' else module.exact(data, 2)
                result = sm.analyze(data, plan=plan, workers=2)
                self.assertLessEqual(Fraction(result['minimum_finish_in_model']), Fraction(plan['finish']))
                schedule = [{'task': r['task'], 'worker': next(p['worker'] for p in plan['schedule'] if p['task'] == r['task']),
                             'start': Decimal(r['earliest_start']), 'finish': Decimal(r['earliest_finish'])}
                            for r in result['tasks']]
                self.assertTrue(sm.pc.check(data, {'workers': 2, 'finish': Decimal(result['minimum_finish_in_model']),
                                                  'schedule': schedule}, 2)['valid'])

    def test_cli_and_file_boundaries(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        command = [sys.executable, '-B', str(HERE / 'slackmap.py')]
        for budget, expected in [('10', 0), ('8', 2), ('NaN', 1)]:
            result = subprocess.run(command + ['--demo', '--budget', budget], capture_output=True, text=True)
            self.assertEqual(result.returncode, expected, result.stderr)
            if expected == 1:
                self.assertEqual(result.stdout, '')
            else:
                self.assertEqual(json.loads(result.stdout)['deadline_feasible_in_model'], expected == 0)
        path = SCRATCH / 'tasks.json'
        path.write_text(json.dumps(sm.demo()))
        result = subprocess.run(command + ['--tasks', str(path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        for raw in ['{"tasks": [], "tasks": []}', ' '*100001, '{"n": NaN}']:
            path.write_text(raw)
            result = subprocess.run(command + ['--tasks', str(path)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, '')
        with self.assertRaises(ValueError):
            sm.pc.read_json(Path.cwd().parent / 'outside-slackmap.json')


if __name__ == '__main__':
    unittest.main(verbosity=2)
