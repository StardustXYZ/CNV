"""Start CNV and open it in the browser (used by run.bat and the desktop shortcut).

If CNV is already running, it only opens the browser; otherwise it starts the server
and opens the browser as soon as the server answers.

Usage:
    python -m app.launcher
"""

from __future__ import annotations

import socket
import threading
import time
import webbrowser

HOST = "127.0.0.1"
PORT = 8000
URL = f"http://{HOST}:{PORT}"


def is_running(host: str = HOST, port: int = PORT) -> bool:
    """True if something already accepts connections on the CNV port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def _open_when_ready(timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if is_running():
            webbrowser.open(URL)
            return
        time.sleep(0.3)


def main() -> None:
    if is_running():
        print(f"CNV è già acceso: apro {URL}")
        webbrowser.open(URL)
        return

    import uvicorn

    threading.Thread(target=_open_when_ready, daemon=True).start()
    uvicorn.run("app.main:app", host=HOST, port=PORT)


if __name__ == "__main__":
    main()
