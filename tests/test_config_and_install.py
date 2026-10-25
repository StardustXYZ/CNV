"""Tests for settings parsing and the run.bat install check."""

from __future__ import annotations

from datetime import time

import pytest
import yaml

from app.config import _parse_time
from app.install_check import is_up_to_date, main, mark_installed


@pytest.mark.parametrize(
    ("yaml_line", "expected"),
    [
        ('auto_sync_time: "08:00"', time(8, 0)),
        ("auto_sync_time: 08:00", time(8, 0)),
        ("auto_sync_time: 20:30", time(20, 30)),  # YAML reads it as the number 1230
        ("auto_sync_time: 8:00", time(8, 0)),  # ...and this as 480
    ],
)
def test_auto_sync_time_with_or_without_quotes(yaml_line, expected):
    value = yaml.safe_load(yaml_line)["auto_sync_time"]
    assert _parse_time(value) == expected


@pytest.mark.parametrize("value", ["alle otto", "25:00", "", None])
def test_invalid_auto_sync_time_gives_a_clear_error(value):
    with pytest.raises(ValueError, match='Usa il formato "HH:MM"'):
        _parse_time(value)


def test_install_check(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    marker = tmp_path / ".venv" / "cnv-installed.txt"
    pyproject.write_text('[project]\nname = "cnv"\n')

    assert not is_up_to_date(pyproject, marker)  # never installed
    mark_installed(pyproject, marker)
    assert is_up_to_date(pyproject, marker)

    pyproject.write_text('[project]\nname = "cnv"\ndependencies = ["nuova"]\n')
    assert not is_up_to_date(pyproject, marker)  # dependencies changed: install again


def test_install_check_command_exit_codes(monkeypatch, tmp_path):
    import app.install_check as install_check

    monkeypatch.setattr(install_check, "PYPROJECT", tmp_path / "pyproject.toml")
    monkeypatch.setattr(install_check, "MARKER", tmp_path / "marker.txt")
    (tmp_path / "pyproject.toml").write_text("x")

    assert main(["prog", "check"]) == 1
    assert main(["prog", "mark"]) == 0
    assert main(["prog", "check"]) == 0
