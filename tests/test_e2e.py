# Copyright 2026 Vojnar Autonomous s.r.o.
# Licensed under the Apache License, Version 2.0

import json
import os
import signal
import socket
import subprocess
import time

import pytest

from colcon_guard import envfilter
from colcon_guard.config import CONFIG_NAME

pytestmark = pytest.mark.e2e


def chain(ws):
    return envfilter.read_chain(str(ws / 'install'))


def build_env_dump(ws, pkg):
    path = ws / 'build' / pkg / 'colcon_command_prefix_setup_py.sh.env'
    return dict(
        line.split('=', 1) for line in path.read_text().splitlines()
        if '=' in line)


def ok(result):
    assert result.returncode == 0, result.stdout + result.stderr
    return result


@pytest.fixture
def layered(rig, sh):
    """Workspace A built, workspace B built over A."""
    a, b = rig / 'ws_a', rig / 'ws_b'
    ok(sh(a, 'colcon build'))
    ok(sh(b, 'colcon build', source=[a / 'install']))
    return a, b


def test_baseline_plain_rebuild_closes_the_cycle(layered, sh):
    a, b = layered
    assert chain(a) == []
    assert chain(b) == [str(a / 'install')]
    ok(sh(a, 'colcon build', source=[b / 'install']))
    assert chain(a) == [str(b / 'install')]


def test_plain_rebuild_warns_with_hint(layered, sh):
    a, b = layered
    result = ok(sh(a, 'colcon build', source=[b / 'install']))
    assert 'did you miss --drop-self-underlay?' in result.stderr
    assert chain(a) == [str(b / 'install')]


@pytest.mark.parametrize('order', ['ab', 'ba'])
def test_drop_self_underlay_repairs_closed_cycle(layered, sh, order):
    a, b = layered
    ok(sh(a, 'colcon build', source=[b / 'install']))
    assert chain(a) == [str(b / 'install')]
    src = [a / 'install', b / 'install'] if order == 'ab' \
        else [b / 'install', a / 'install']
    result = ok(sh(a, 'colcon build --drop-self-underlay', source=src))
    assert 'the cycle is cut' in result.stderr
    assert chain(a) == []
    dump = build_env_dump(a, 'a_app')
    assert str(b / 'install') not in dump.get('AMENT_PREFIX_PATH', '')
    assert str(b / 'install') not in dump.get('PYTHONPATH', '')


def test_drop_self_underlay_every_step_keeps_true_underlay(rig, sh):
    a, b = rig / 'ws_a', rig / 'ws_b'
    flag = 'colcon build --drop-self-underlay'
    ok(sh(a, flag))
    ok(sh(b, flag, source=[a / 'install']))
    assert chain(b) == [str(a / 'install')]
    result = ok(sh(a, flag, source=[b / 'install']))
    assert chain(a) == []
    assert chain(b) == [str(a / 'install')]
    assert 'dropping' in result.stderr


def test_building_the_upper_workspace_keeps_lower_one(layered, sh):
    a, b = layered
    result = ok(sh(b, 'colcon build --drop-self-underlay',
                   source=[b / 'install']))
    guard_lines = [line for line in result.stderr.splitlines()
                   if line.startswith('colcon-guard:')]
    assert not any(str(a / 'install') in line for line in guard_lines)
    assert chain(b) == [str(a / 'install')]


def test_local_config_enables_and_cli_overrides(layered, sh):
    a, b = layered
    (a / CONFIG_NAME).write_text('drop_self_underlay = true\n')
    ok(sh(a, 'colcon build', source=[b / 'install']))
    assert chain(a) == []
    ok(sh(a, 'colcon build', source=[b / 'install']))
    ok(sh(a, 'colcon build --no-drop-self-underlay', source=[b / 'install']))
    assert chain(a) == [str(b / 'install')]


def test_test_verb_uses_the_same_chain_handling(layered, sh):
    a, b = layered
    result = ok(sh(a, 'colcon test --drop-self-underlay',
                   source=[b / 'install']))
    assert 'dropping' in result.stderr
    result = ok(sh(a, 'colcon test', source=[b / 'install']))
    assert 'did you miss --drop-self-underlay?' in result.stderr


