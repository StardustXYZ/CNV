"""Protection against actions triggered by other websites (cross-site requests).

CNV runs on 127.0.0.1 without login: any page open in the browser could otherwise
send a form to http://127.0.0.1:8000/sync or change votes. Browsers say where a
request comes from in the Origin (or Referer) header, so actions are accepted only
when they come from CNV's own pages.
"""

from __future__ import annotations

from urllib.parse import urlsplit

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def is_same_origin(method: str, host: str | None, origin: str | None, referer: str | None) -> bool:
    """True if the request may proceed.

    Reading pages is always allowed. Actions (POST, ...) are refused when the browser
    says they come from another site. Without Origin and Referer (e.g. a script on
    this computer) the request is allowed: browsers always send one of them.
    """
    if method.upper() in SAFE_METHODS:
        return True
    source = origin or referer
    if not source:
        return True
    if source == "null":  # sandboxed frames and some privacy redirects
        return False
    return bool(host) and urlsplit(source).netloc.lower() == host.lower()
