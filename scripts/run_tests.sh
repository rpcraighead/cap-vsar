#!/usr/bin/env bash
# The one command that runs every test suite in this repository (O2-2).
#
#   python3.12 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
#   scripts/run_tests.sh                # everything that needs neither X-Plane nor Air Manager
#   scripts/run_tests.sh --pytest-only  # just the four pytest suites
#   scripts/run_tests.sh --no-shim      # CI
#
# This is scripts/ci_local.sh under the name people look for. See that file for
# what runs and why the suites are separate processes.
exec "$(dirname "$0")/ci_local.sh" "$@"
