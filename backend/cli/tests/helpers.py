"""Shared test helpers."""

from __future__ import annotations

import re

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def plain(text: str) -> str:
    """Rendered output with the styling removed.

    Rich styles fragments of a line independently -- an option's leading
    hyphen apart from its name, a number apart from the words around it -- so
    with colour on a phrase like "--version" or "1 additional finding(s)"
    reaches the buffer as several styled runs and a literal substring search
    misses it. CI turns colour on and a local shell usually does not, which is
    exactly the difference these assertions should not depend on.
    """
    return _ANSI.sub("", text)
