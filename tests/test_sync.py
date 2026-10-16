"""Tests for the sync service."""

from __future__ import annotations

from app.services.sync import normalize_title


def test_normalize_basic():
    assert normalize_title("  Il Gladiatore II  ") == "il gladiatore ii"


def test_normalize_accents():
    assert normalize_title("Città di Dio") == "citta di dio"


def test_normalize_punctuation():
    assert normalize_title("Napoli – New York") == "napoli new york"


def test_normalize_apostrophe():
    # Apostrophe and similar chars are stripped
    result = normalize_title("L'Amore è Bello")
    assert "lamore" in result
    assert "bello" in result

