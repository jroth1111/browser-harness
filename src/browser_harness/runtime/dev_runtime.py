"""Dev runtime — arbitrary Python execution over browser helpers.

Explicitly unsafe: preserves the current browser-harness -c behavior.
No no-bypass claim is made for this runtime.
"""
from __future__ import annotations

from ..helpers import *  # noqa: F401,F403
from ..agent_helpers import *  # noqa: F401,F403  agent-editable namespace
from ..response import Response


def run_dev(code: str) -> None:
    """Execute arbitrary Python in the browser-harness namespace.

    This is the legacy -c / stdin path. It provides no authority guarantees.
    """
    exec(code, globals())  # noqa: S102
