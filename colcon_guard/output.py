# Copyright 2026 Vojnar Autonomous s.r.o.
# Licensed under the Apache License, Version 2.0

import os
import sys

from colcon_core.logging import colcon_logger

_logger = colcon_logger.getChild('colcon_guard')


def display_path(path):
    path = os.path.abspath(path)
    candidates = [path, os.path.relpath(path)]
    home = os.path.expanduser('~')
    if home != os.sep and path.startswith(home + os.sep):
        candidates.append('~' + path[len(home):])
    return min(candidates, key=len)


def say(message, level=None, details=()):
    prefix = f'colcon-guard: {level}: ' if level else 'colcon-guard: '
    lines = [prefix + message] + [f'  {line}' for line in details]
    print('\n'.join(lines), file=sys.stderr)
    _logger.debug('\n'.join(lines))


def die(message, details=()):
    lines = [f'colcon-guard: error: {message}']
    lines += [f'  {line}' for line in details]
    _logger.debug('\n'.join(lines))
    raise SystemExit('\n'.join(lines))
