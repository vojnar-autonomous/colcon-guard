# Contributing

Bug reports and pull requests are welcome.

## Development

    pip install -e '.[test]'
    pytest                  # unit and end-to-end tests
    pytest -m "not e2e"     # unit tests only

The end-to-end tests run the real `colcon` on the workspaces in `tests/rig`.
Tests marked `ros` run only where a ROS 2 installation is found.

## Pull requests

- Keep changes focused and add or update tests.
- CI must pass (Python 3.9 and 3.12, ROS Humble and Jazzy).
- By contributing you agree that your contribution is licensed under the
  Apache License 2.0 (see section 5 of the license).
