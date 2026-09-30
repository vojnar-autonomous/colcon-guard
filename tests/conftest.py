# Copyright 2026 Vojnar Autonomous s.r.o.
# Licensed under the Apache License, Version 2.0

import os
import shutil
import subprocess
from pathlib import Path

import pytest

RIG = Path(__file__).parent / 'rig'


@pytest.fixture
def rig(tmp_path):
    target = tmp_path / 'rig'
    shutil.copytree(RIG, target)
    return target


@pytest.fixture
def sh(tmp_path):
    colcon_home = tmp_path / 'colcon_home'
    colcon_home.mkdir()

    def run(cwd, command, *, source=(), env=None, timeout=180):
        prelude = ''.join(f'. {Path(s) / "setup.sh"}; ' for s in source)
        full_env = {
            'PATH': os.environ['PATH'],
            'HOME': str(tmp_path),
            'COLCON_HOME': str(colcon_home),
            'LANG': 'C.UTF-8',
        }
        full_env.update(env or {})
        return subprocess.run(
            ['bash', '-c', f'{prelude}cd {cwd} && {command}'],
            env=full_env, capture_output=True, text=True, timeout=timeout)

    return run


def write_colcon_setup(prefix, chain):
    """Write a setup.sh in colcon's prefix_chain format (chain: highest first)."""
    prefix = Path(prefix)
    prefix.mkdir(parents=True, exist_ok=True)
    lines = [
        '# generated from colcon_core/shell/template/prefix_chain.sh.em',
        '',
        '# This script extends the environment with the environment of other '
        'prefix',
        '# paths which were sourced when this file was generated.',
        '',
    ]
    if chain:
        lines += ['# source chained prefixes']
        for entry in reversed(chain):
            lines += [
                '# setting COLCON_CURRENT_PREFIX avoids relying on the build '
                'time prefix of the sourced script',
                f'COLCON_CURRENT_PREFIX="{entry}"',
                '_colcon_prefix_chain_sh_source_script '
                '"$COLCON_CURRENT_PREFIX/local_setup.sh"',
                '',
            ]
    lines += [
        '# source this prefix',
        'COLCON_CURRENT_PREFIX="$_colcon_prefix_chain_sh_COLCON_CURRENT_PREFIX"',
    ]
    (prefix / 'setup.sh').write_text('\n'.join(lines) + '\n')
    (prefix / '.colcon_install_layout').write_text('isolated\n')
