# Copyright 2026 Vojnar Autonomous s.r.o.
# Licensed under the Apache License, Version 2.0

import json
import os

from colcon_core.plugin_system import satisfies_version
from colcon_core.verb import VerbExtensionPoint

from colcon_guard.lock import holder_lines
from colcon_guard.lock import lock_path
from colcon_guard.lock import probe
from colcon_guard.lock import unreliable_filesystem

EXIT_CODES = {'free': 0, 'absent': 0, 'busy': 1, 'unsupported': 3}


class GuardVerb(VerbExtensionPoint):
    """Inspect the colcon-guard state of the current workspace."""

    def __init__(self):
        super().__init__()
        satisfies_version(VerbExtensionPoint.EXTENSION_POINT_VERSION, '^1.0')

    def add_arguments(self, *, parser):
        parser.add_argument(
            'action', choices=['status'],
            help='status: report whether a build/test holds the workspace')
        parser.add_argument(
            '--json', action='store_true', help='Machine readable output')

    def main(self, *, context):
        root = os.getcwd()
        state, holder = probe(root)
        fstype = unreliable_filesystem(root)
        if context.args.json:
            print(json.dumps({
                'workspace': root, 'lock': lock_path(root), 'state': state,
                'holder': holder, 'unreliable_filesystem': fstype}))
        else:
            print(f'workspace: {root}')
            print(f'state: {state}')
            if state == 'busy':
                print('holder:')
                for line in holder_lines(holder):
                    print(f'  {line}')
            elif state == 'free' and holder:
                print('last holder (stale record):')
                for line in holder_lines(holder):
                    print(f'  {line}')
            if fstype:
                print(f'warning: {fstype} filesystem, locking may be '
                      'unreliable')
        return EXIT_CODES[state]
