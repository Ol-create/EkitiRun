"""Bib numbers as people type them. Owner: Lead."""

import re

_TYPED_BIB = re.compile(r"^([A-Z])\s*0*(\d{1,4})$")


def normalize_bib(raw: str) -> str:
    """'h42', 'H 0042' and 'H0042' all become 'H0042'. Anything else is just upper-cased."""
    text = raw.strip().upper()
    match = _TYPED_BIB.match(text)
    return f"{match[1]}{int(match[2]):04d}" if match else text