def test_clean_underlay_resets_to_base(layered, sh, tmp_path):
    a, b = layered
    base = tmp_path / 'fake_ros'
    base.mkdir()
    (a / CONFIG_NAME).write_text(f'base_prefix = ["{base}"]\n')
    ok(sh(a, 'colcon build', source=[b / 'install']))
    result = ok(sh(a, 'colcon build --clean-underlay',
                   source=[b / 'install'],
                   env={'AMENT_PREFIX_PATH': str(base)}))
    assert chain(a) == []
    assert 'clean-underlay: dropping' in result.stderr
    dump = build_env_dump(a, 'a_app')
    assert str(base) in dump['AMENT_PREFIX_PATH']
    assert str(b / 'install') not in dump['AMENT_PREFIX_PATH']


def test_clean_underlay_needs_base(layered, sh):
    a, _ = layered
    result = sh(a, 'colcon build --clean-underlay')
    assert result.returncode != 0
    assert 'needs a base install' in result.stderr


def test_lock_blocks_concurrent_build_and_reports_holder(rig, sh):
    a = rig / 'ws_a'
    env = {'GUARD_RIG_SLEEP': '2'}
    first = subprocess.Popen(
        ['bash', '-c', f'cd {a} && colcon build'],
        env={**os.environ, **env}, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        status = None
        for _ in range(40):
            status = sh(a, 'colcon --log-base /dev/null guard status --json')
            if json.loads(status.stdout)['state'] == 'busy':
                break
            time.sleep(0.25)
        assert status.returncode == 1
        holder = json.loads(status.stdout)['holder']
        assert holder['hostname'] == socket.gethostname()
        second = sh(a, 'colcon build')
        assert second.returncode != 0
        assert 'already being built or tested elsewhere' in second.stderr
        assert socket.gethostname() in second.stderr
        assert 'colcon build' in second.stderr or 'build' in second.stderr
    finally:
        first.wait(timeout=120)
    ok(sh(a, 'colcon build'))
    state = json.loads(
        sh(a, 'colcon --log-base /dev/null guard status --json').stdout)
    assert state['state'] == 'free'


def test_lock_released_when_builder_is_killed(rig, sh):
    a = rig / 'ws_a'
    first = subprocess.Popen(
        ['bash', '-c', f'cd {a} && exec colcon build'],
        env={**os.environ, 'GUARD_RIG_SLEEP': '5'},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True)
    try:
        for _ in range(40):
            out = sh(a, 'colcon --log-base /dev/null guard status --json')
            if json.loads(out.stdout)['state'] == 'busy':
                break
            time.sleep(0.25)
        else:
            pytest.fail('lock was never taken')
        os.killpg(first.pid, signal.SIGKILL)
        first.wait(timeout=30)
        time.sleep(0.3)
        out = json.loads(
            sh(a, 'colcon --log-base /dev/null guard status --json').stdout)
        assert out['state'] == 'free'
        assert out['holder']['verb'] == 'build'
    finally:
        try:
            os.killpg(first.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    ok(sh(a, 'colcon build'))


def test_distro_guard_hard_fails(rig, sh):
    a = rig / 'ws_a'
    result = sh(a, 'colcon build', env={
        'ROS_DISTRO': 'jazzy',
        'AMENT_PREFIX_PATH': '/opt/ros/humble:/opt/ros/jazzy'})
    assert result.returncode != 0
    assert "expected ROS distro 'jazzy'" in result.stderr
    assert not (a / 'build' / 'a_core').exists()


def test_distro_expectation_from_local_config(rig, sh):
    a = rig / 'ws_a'
    (a / CONFIG_NAME).write_text('expected_distro = "jazzy"\n')
    result = sh(a, 'colcon build',
                env={'AMENT_PREFIX_PATH': '/opt/ros/humble'})
    assert result.returncode != 0
    assert 'humble' in result.stderr


def test_broken_symlink_warns_then_errors(rig, sh):
    a = rig / 'ws_a'
    os.symlink('/nonexistent/target', a / 'src' / 'dead_link')
    result = ok(sh(a, 'colcon build'))
    assert 'broken symlinks in the workspace' in result.stderr
    assert 'dead_link' in result.stderr
    result = sh(a, 'colcon build --broken-symlink-error')
    assert result.returncode != 0
    assert 'dead_link' in result.stderr


def test_other_verbs_are_not_guarded(rig, sh):
    a = rig / 'ws_a'
    os.symlink('/nonexistent/target', a / 'src' / 'dead_link')
    result = ok(sh(a, 'colcon list'))
    assert 'colcon-guard' not in result.stderr
    assert not (a / '.colcon_guard.lock').exists()
