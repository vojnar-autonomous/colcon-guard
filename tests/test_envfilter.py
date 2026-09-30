# Copyright 2026 Vojnar Autonomous s.r.o.
# Licensed under the Apache License, Version 2.0

import os

from colcon_guard import envfilter
from tests.conftest import write_colcon_setup


def test_read_chain_orders_highest_priority_first(tmp_path):
    a, b, c = (tmp_path / n for n in 'abc')
    write_colcon_setup(c, [str(b), str(a)])
    assert envfilter.read_chain(str(c)) == [str(b), str(a)]


def test_read_chain_none_for_foreign_setup(tmp_path):
    (tmp_path / 'setup.sh').write_text('# ament generated\nexport X=1\n')
    assert envfilter.read_chain(str(tmp_path)) is None
    assert envfilter.read_chain(str(tmp_path / 'missing')) is None


def test_chain_closure_is_transitive_and_cycle_safe(tmp_path):
    a, b, c = (tmp_path / n for n in 'abc')
    write_colcon_setup(a, [str(b)])
    write_colcon_setup(b, [str(c)])
    write_colcon_setup(c, [str(a)])
    assert envfilter.chain_closure(str(a)) == {str(a), str(b), str(c)}


def _env(*prefixes, extra=None):
    env = {
        'COLCON_PREFIX_PATH': os.pathsep.join(map(str, prefixes)),
        'AMENT_PREFIX_PATH': os.pathsep.join(
            str(p) + '/pkg' for p in prefixes),
        'PATH': os.pathsep.join([str(p) + '/bin' for p in prefixes] +
                                ['/usr/bin']),
    }
    env.update(extra or {})
    return env


def test_drop_self_no_op_without_self_or_overlays(tmp_path):
    a, base = tmp_path / 'a', tmp_path / 'base'
    write_colcon_setup(a, [])
    env = _env(base)
    plan = envfilter.plan_drop_self(env, str(a))
    assert plan.empty


def test_drop_self_keeps_true_underlay(tmp_path):
    a, b = tmp_path / 'a', tmp_path / 'b'
    write_colcon_setup(a, [])
    write_colcon_setup(b, [str(a)])
    env = _env(b, a)
    plan = envfilter.plan_drop_self(env, str(b))
    assert plan.roots == [str(b)]
    changes = envfilter.apply_plan(env, plan.roots)
    assert env['COLCON_PREFIX_PATH'] == str(a)
    assert 'PATH' in changes and str(b) not in env['PATH']
    assert env['PATH'].endswith('/usr/bin')


def test_drop_self_removes_overlay_and_breaks_cycle_either_order(tmp_path):
    a, b = tmp_path / 'a', tmp_path / 'b'
    write_colcon_setup(a, [str(b)])
    write_colcon_setup(b, [str(a)])
    for order in ((a, b), (b, a)):
        env = _env(*order)
        plan = envfilter.plan_drop_self(env, str(a))
        assert set(plan.roots) == {str(a), str(b)}
        assert plan.cycles == [str(b)]
        envfilter.apply_plan(env, plan.roots)
        assert 'COLCON_PREFIX_PATH' not in env
        assert 'AMENT_PREFIX_PATH' not in env


def test_drop_self_removes_overlay_not_chained_into_env(tmp_path):
    a, b = tmp_path / 'a', tmp_path / 'b'
    write_colcon_setup(a, [])
    write_colcon_setup(b, [str(a)])
    env = _env(b)
    plan = envfilter.plan_drop_self(env, str(a))
    assert plan.roots == [str(b)]


def test_drop_self_falls_back_to_order_without_chain_info(tmp_path):
    a, o, u = tmp_path / 'a', tmp_path / 'o', tmp_path / 'u'
    for p in (a, o, u):
        p.mkdir()
    env = _env(o, a, u)
    plan = envfilter.plan_drop_self(env, str(a))
    assert set(plan.roots) == {str(a), str(o)}
    assert 'order' in plan.reasons[str(o)]


def test_apply_plan_leaves_single_valued_vars_alone(tmp_path):
    a = tmp_path / 'a'
    env = _env(a, extra={'MY_CONFIG': f'{a}/etc/x.yaml'})
    envfilter.apply_plan(env, [str(a)])
    assert env['MY_CONFIG'] == f'{a}/etc/x.yaml'


def test_clean_keeps_base_and_drops_workspaces(tmp_path):
    base, a, foreign = (tmp_path / n for n in ('base', 'a', 'foreign'))
    base.mkdir()
    foreign.mkdir()
    write_colcon_setup(a, [])
    env = {
        'AMENT_PREFIX_PATH': os.pathsep.join(
            [str(a) + '/pkg', str(base), str(foreign)]),
        'COLCON_PREFIX_PATH': str(a),
    }
    plan = envfilter.plan_clean(env, [str(base)])
    assert plan.roots == [str(a)]
    assert plan.kept == [str(foreign)]
    envfilter.apply_plan(env, plan.roots)
    assert env['AMENT_PREFIX_PATH'] == os.pathsep.join([str(base), str(foreign)])
    assert 'COLCON_PREFIX_PATH' not in env


def test_clean_never_treats_system_prefixes_as_workspaces():
    env = {'CMAKE_PREFIX_PATH': '/usr:/usr/local', 'PATH': '/usr/bin:/bin'}
    plan = envfilter.plan_clean(env, ['/opt/ros/none'])
    assert plan.empty
    assert set(plan.kept) == {os.path.realpath('/usr'),
                              os.path.realpath('/usr/local')}

def test_environment_layers_orders_and_collapses(tmp_path):
    base, a, b = (tmp_path / n for n in ('base', 'a', 'b'))
    base.mkdir()
    write_colcon_setup(a, [])
    write_colcon_setup(b, [str(a)])
    env = {
        'AMENT_PREFIX_PATH': os.pathsep.join(
            [f'{b}/pkg1', f'{b}/pkg2', f'{a}/pkg3', str(base)]),
        'COLCON_PREFIX_PATH': os.pathsep.join([str(b), str(a)]),
    }
    assert envfilter.environment_layers(env) == [str(b), str(a), str(base)]


def test_environment_layers_puts_colcon_only_workspaces_first(tmp_path):
    base, ws = tmp_path / 'base', tmp_path / 'ws'
    base.mkdir()
    write_colcon_setup(ws, [])
    env = {'AMENT_PREFIX_PATH': str(base), 'COLCON_PREFIX_PATH': str(ws)}
    assert envfilter.environment_layers(env) == [str(ws), str(base)]
