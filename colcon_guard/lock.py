# Copyright 2026 Vojnar Autonomous s.r.o.
# Licensed under the Apache License, Version 2.0

import datetime
import errno
import fcntl
import json
import os
import re
import socket
import sys

from colcon_guard import __version__

LOCK_NAME = '.colcon_guard.lock'

_UNSUPPORTED_ERRNOS = (errno.ENOLCK, errno.EOPNOTSUPP, errno.ENOSYS, errno.EINVAL)
_UNRELIABLE_FS = re.compile(
    r'^(nfs\d*|cifs|smb\w*|9p|drvfs|virtiofs|vboxsf|ceph|glusterfs|lustre|'
    r'afs|ncpfs|fuse(\..+)?)$')


class LockUnsupported(Exception):
    pass


class WorkspaceBusy(Exception):
    def __init__(self, holder):
        super().__init__('workspace is locked')
        self.holder = holder


def lock_path(root):
    return os.path.join(str(root), LOCK_NAME)


def filesystem_type(path):
    path = os.path.realpath(path)
    best_len, best_type = -1, None
    try:
        with open('/proc/self/mountinfo') as handle:
            lines = handle.read().splitlines()
    except OSError:
        return None
    for line in lines:
        left, sep, right = line.partition(' - ')
        fields = left.split(' ')
        if not sep or len(fields) < 5:
            continue
        mount_point = re.sub(
            r'\\([0-7]{3})', lambda m: chr(int(m.group(1), 8)), fields[4])
        mp = mount_point.rstrip('/')
        if path == mount_point or path.startswith(mp + '/') or mp == '':
            if len(mp) > best_len:
                best_len, best_type = len(mp), right.split(' ')[0]
    return best_type


def unreliable_filesystem(path):
    fstype = filesystem_type(path)
    if fstype and _UNRELIABLE_FS.match(fstype):
        return fstype
    return None


def holder_info(verb):
    return {
        'hostname': socket.gethostname(),
        'pid': os.getpid(),
        'uid': os.getuid(),
        'verb': verb,
        'cmdline': list(sys.argv),
        'cwd': os.getcwd(),
        'started': datetime.datetime.now(datetime.timezone.utc).isoformat(
            timespec='seconds'),
        'guard_version': __version__,
    }


def read_holder(path):
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return None
    try:
        raw = os.read(fd, 65536)
    finally:
        os.close(fd)
    try:
        data = json.loads(raw.decode('utf-8'))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def describe_holder(holder):
    if not holder:
        return 'holder unknown (metadata not written yet or unreadable)'
    return (
        f"host={holder.get('hostname')} pid={holder.get('pid')} "
        f"since={holder.get('started')} "
        f"cmd={' '.join(holder.get('cmdline') or [])}")


class WorkspaceLock:

    def __init__(self, root):
        self.path = lock_path(root)
        self._fd = None

    @property
    def held(self):
        return self._fd is not None

    def acquire(self, info):
        for _ in range(3):
            fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o664)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as e:
                os.close(fd)
                if e.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
                    raise WorkspaceBusy(read_holder(self.path))
                if e.errno in _UNSUPPORTED_ERRNOS:
                    raise LockUnsupported(os.strerror(e.errno))
                raise
            try:
                same = os.fstat(fd).st_ino == os.stat(self.path).st_ino
            except FileNotFoundError:
                same = False
            if not same:
                os.close(fd)
                continue
            payload = json.dumps(info).encode('utf-8')
            os.pwrite(fd, payload, 0)
            os.ftruncate(fd, len(payload))
            self._fd = fd
            return
        raise RuntimeError('lock file was replaced repeatedly')

    def release(self):
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None


def probe(root):
    path = lock_path(root)
    if not os.path.exists(path):
        return 'absent', None
    holder = read_holder(path)
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return 'absent', None
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except OSError as e:
            if e.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
                return 'busy', holder
            if e.errno in _UNSUPPORTED_ERRNOS:
                return 'unsupported', holder
            raise
        fcntl.flock(fd, fcntl.LOCK_UN)
        return 'free', holder
    finally:
        os.close(fd)
