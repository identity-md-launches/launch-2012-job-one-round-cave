"""Independent presence-set oracle, reference, bounds and command-line checks."""
import copy
import itertools
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import dependcheck as d


def document(schema, response=False, version='3.1.0'):
    media = {'application/json': {'schema': schema}}
    operation = {'responses': {'200': {'description': 'ok', 'content': media if response else {}}}}
    if not response:
        operation['requestBody'] = {'content': media}
    return {'openapi': version, 'paths': {'/items': {'post': operation}}}


def findings(old, new, response=False, version='3.1.0'):
    return [f for f in d.compare(document(old, response, version),
                                 document(new, response, version))['findings']
            if f['code'] == 'dependent_required_incompatible']


class Tests(unittest.TestCase):
    def test_finite_acceptance_oracle(self):
        # Independent evaluation of every object-presence set over three names.
        # All 64 directed graphs, paired with all eight choices of required set.
        # Compare each model with empty, chained, cyclic and unconditional models.
        names = ('a', 'b', 'c')
        edges = list(itertools.permutations(names, 2))
        sets = [set(n for n, flag in zip(names, flags) if flag)
                for flags in itertools.product((False, True), repeat=3)]
        def accepted(schema):
            return {tuple(sorted(p)) for p in sets
                    if set(schema.get('required', [])) <= p and
                    all(a not in p or set(bs) <= p
                        for a, bs in schema.get('dependentRequired', {}).items())}
        targets = [dict(type='object', dependentRequired=graph, required=required)
                   for graph in ({}, {'a': ['b'], 'b': ['c']},
                                 {'a': ['b'], 'b': ['a']})
                   for required in ([], ['c'])]
        for flags in itertools.product((False, True), repeat=6):
            graph = {}
            for (a, b), flag in zip(edges, flags):
                if flag:
                    graph.setdefault(a, []).append(b)
            for required in sets:
                old = dict(type='object', dependentRequired=graph, required=sorted(required))
                for new in targets:
                    for response in (False, True):
                        # Existing required findings account for unconditional
                        # changes. Check the combined presence-rule analyzer.
                        report = d.compare(document(old, response), document(new, response))
                        codes = {'dependent_required_incompatible', 'request_property_required',
                                 'response_property_not_guaranteed'}
                        detected = any(f['code'] in codes for f in report['findings'])
                        before, after = accepted(old), accepted(new)
                        expected = bool(after - before if response else before - after)
                        # Base required checks may conservatively flag redundant
                        # unconditional changes. Never miss an oracle break.
                        self.assertFalse(expected and not detected, (old, new, response))
                        if old['required'] == new['required']:
                            self.assertEqual(detected, expected, (old, new, response))

    def test_transitive_redundancy(self):
        old = {'dependentRequired': {'a': ['b'], 'b': ['c']}}
        new = {'dependentRequired': {'a': ['b', 'c'], 'b': ['c']}}
        self.assertFalse(findings(old, new))
        self.assertFalse(findings(new, old, True))
        self.assertEqual(d.compare(document(old), document(new))['status'], 'review_required')

    def test_required_seed_closure(self):
        old = {'required': ['b'], 'dependentRequired': {'b': ['c']}}
        new = dict(old, dependentRequired={'a': ['c'], 'b': ['c']})
        self.assertFalse(findings(old, new))
        self.assertTrue(findings({}, {'dependentRequired': {'a': ['b']}}))

    def test_self_dependencies_empty_and_cycles(self):
        for graph in ({'a': ['a']}, {'a': []}, {}):
            self.assertFalse(findings({}, {'dependentRequired': graph}))
        cycle = {'dependentRequired': {'a': ['b'], 'b': ['a']}}
        self.assertEqual(len(findings({}, cycle)), 2)
        self.assertFalse(findings(cycle, {}))
        self.assertEqual(len(findings(cycle, {}, True)), 2)

    def test_versions_and_nonobject_types(self):
        old, new = {}, {'dependentRequired': {'a': ['b']}}
        self.assertFalse(findings(old, new, version='3.0.3'))
        for kind in ('string', ['array', 'null']):
            self.assertFalse(findings(dict(old, type=kind), dict(new, type=kind)))
        for kind in ('object', ['object', 'null']):
            self.assertTrue(findings(dict(old, type=kind), dict(new, type=kind)))
        self.assertTrue(findings(old, new))
        self.assertEqual(d.compare(document(old, version='3.0.3'),
                                   document(new))['status'], 'review_required')

    def test_malformed_constraints(self):
        for value in (None, [], True, {'a': 'b'}, {'a': [1]}, {'a': ['b', 'b']}):
            with self.subTest(value=value):
                with self.assertRaises(d.api.Invalid):
                    findings({}, {'dependentRequired': value})

    def test_graph_limits(self):
        with self.assertRaises(d.api.Invalid):
            findings({}, {'dependentRequired': {'a': [str(i) for i in range(256)]}})
        graph = {str(i): [str(j) for j in range(33)] for i in range(32)}
        with self.assertRaises(d.api.Invalid):
            findings({}, {'dependentRequired': graph})

    def test_nested_refs_recursion_and_escaped_paths(self):
        old = document({'$ref': '#/components/schemas/N'})
        old['components'] = {'schemas': {'N': {'properties': {
            'next': {'$ref': '#/components/schemas/N'},
            'array': {'type': 'array', 'items': {'type': 'object'}}}}}}
        new = copy.deepcopy(old)
        new['components']['schemas']['N']['properties']['array']['items']['dependentRequired'] = {'a/~': ['b']}
        hits = [f for f in d.compare(old, new)['findings']
                if f['code'] == 'dependent_required_incompatible']
        self.assertEqual(len(hits), 1)
        self.assertTrue(hits[0]['location'].endswith('/items/dependentRequired/a~1~0'))

    def test_inherited_findings(self):
        old = {'properties': {'x': {'type': 'array', 'const': [1], 'minItems': 1}}}
        new = {'properties': {'x': {'type': 'array', 'const': [2], 'minItems': 2, 'uniqueItems': True}},
               'dependentRequired': {'a': ['b']}}
        codes = {f['code'] for f in d.compare(document(old), document(new))['findings']}
        self.assertTrue({'const_incompatible', 'size_bound_incompatible',
                         'unique_items_incompatible', 'dependent_required_incompatible'} <= codes)
        self.assertTrue(any(f['code'] == 'multiple_of_incompatible' for f in
                            d.compare(document({'multipleOf': 2}), document({'multipleOf': 3}))['findings']))

    def test_demo_and_capture(self):
        report = d.demo()
        self.assertEqual(report['counts'], {'breaking': 1, 'review': 1, 'info': 0})
        obj, _ = d.api.load(d.unique.const.multiple.bound.BASE.with_name('imd-openapi.json'))
        self.assertEqual(d.compare(obj, obj)['findings'], [])
        self.assertEqual(d.compare(obj, obj)['operations_compared'], 5)

    def test_cli(self):
        scratch = Path('test/scratch')
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            old, new = Path(folder) / 'old.json', Path(folder) / 'new.json'
            old.write_text(json.dumps(document({})))
            for schema, expected in (({}, 0), ({'dependentRequired': {'a': ['b']}}, 1),
                                     ({'dependentRequired': {'a': []}}, 3),
                                     ({'dependentRequired': {'a': None}}, 2)):
                new.write_text(json.dumps(document(schema)))
                run = subprocess.run([sys.executable, '-B', str(Path(__file__).with_name('dependcheck.py')),
                                      'compare', str(old), str(new)], capture_output=True, text=True, timeout=10)
                self.assertEqual(run.returncode, expected, run.stderr)
                if expected != 2:
                    self.assertEqual(len(json.loads(run.stdout)['old_sha256']), 64)


if __name__ == '__main__':
    unittest.main()
