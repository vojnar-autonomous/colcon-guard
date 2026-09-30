# Copyright 2026 Vojnar Autonomous s.r.o.
# Licensed under the Apache License, Version 2.0

import signal
import subprocess
import sys

import pytest

from colcon_guard import lock as lockmod

HOLDER = (
    'import sys, time\n'
    'from colcon_guard.lock import WorkspaceLock, holder_info\n'
    'l = WorkspaceLock(sys.argv[1]); l.acquire(holder_info("build"))\n'
    'print("held", flush=True); time.sleep(60)\n')


def _spawn_holder(root):
    proc = subprocess.Popen(
        [sys.executable, '-c', HOLDER, str(root)],
        stdout=subprocess.PIPE, text=True)
    assert proc.stdout.readline().strip() == 'held'
    return proc


def test_acquire_writes_metadata_and_blocks_second_holder(tmp_path):
    first = lockmod.WorkspaceLock(tmp_path)
    first.acquire(lockmod.holder_info('build'))
    second = lockmod.WorkspaceLock(tmp_path)
    with pytest.raises(lockmod.WorkspaceBusy) as info:
        second.acquire(lockmod.holder_info('test'))
    assert info.value.holder['verb'] == 'build'
    assert info.value.holder['hostname']
    assert lockmod.probe(tmp_path)[0] == 'busy'
    first.release()
    assert lockmod.probe(tmp_path)[0] == 'free'
    second.acquire(lockmod.holder_info('test'))
    assert lockmod.read_holder(second.path)['verb'] == 'test'
    second.release()


def test_busy_does_not_wipe_holder_metadata(tmp_path):
    first = lockmod.WorkspaceLock(tmp_path)
    first.acquire(lockmod.holder_info('build'))
    with pytest.raises(lockmod.WorkspaceBusy):
        lockmod.WorkspaceLock(tmp_path).acquire(lockmod.holder_info('test'))
    assert lockmod.read_holder(first.path)['verb'] == 'build'
    first.release()


def test_lock_survives_killed_holder(tmp_path):
    proc = _spawn_holder(tmp_path)
    try:
        assert lockmod.probe(tmp_path)[0] == 'busy'
        proc.send_signal(signal.SIGKILL)
        proc.wait()
        state, stale = lockmod.probe(tmp_path)
        assert state == 'free'
        assert stale['pid'] == proc.pid
        lock = lockmod.WorkspaceLock(tmp_path)
        lock.acquire(lockmod.holder_info('build'))
        lock.release()
    finally:
        proc.kill()


def test_probe_absent(tmp_path):
    assert lockmod.probe(tmp_path) == ('absent', None)


def test_filesystem_type_and_unreliable_detection(tmp_path):
    assert isinstance(lockmod.filesystem_type(tmp_path), str)
    assert lockmod._UNRELIABLE_FS.match('nfs4')
    assert lockmod._UNRELIABLE_FS.match('fuse.sshfs')
    assert lockmod._UNRELIABLE_FS.match('9p')
    assert not lockmod._UNRELIABLE_FS.match('ext4')
    assert not lockmod._UNRELIABLE_FS.match('overlay')
