# colcon-guard
[![CI](https://github.com/vojnar-autonomous/colcon-guard/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/vojnar-autonomous/colcon-guard/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/colcon-guard)](https://pypi.org/project/colcon-guard/)
[![Python](https://img.shields.io/pypi/pyversions/colcon-guard)](https://pypi.org/project/colcon-guard/)
[![License](https://img.shields.io/pypi/l/colcon-guard)](https://github.com/vojnar-autonomous/colcon-guard/blob/main/LICENSE)

Extension for [colcon](https://colcon.readthedocs.io) that guards `colcon build`
and `colcon test` against two failure modes of shared and layered workspaces:

* a workspace being built on top of its own install (or on top of workspaces
  that were built on top of it), which bakes the wrong underlay chain into
  `install/setup.sh`;
* two builds writing into the same workspace at the same time, for example from
  several containers sharing a bind mount.

It hooks into plain `colcon build` / `colcon test`; no wrapper command is needed.

## Installation

colcon-guard is a regular [colcon](https://colcon.readthedocs.io) extension.
It has to be installed into the Python environment that runs `colcon`; colcon
then finds it through its entry points and there is nothing to configure.

It needs Python 3.9 or newer and runs on Linux (tested in CI on Ubuntu with
ROS 2 Humble and Jazzy). Other POSIX systems should work but are untested.
Windows is not supported, the workspace lock uses `fcntl`.

### colcon installed with ROS 2 (apt)

The ROS 2 instructions install colcon with `apt`
(`python3-colcon-common-extensions`). That colcon runs on the system Python, so
install colcon-guard for that interpreter:

    PIP_BREAK_SYSTEM_PACKAGES=1 pip install --user colcon-guard

The variable is needed on Ubuntu 24.04 (ROS 2 Jazzy), where pip otherwise
refuses to install into the system Python, and is ignored by the older pip on
Ubuntu 22.04 (ROS 2 Humble).

In a container image:

    RUN PIP_BREAK_SYSTEM_PACKAGES=1 pip install --no-cache-dir colcon-guard

A virtual environment that contains only colcon-guard is not seen by this
colcon, because colcon loads extensions from its own interpreter.

### colcon installed with pip

If colcon comes from PyPI, for example in a virtual environment or in CI,
install both into the same environment:

    python3 -m venv ~/colcon-venv
    . ~/colcon-venv/bin/activate
    pip install colcon-common-extensions colcon-guard

### Verify and remove

    colcon extensions | grep guard
    colcon build --help | grep -A1 drop-self-underlay
    colcon --log-base /dev/null guard status

To remove it: `pip uninstall colcon-guard`.

Releases before 0.1.0 are alpha.

## Quick start

    colcon build --drop-self-underlay    # never layer this workspace on its own install
    colcon guard status

Without the flag, colcon-guard still takes the workspace lock and warns when the
environment already contains the workspace's own install.

## Checks

| Check | Default | Behaviour |
|---|---|---|
| Workspace lock | always on | Non-blocking `flock` on `<workspace>/.colcon_guard.lock`. A second build/test exits immediately and prints who holds the lock (host, command line, start time). |
| ROS distro consistency | always on | Hard fail when the prefix paths contain a ROS distro other than `ROS_DISTRO` (or `expected_distro` from the local config), or mix several distros. |
| Broken symlinks | always on, warning | Scans the workspace before the build. `--broken-symlink-error` turns the warning into a failure. |
| Self-layering detection | always on, warning | Warns when the workspace's own install (or an overlay of it) is in the environment and suggests `--drop-self-underlay`. |
| `--drop-self-underlay` | opt-in | See below. |
| `--clean-underlay` | opt-in | Resets the environment to the base ROS install. |

Every flag also has a `--no-...` form.

## `--drop-self-underlay`

Before the build the environment is cleaned of the workspace's own install
**and of every workspace built on top of it**. Underlays below the workspace stay.

Whether a prefix is an overlay is decided from the chain baked into its
`install/setup.sh` (transitive), not from its position in `COLCON_PREFIX_PATH`,
because after a chain cycle has been closed the order depends on which
`setup.sh` was sourced last. When a prefix has no readable chain, the order in
`COLCON_PREFIX_PATH` is used as a fallback. If two workspaces chain each other,
the cycle is reported and cut.

Everything that is dropped is printed. Entries under dropped prefixes are removed
from `AMENT_PREFIX_PATH`, `CMAKE_PREFIX_PATH`, `COLCON_PREFIX_PATH`, `PATH`,
`LD_LIBRARY_PATH`, `PYTHONPATH`, `PKG_CONFIG_PATH` and any other multi-entry
variable; unrelated entries are untouched.

Example, workspaces A (base) and B (built over A), shell with B sourced:

```
cd ws_a && colcon build --drop-self-underlay   # A is built over its real underlays only
cd ws_b && colcon build --drop-self-underlay   # B keeps A as its underlay
```

## `--clean-underlay`

Keeps only the base install (`/opt/ros/$ROS_DISTRO`, or `base_prefix` from the
local config) and drops every colcon workspace prefix. Prefixes that are not
colcon workspaces and not under the base install are kept and reported. System
prefixes such as `/usr` are never treated as workspaces.

## Local configuration

Optional `<workspace>/.colcon_guard.toml`, read at build/test time. Command line
flags override it. There are no global defaults on purpose.

```toml
drop_self_underlay = true
clean_underlay = false
broken_symlink_error = false
expected_distro = "jazzy"
base_prefix = ["/opt/ros/jazzy"]
```

## `colcon guard status`

```
colcon --log-base /dev/null guard status [--install-base DIR] [--json]
```

Prints whether a build/test holds the workspace lock and lists the layers in
the current environment (highest priority first), each marked as `this
workspace`, `overlay` (built on top of this workspace) or `underlay`.

Exit code 0: free or never locked, 1: a build/test is running, 3: locking is not
supported on this filesystem. Busy/free is decided by probing the lock, not by
the metadata file, so a record left by a crashed build is reported as stale.
`--json` reports only the lock state.

## Limitations

* The lock relies on `flock`, which works between processes and containers on one
  kernel (bind mounts). It is not reliable on NFS/SMB/9p/FUSE; a warning is
  printed when the workspace is on such a filesystem.
* The workspace is the current directory, as everywhere in colcon. The lock file
  lives there, outside `build/`, `install/` and `log/`, so a clean rebuild
  (`rm -rf build install log`) cannot remove it. It cannot stop such a `rm` from
  breaking a build that is already running.
* `colcon guard status` probes with a shared lock for a moment; a build starting
  in that instant can report the workspace as busy.
* `colcon` creates `build/`, `install/` and the log directory before the guard
  runs, so a refused build leaves those (empty) directories behind.
* Overlays are recognised through `COLCON_PREFIX_PATH`. A workspace sourced by
  other means is not detected as an overlay.
* Only the `sh` chain (`setup.sh`) is inspected; other shells are generated from
  the same chain.
* Broken symlink scan does not descend into packages and skips `build`, `install`,
  `log`, `.git` and directories with `COLCON_IGNORE`.

## How it hooks in

A `colcon_core.package_selection` extension: `add_arguments()` adds the flags to
the verbs that use package selection, `check_parameters()` runs after argument
parsing and before any job is created, and is allowed to raise `SystemExit`.
Environment changes are made in `os.environ` of the colcon process, which the
per-package command environment (`env -0` after sourcing dependencies) inherits.
The hook acts only for the `build` and `test` verbs. `colcon guard status` is a
regular `colcon_core.verb` extension.

## Testing

Every push and pull request runs the full test suite in
[GitHub Actions](https://github.com/vojnar-autonomous/colcon-guard/actions/workflows/ci.yml):

- Python 3.9 to 3.13 with colcon from PyPI;
- ROS 2 Humble and Jazzy containers with colcon from `apt`, including tests
  against a real ROS installation;
- a packaging job that builds the sdist and wheel, checks them with `twine` and
  installs the wheel into a clean virtual environment.

To run the tests locally:

    pip install -e '.[test]'
    pytest                      # unit tests + end-to-end tests
    pytest -m "not e2e"         # unit tests only

`tests/rig/` contains two workspaces of empty `ament_python` packages: `ws_a`
(`a_core`, `a_app` depending on `a_core`) and `ws_b` (`b_app` depending on
`a_app`, plus an override of `a_core`). The end-to-end tests copy the rig to a
temporary directory and run the real `colcon` on it: layering, cycle repair in
both `setup.sh` orderings, the `test` verb, lock contention, lock release after
`kill -9`, the distro guard, symlinks and local configuration. Tests marked
`ros` run only where a ROS 2 installation is found.

## License

Apache-2.0
