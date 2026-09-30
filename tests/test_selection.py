import os

from colcon_guard import envfilter
from colcon_guard.selection import _layer_lines
from tests.conftest import write_colcon_setup


def _layers(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    a, b, base = tmp_path / 'a', tmp_path / 'b', tmp_path / 'base'
    base.mkdir()
    write_colcon_setup(a, [])
    write_colcon_setup(b, [str(a)])
    env = {
        'COLCON_PREFIX_PATH': os.pathsep.join([str(b), str(a)]),
        'AMENT_PREFIX_PATH': os.pathsep.join(
            [f'{b}/p', f'{a}/p', str(base)]),
    }
    return a, base, env


def test_layers_before_the_flag_show_roles(tmp_path, monkeypatch):
    a, base, env = _layers(tmp_path, monkeypatch)
    plan = envfilter.plan_drop_self(env, str(a))
    rows = _layer_lines(envfilter.environment_layers(env), plan, str(a),
                        acting=False)
    assert rows == [
        'b     overlay (built on top of this workspace)',
        'a     this workspace',
        'base  underlay',
    ]


def test_layers_with_drop_self_show_dropped_and_kept(tmp_path, monkeypatch):
    a, base, env = _layers(tmp_path, monkeypatch)
    plan = envfilter.plan_drop_self(env, str(a))
    rows = _layer_lines(envfilter.environment_layers(env), plan, str(a),
                        acting=True)
    assert rows == [
        'b     dropped (built on top of this workspace)',
        'a     dropped (this workspace)',
        'base  kept',
    ]


def test_layers_with_clean_underlay_mark_base(tmp_path, monkeypatch):
    a, base, env = _layers(tmp_path, monkeypatch)
    plan = envfilter.plan_clean(env, [str(base)])
    rows = _layer_lines(envfilter.environment_layers(env), plan, str(a),
                        acting=True, bases=[str(base)])
    assert rows == [
        'b     dropped',
        'a     dropped',
        'base  kept (base install)',
    ]


def test_layers_include_roots_missing_from_the_environment(
        tmp_path, monkeypatch):
    a, base, env = _layers(tmp_path, monkeypatch)
    plan = envfilter.plan_drop_self(env, str(a))
    rows = _layer_lines([], plan, str(a), acting=False)
    assert any(row.endswith('this workspace') for row in rows)
