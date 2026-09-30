# Copyright 2026 Vojnar Autonomous s.r.o.
# Licensed under the Apache License, Version 2.0

import os
import re

from colcon_guard.envfilter import PREFIX_VARS
from colcon_guard.envfilter import split_pathlist

_ROS_DISTRO_IN_PATH = re.compile(r'(?:^|/)opt/ros/([A-Za-z0-9_]+)(?:/|$)')
_SKIP_DIRS = {'build', 'install', 'log', '.git', '.hg', '.svn', '__pycache__'}
_PACKAGE_MARKERS = (
    'package.xml', 'setup.py', 'setup.cfg', 'pyproject.toml', 'CMakeLists.txt')
_MAX_REPORTED = 20


def find_distros(env):
    found = set()
    for var in PREFIX_VARS:
        for entry in split_pathlist(env.get(var, '')):
            m = _ROS_DISTRO_IN_PATH.search(entry)
            if m:
                found.add(m.group(1))
    return found


def check_distro(env, expected=None):
    """Return an error message, or None if the environment is consistent."""
    expected = expected or env.get('ROS_DISTRO') or None
    found = find_distros(env)
    if expected:
        foreign = sorted(found - {expected})
        if foreign:
            return (f"expected ROS distro '{expected}' but the prefix paths "
                    f"contain: {', '.join(foreign)}")
    elif len(found) > 1:
        return ('prefix paths mix ROS distros: '
                f"{', '.join(sorted(found))}")
    return None


def find_broken_symlinks(roots):
    broken = []
    for root in roots:
        root = os.path.abspath(root)
        for current, dirs, files in os.walk(root, followlinks=False):
            names = set(dirs) | set(files)
            if current != root and (
                    'COLCON_IGNORE' in names or
                    any(m in names for m in _PACKAGE_MARKERS)):
                dirs[:] = []
                continue
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
            for name in list(dirs) + list(files):
                path = os.path.join(current, name)
                if os.path.islink(path) and not os.path.exists(path):
                    broken.append(path)
                    if len(broken) >= _MAX_REPORTED:
                        return broken
    return broken
