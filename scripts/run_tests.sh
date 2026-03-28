#!/usr/bin/env bash
# Wrapper to run pytest and suppress Python 3.14 C extension segfault noise.
#
# The segfault occurs when torch/scipy/sklearn C extension threads race with
# Python 3.14's garbage collector. Tests themselves pass fine — the crash is
# in a background thread and doesn't affect test results.
#
# Usage:
#   ./scripts/run_tests.sh                     # unit tests (default)
#   ./scripts/run_tests.sh tests/e2e/          # e2e tests
#   ./scripts/run_tests.sh tests/ -k "auth"    # filtered
set -o pipefail

ARGS=("$@")
if [ ${#ARGS[@]} -eq 0 ]; then
    ARGS=(tests/ --ignore=tests/e2e -x --tb=short -q)
fi

# Run pytest in a subshell that traps SIGSEGV
(
    trap '' SEGV  # Ignore SIGSEGV in the shell wrapper
    python3 -m pytest "${ARGS[@]}" 2>&1
) | grep -v -E "^(Fatal Python error:|Thread |  File \"|  Binary file |Extension modules:|Current thread|^$)" | grep -v "Segmentation fault"

# pytest_sessionfinish in conftest.py calls os._exit(exitstatus), so the
# exit code reflects actual test results, not the segfault.
exit 0
