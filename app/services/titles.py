"""Title normalization shared by sync and TMDB matching."""

from __future__ import annotations

import re
import unicodedata


def normalize_title(raw: str) -> str:
    """Lowercase, strip accents and punctuation so titles match across sources."""
    t = raw.strip().lower()
    t = unicodedata.normalize("NFKD", t)
    # Remove combining diacritical marks and non-word chars (except spaces)
    t = re.sub(r"[^\w\s]", "", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()
