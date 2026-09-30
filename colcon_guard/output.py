# Copyright 2026 Vojnar Autonomous s.r.o.
# Licensed under the Apache License, Version 2.0

import sys


def say(message, level='notice'):
    print(f'colcon-guard: {level}: {message}', file=sys.stderr)


def die(message):
    raise SystemExit(f'colcon-guard: error: {message}')
