"""Actions may only come from CNV's own pages."""

from __future__ import annotations

import pytest

from app.web.security import is_same_origin


@pytest.mark.parametrize(
    ("method", "origin", "referer", "allowed"),
    [
        ("GET", "https://evil.example", None, True),  # reading is always fine
        ("POST", "http://127.0.0.1:8000", None, True),  # CNV's own page
        ("POST", None, "http://127.0.0.1:8000/in-uscita", True),
        ("POST", None, None, True),  # no browser involved (script on this PC)
        ("POST", "https://evil.example", None, False),
        ("POST", None, "https://evil.example/page", False),
        ("POST", "http://127.0.0.1:9999", None, False),  # another local app
        ("POST", "null", None, False),
    ],
)
def test_is_same_origin(method, origin, referer, allowed):
    assert is_same_origin(method, "127.0.0.1:8000", origin, referer) is allowed
