# Copyright 2026 Vojnar Autonomous s.r.o.
# Licensed under the Apache License, Version 2.0

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib

from colcon_guard.output import die
from colcon_guard.output import say

CONFIG_NAME = '.colcon_guard.toml'

_BOOL_KEYS = (
    'drop_self_underlay', 'clean_underlay', 'broken_symlink_error')
_KEYS = _BOOL_KEYS + ('expected_distro', 'base_prefix')


def load_config(root):
    path = Path(root) / CONFIG_NAME
    if not path.is_file():
        return {}
    try:
        with path.open('rb') as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as e:
        die(f'cannot read {path}: {e}')
    for key in sorted(set(data) - set(_KEYS)):
        say(f'{CONFIG_NAME}: unknown key {key!r} ignored', 'warning')
        del data[key]
    for key in _BOOL_KEYS:
        if key in data and not isinstance(data[key], bool):
            die(f'{CONFIG_NAME}: {key} must be a boolean')
    if 'expected_distro' in data and not isinstance(
            data['expected_distro'], str):
        die(f'{CONFIG_NAME}: expected_distro must be a string')
    if 'base_prefix' in data:
        value = data['base_prefix']
        if isinstance(value, str):
            data['base_prefix'] = [value]
        elif not (isinstance(value, list) and
                  all(isinstance(v, str) for v in value)):
            die(f'{CONFIG_NAME}: base_prefix must be a string or a list')
    return data


def resolve_flag(cli_value, config, key):
    if cli_value is not None:
        return cli_value, 'command line'
    if key in config:
        return config[key], CONFIG_NAME
    return False, 'default'
