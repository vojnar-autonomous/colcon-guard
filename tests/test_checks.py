# Copyright 2026 Vojnar Autonomous s.r.o.
# Licensed under the Apache License, Version 2.0

import os

from colcon_guard import checks
from colcon_guard import config


def test_distro_expected_from_env():
    env = {'ROS_DISTRO': 'jazzy',
           'AMENT_PREFIX_PATH': '/opt/ros/jazzy:/opt/ros/humble'}
    assert 'humble' in checks.check_distro(env)


def test_distro_consistent():
    env = {'ROS_DISTRO': 'jazzy', 'AMENT_PREFIX_PATH': '/opt/ros/jazzy:/ws/i'}
    assert checks.check_distro(env) is None


def test_distro_mixed_without_expectation():
    env = {'AMENT_PREFIX_PATH': '/opt/ros/jazzy', 'CMAKE_PREFIX_PATH':
           '/opt/ros/humble'}
    assert 'mix' in checks.check_distro(env)
    assert checks.check_distro(env, expected='jazzy') is not None


def test_distro_config_overrides_env():
    env = {'ROS_DISTRO': 'humble', 'AMENT_PREFIX_PATH': '/opt/ros/humble'}
    assert checks.check_distro(env, expected='jazzy') is not None


def test_broken_symlinks_detected_and_pruned(tmp_path):
    src = tmp_path / 'src'
    (src / 'pkg').mkdir(parents=True)
    (src / 'pkg' / 'package.xml').write_text('<package/>')
    os.symlink('/nonexistent/inside_pkg', src / 'pkg' / 'dead_inside')
    (src / 'ignored').mkdir()
    (src / 'ignored' / 'COLCON_IGNORE').write_text('')
    os.symlink('/nonexistent/ignored', src / 'ignored' / 'dead')
    (tmp_path / 'build').mkdir()
    os.symlink('/nonexistent/build', tmp_path / 'build' / 'dead')
    os.symlink('/nonexistent/top', src / 'dead_top')
    os.symlink(src / 'pkg', src / 'alive')
    found = checks.find_broken_symlinks([str(tmp_path)])
    assert found == [str(src / 'dead_top')]


def test_config_load_validation_and_precedence(tmp_path, capsys):
    (tmp_path / config.CONFIG_NAME).write_text(
        'drop_self_underlay = true\nbase_prefix = "/opt/ros/jazzy"\n'
        'bogus = 1\n')
    cfg = config.load_config(tmp_path)
    assert cfg == {'drop_self_underlay': True,
                   'base_prefix': ['/opt/ros/jazzy']}
    assert 'bogus' in capsys.readouterr().err
    assert config.resolve_flag(None, cfg, 'drop_self_underlay') == (
        True, config.CONFIG_NAME)
    assert config.resolve_flag(False, cfg, 'drop_self_underlay') == (
        False, 'command line')
    assert config.resolve_flag(None, cfg, 'clean_underlay') == (
        False, 'default')


def test_config_type_error_exits(tmp_path):
    import pytest
    (tmp_path / config.CONFIG_NAME).write_text('drop_self_underlay = "yes"\n')
    with pytest.raises(SystemExit):
        config.load_config(tmp_path)
