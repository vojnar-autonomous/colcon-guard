# Copyright 2026 Vojnar Autonomous s.r.o.
# Licensed under the Apache License, Version 2.0

import json
import os

from colcon_core.plugin_system import satisfies_version
from colcon_core.verb import VerbExtensionPoint

from colcon_guard import envfilter
from colcon_guard.lock import holder_lines
from colcon_guard.lock import lock_path
from colcon_guard.lock import probe
from colcon_guard.lock import unreliable_filesystem
from colcon_guard.selection import _layer_lines

EXIT_CODES = {'free': 0, 'absent': 0, 'busy': 1, 'unsupported': 3}


class GuardVerb(VerbExtensionPoint):
    """Inspect the colcon-guard state of the current workspace."""

    def __init__(self):
        super().__init__()
        satisfies_version(VerbExtensionPoint.EXTENSION_POINT_VERSION, '^1.0')

    def add_arguments(self, *, parser):
        parser.add_argument(
            'action', choices=['status'],
            help='status: report the workspace lock and the layers in the '
                 'current environment')
        parser.add_argument(
            '--install-base', default='install',
            help='Install directory of this workspace (default: install)')
        parser.add_argument(
            '--json', action='store_true',
            help='Machine readable output (lock state only)')

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
            self._print_layers(context.args.install_base)
        return EXIT_CODES[state]

    @staticmethod
    def _print_layers(install_base):
        env = os.environ
        layers = envfilter.environment_layers(env)
        plan = envfilter.plan_drop_self(env, install_base)
        rows = _layer_lines(
            layers, plan, envfilter.canon(install_base), acting=False)
        if not rows:
            print('environment layers: none')
            return
        print('environment layers, highest priority first:')
        for row in rows:
            print(f'  {row}')
