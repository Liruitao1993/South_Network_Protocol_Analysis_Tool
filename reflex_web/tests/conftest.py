"""pytest fixtures for Reflex browser automation tests"""
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest


BASE_DIR = Path(__file__).resolve().parent.parent


def _find_free_port(start=8096):
    """Find a free TCP port starting from start."""
    port = start
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("", port))
                return port
            except OSError:
                port += 1


def _wait_for_server(url: str, timeout: int = 300):
    """Wait until the given URL returns HTTP 200."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"Server did not start at {url} within {timeout}s")


@pytest.fixture(scope="session")
def reflex_app():
    """Start Reflex dev server and yield the frontend URL."""
    frontend_port = _find_free_port()
    backend_port = _find_free_port(frontend_port + 1)
    app_url = f"http://localhost:{frontend_port}"

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    log_path = BASE_DIR / ".tests" / "reflex_server.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(log_path, "w", encoding="utf-8")

    proc = subprocess.Popen(
        [
            sys.executable, "-m", "reflex", "run",
            "--frontend-port", str(frontend_port),
            "--backend-port", str(backend_port),
        ],
        cwd=str(BASE_DIR),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        _wait_for_server(app_url, timeout=300)
        yield app_url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log_file.close()
