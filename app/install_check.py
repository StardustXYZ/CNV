"""Tell run.bat whether the dependencies must be (re)installed.

The install needs internet and takes several seconds, so it runs only the first time
and after pyproject.toml changes. Standard library only: it runs before the install.

Usage:
    python -m app.install_check check   # exit code 0 = up to date, 1 = install needed
    python -m app.install_check mark    # record that the install succeeded
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT_DIR / "pyproject.toml"
MARKER = ROOT_DIR / ".venv" / "cnv-installed.txt"


def _fingerprint(pyproject: Path) -> str:
    return hashlib.sha256(pyproject.read_bytes()).hexdigest()


def is_up_to_date(pyproject: Path | None = None, marker: Path | None = None) -> bool:
    pyproject, marker = pyproject or PYPROJECT, marker or MARKER
    return marker.exists() and marker.read_text(encoding="utf-8").strip() == _fingerprint(pyproject)


def mark_installed(pyproject: Path | None = None, marker: Path | None = None) -> None:
    pyproject, marker = pyproject or PYPROJECT, marker or MARKER
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(_fingerprint(pyproject), encoding="utf-8")


def main(argv: list[str]) -> int:
    command = argv[1] if len(argv) > 1 else "check"
    if command == "mark":
        mark_installed()
        return 0
    return 0 if is_up_to_date() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
