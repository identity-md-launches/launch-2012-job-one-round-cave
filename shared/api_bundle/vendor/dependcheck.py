#!/usr/bin/env python3
"""Offline OpenAPI 3.1 dependentRequired change checks. Standard library only."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import sys

PREVIOUS = Path(__file__).with_name('uniquecheck.py')
spec = importlib.util.spec_from_file_location('dependcheck_unique', PREVIOUS)
unique = importlib.util.module_from_spec(spec)
spec.loader.exec_module(unique)
api = unique.api
MAX_NAMES = 256
MAX_EDGES = 1024


def rules(schema):
    """Validate the visited dependency graph and its unconditional seeds."""
    raw = schema.get('dependentRequired', {})
    api.require(isinstance(raw, dict), 'dependentRequired must be an object')
    graph = {}
    names = set(schema.get('required', []))  # validated by inherited analyzer
    edges = 0
    for trigger, dependencies in raw.items():
        api.require(isinstance(trigger, str), 'dependency trigger must be a string')
        api.require(isinstance(dependencies, list) and
                    all(isinstance(x, str) for x in dependencies),
                    'dependentRequired values must be arrays of strings')
        api.require(len(set(dependencies)) == len(dependencies),
                    'dependentRequired arrays must have unique entries')
        graph[trigger] = set(dependencies)
        names.add(trigger)
        names.update(dependencies)
        edges += len(dependencies)
    api.require(len(names) <= MAX_NAMES and edges <= MAX_EDGES,
                'dependency graph exceeds 256 names or 1024 edges')
    return graph, set(schema.get('required', []))


def closure(graph, seeds):
    """Least set of present properties satisfying all triggered implications."""
    present = set(seeds)
    pending = list(present)
    while pending:
        trigger = pending.pop()
        for name in graph.get(trigger, frozenset()) - present:
            present.add(name)
            pending.append(name)
    return present


def excludes_objects(schema):
    kind = schema.get('type')
    return kind is not None and (kind != 'object' if isinstance(kind, str)
                                 else 'object' not in kind)


class Analyzer(unique.Analyzer):
    def _schema(self, old, new, loc, direction):
        super()._schema(old, new, loc, direction)
        if not (self.old.obj['openapi'].startswith('3.1.') and
                self.new.obj['openapi'].startswith('3.1.')):
            return
        if 'dependentRequired' not in old and 'dependentRequired' not in new:
            return
        before, after = rules(old), rules(new)
        if excludes_objects(old) and excludes_objects(new):
            return
        # Requests must preserve old inputs; responses must stay inside the old
        # contract. Only positive presence implications are proved here.
        source, target = (before, after) if direction == 'request' else (after, before)
        graph, required = source
        for trigger, dependencies in sorted(target[0].items()):
            implied = closure(graph, required | {trigger})
            missing = sorted(dependencies - implied)
            if missing:
                self.emit('breaking', 'dependent_required_incompatible',
                          api.pointer(loc + '/dependentRequired', trigger),
                          ('New request' if direction == 'request' else 'Old response') +
                          ' dependency on ' + json.dumps(trigger) + ' requires ' +
                          json.dumps(missing) + ', not implied by the ' +
                          ('old request' if direction == 'request' else 'new response') +
                          ' presence rules. Other constraints may make the case unreachable.')


def compare(old, new):
    report = Analyzer(old, new).run()
    report['extension'] = 'dependcheck-v1 (includes uniquecheck, constcheck, multiplecheck, boundcheck)'
    return report


def demo():
    old, digest = api.load(unique.const.multiple.bound.BASE.with_name('imd-openapi.json'))
    old = copy.deepcopy(old)
    body = old['paths']['/requests/quote']['post']['requestBody']['content']['application/json']['schema']
    body.setdefault('properties', {}).update({
        'clientReference': {'type': 'string'}, 'clientContext': {'type': 'string'}})
    new = copy.deepcopy(old)
    new['paths']['/requests/quote']['post']['requestBody']['content']['application/json']['schema']['dependentRequired'] = {
        'clientReference': ['clientContext']}
    report = compare(old, new)
    report.update(capture_sha256=digest,
                  demo='Hypothetical dependency added to the captured public IMD description; no operation called.',
                  illustrative_presence_change='clientReference now also requires clientContext; values and other required fields are outside this illustration.')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('demo')
    diff = commands.add_parser('compare')
    diff.add_argument('old')
    diff.add_argument('new')
    args = parser.parse_args(argv)
    try:
        if args.command == 'demo':
            report = demo()
        else:
            old, oh = api.load(args.old)
            new, nh = api.load(args.new)
            report = compare(old, new)
            report.update(old_sha256=oh, new_sha256=nh)
        print(json.dumps(report, indent=2, allow_nan=False))
        return 0 if args.command == 'demo' else {
            'breaking': 1, 'review_required': 3, 'no_detected_breakage': 0}[report['status']]
    except (api.Invalid, OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        print('dependcheck: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
