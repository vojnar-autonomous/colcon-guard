import glob
import os
from pathlib import Path

import pytest

from colcon_guard.config import CONFIG_NAME
from tests.test_e2e import build_env_dump
from tests.test_e2e import chain
from tests.test_e2e import ok


def _ros_prefix():
    override = os.environ.get('GUARD_TEST_ROS_PREFIX')
    if override:
        return Path(override)
    for setup in sorted(glob.glob('/opt/ros/*/setup.sh')):
        return Path(setup).parent
    return None


ROS = _ros_prefix()

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.ros,
    pytest.mark.skipif(ROS is None, reason='no ROS 2 installation found'),
]


def _rows(stderr):
    return [' '.join(line.split()) for line in stderr.splitlines()]


def _ros_row(stderr):
    rows = [row for row in _rows(stderr) if ROS.name in row]
    assert rows, stderr
    return rows[0]


def test_plain_ros_environment_is_silent(rig, sh):
    result = ok(sh(rig / 'ws_a', 'colcon build', source=[ROS]))
    assert 'colcon-guard' not in result.stderr


def test_ros_base_is_listed_as_underlay(rig, sh):
    a = rig / 'ws_a'
    ok(sh(a, 'colcon build', source=[ROS]))
    result = ok(sh(a, 'colcon build', source=[ROS, a / 'install']))
    assert _ros_row(result.stderr).endswith('underlay')
    assert 'install this workspace' in _rows(result.stderr)


def test_drop_self_keeps_ros_in_the_chain(rig, sh):
    a = rig / 'ws_a'
    ok(sh(a, 'colcon build', source=[ROS]))
    result = ok(sh(a, 'colcon build --drop-self-underlay',
                   source=[ROS, a / 'install']))
    assert _ros_row(result.stderr).endswith('kept')
    assert chain(a) == [os.path.realpath(ROS)]


def test_clean_underlay_keeps_the_ros_base(rig, sh):
    a = rig / 'ws_a'
    (a / CONFIG_NAME).write_text(f'base_prefix = ["{ROS}"]\n')
    ok(sh(a, 'colcon build', source=[ROS]))
    result = ok(sh(a, 'colcon build --clean-underlay',
                   source=[ROS, a / 'install']))
    assert 'kept (base install)' in result.stderr
    assert chain(a) == [os.path.realpath(ROS)]
    assert str(ROS) in build_env_dump(a, 'a_app')['AMENT_PREFIX_PATH']


def test_distro_guard_on_sourced_ros(rig, sh):
    if not str(ROS).startswith('/opt/ros/'):
        pytest.skip('the distro guard keys on /opt/ros/<distro> paths')
    other = 'humble' if ROS.name != 'humble' else 'jazzy'
    result = sh(rig / 'ws_a', f'ROS_DISTRO={other} colcon build',
                source=[ROS])
    assert result.returncode != 0
    assert f"expected ROS distro '{other}'" in result.stderr
