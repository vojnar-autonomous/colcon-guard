# Copyright 2026 Vojnar Autonomous s.r.o.
# Licensed under the Apache License, Version 2.0

import argparse
import os

from colcon_core.command import register_command_exit_handler
from colcon_core.logging import colcon_logger
from colcon_core.package_selection import PackageSelectionExtensionPoint

from colcon_guard import checks
from colcon_guard import envfilter
from colcon_guard.config import CONFIG_NAME
from colcon_guard.config import load_config
from colcon_guard.config import resolve_flag
from colcon_guard.lock import holder_info
from colcon_guard.lock import holder_lines
from colcon_guard.lock import LockUnsupported
from colcon_guard.lock import unreliable_filesystem
from colcon_guard.lock import WorkspaceBusy
from colcon_guard.lock import WorkspaceLock
from colcon_guard.output import die
from colcon_guard.output import display_path
from colcon_guard.output import say

logger = colcon_logger.getChild(__name__)

GUARDED_VERBS = ('build', 'test')

_state = {'done': False, 'lock': None}


class GuardPackageSelection(PackageSelectionExtensionPoint):
    """Guard the workspace before build and test."""

    PRIORITY = 900

    def add_arguments(self, *, parser):
        parser.add_argument(
            '--drop-self-underlay', dest='guard_drop_self_underlay',
            action=argparse.BooleanOptionalAction, default=None,
            help='Remove this workspace\'s own install and everything '
                 'sourced on top of it from the environment before '
                 'build/test')
        parser.add_argument(
            '--clean-underlay', dest='guard_clean_underlay',
            action=argparse.BooleanOptionalAction, default=None,
            help='Reset the environment to the base ROS install only '
                 '(build/test)')
        parser.add_argument(
            '--broken-symlink-error', dest='guard_broken_symlink_error',
            action=argparse.BooleanOptionalAction, default=None,
            help='Fail instead of warning when broken symlinks are found '
                 'in the workspace (build/test)')

    def select_packages(self, *, args, decorators):
        pass

    def check_parameters(self, *, args, pkg_names):
        if getattr(args, 'verb_name', None) not in GUARDED_VERBS:
            return
        if _state['done']:
            return
        _state['done'] = True
        run_guard(args)


def _install_base(args):
    return os.path.abspath(getattr(args, 'install_base', None) or 'install')


def _acquire_lock(root, verb):
    fstype = unreliable_filesystem(root)
    if fstype:
        say(f'workspace is on a {fstype} filesystem, flock is not '
            'guaranteed to work across hosts here', 'warning')
    lock = WorkspaceLock(root)
    try:
        lock.acquire(holder_info(verb))
    except WorkspaceBusy as e:
        die('workspace is already being built or tested elsewhere',
            holder_lines(e.holder))
    except LockUnsupported as e:
        say(f'cannot lock the workspace ({e}); concurrent builds are not '
            'guarded', 'warning')
        return
    _state['lock'] = lock
    register_command_exit_handler(lock.release)


def _resolve_base_prefixes(config, env):
    if config.get('base_prefix'):
        bases = config['base_prefix']
    elif env.get('ROS_DISTRO'):
        bases = [f"/opt/ros/{env['ROS_DISTRO']}"]
    else:
        die('--clean-underlay needs a base install: set ROS_DISTRO or '
            f'base_prefix in {CONFIG_NAME}')
    missing = [b for b in bases if not os.path.isdir(b)]
    if missing:
        die('--clean-underlay: base prefix does not exist: '
            f"{', '.join(missing)}")
    return bases


def _apply(plan, env):
    changes = envfilter.apply_plan(env, plan.roots)
    logger.debug('env changes: %s', changes)


def _layer_lines(layers, plan, own, *, acting, bases=()):
    layers = [r for r in plan.roots if r not in layers] + list(layers)
    names = [display_path(layer) for layer in layers]
    width = max(map(len, names), default=0)
    lines = []
    for layer, name in zip(layers, names):
        dropped = layer in plan.roots
        if acting and dropped:
            if plan.mode == 'clean-underlay':
                status = 'dropped'
            elif layer == own:
                status = 'dropped (this workspace)'
            else:
                status = f'dropped ({plan.reasons[layer]})'
        elif acting:
            if any(envfilter.is_under(layer, b) for b in bases):
                status = 'kept (base install)'
            elif plan.mode == 'clean-underlay':
                status = 'kept (not a colcon workspace)'
            else:
                status = 'kept'
        elif layer == own:
            status = 'this workspace'
        elif dropped:
            status = f'overlay ({plan.reasons[layer]})'
        else:
            status = 'underlay'
        lines.append(f'{name.ljust(width)}  {status}')
    return lines


def _report_plan(plan, layers, own, bases=()):
    if not plan.empty:
        say(f'{plan.mode} - environment layers, highest priority first:',
            details=_layer_lines(layers, plan, own, acting=True, bases=bases))
    if plan.cycles:
        names = ', '.join(display_path(c) for c in plan.cycles)
        say(f'this workspace and {names} chain each other; '
            'the cycle is cut', 'warning')


def run_guard(args):
    root = os.getcwd()
    verb = args.verb_name
    env = os.environ
    config = load_config(root)

    _acquire_lock(root, verb)

    drop_self, _ = resolve_flag(
        getattr(args, 'guard_drop_self_underlay', None), config,
        'drop_self_underlay')
    clean, _ = resolve_flag(
        getattr(args, 'guard_clean_underlay', None), config, 'clean_underlay')
    symlink_error, _ = resolve_flag(
        getattr(args, 'guard_broken_symlink_error', None), config,
        'broken_symlink_error')

    install_base = _install_base(args)
    own = envfilter.canon(install_base)
    layers = envfilter.environment_layers(env)
    if clean:
        if drop_self:
            say('--clean-underlay already covers --drop-self-underlay')
        bases = _resolve_base_prefixes(config, env)
        plan = envfilter.plan_clean(env, bases)
        _apply(plan, env)
        _report_plan(plan, layers, own, bases)
        say(f"clean-underlay - underlay set to {', '.join(bases)}")
    elif drop_self:
        plan = envfilter.plan_drop_self(env, install_base)
        _apply(plan, env)
        _report_plan(plan, layers, own)
    else:
        plan = envfilter.plan_drop_self(env, install_base)
        if not plan.empty:
            if own in plan.roots:
                text = (f'{verb} of this workspace would be layered on '
                        'its own install')
            else:
                text = (f'{verb} of this workspace would be layered on '
                        'workspaces built on top of it')
            rows = _layer_lines(layers, plan, own, acting=False)
            say(text, 'warning',
                ['environment layers, highest priority first:'] +
                [f'  {row}' for row in rows])
            say('did you miss --drop-self-underlay?', 'hint')

    message = checks.check_distro(env, config.get('expected_distro'))
    if message:
        die(message)

    base_paths = getattr(args, 'base_paths', None) or ['.']
    broken = checks.find_broken_symlinks(base_paths)
    if broken:
        details = [display_path(path) for path in broken]
        if symlink_error:
            die('broken symlinks in the workspace', details)
        say('broken symlinks in the workspace', 'warning', details)
