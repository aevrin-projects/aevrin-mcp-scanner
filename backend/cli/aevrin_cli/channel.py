"""Which surface this CLI process is acting as.

`InvocationChannel` records who asked for a scan. It never varies the result -
the same server scanned from a laptop and from a CI job produces the same
findings, the same grade and the same policy - so this is provenance, not
policy, and reading it from the environment is safe in a way that reading a
security decision from the environment would not be.

Deliberately not a `--channel` flag. Every CI system already announces itself,
so a flag would add a way to be wrong (a workflow that forgets it reports
`cli`, and nobody notices because nothing breaks) in exchange for nothing. The
one caller that cannot be detected - the MCP server surface - passes its
channel explicitly instead.
"""

from __future__ import annotations

import os

from aevrin_scanner_core.models import InvocationChannel

# `CI` is set by GitHub Actions, GitLab CI, CircleCI, Travis, Buildkite,
# Jenkins' modern images and Netlify. Checking the generic variable rather
# than a list of vendor-specific ones means a CI system nobody here has heard
# of still reports itself correctly.
_CI_VARS = ("CI", "CONTINUOUS_INTEGRATION", "BUILD_NUMBER", "GITHUB_ACTIONS")

# "false" appears because GitHub Actions sets CI=true but some runners and
# local shells export CI=false to mean "not CI"; treating that as CI would be
# worse than not checking at all.
_FALSEY = {"", "0", "false", "no", "off"}


def running_in_ci() -> bool:
    return any(os.environ.get(v, "").strip().lower() not in _FALSEY for v in _CI_VARS)


def current_channel() -> InvocationChannel:
    """The channel this process should record on the scans it produces."""
    return InvocationChannel.CI if running_in_ci() else InvocationChannel.CLI
