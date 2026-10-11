#!/usr/bin/env python3
"""
start.py - one-command launcher for Research Paper Intelligence.

Run it from the project folder (for example in your IDE's terminal):

    python start.py            (Windows may need:  py start.py)
    python3 start.py           (macOS / Linux)

What it does:
  1. Checks that Docker is installed and running, and that your .env file
     exists and has an OpenAlex API key (creates .env from .env.example if
     it's missing).
  2. Builds and starts the app with `docker compose up --build`, keeping
     the live logs in this terminal.
  3. Waits until the app is actually ready, then opens it in your browser.
  4. Press Ctrl+C to stop everything. Your saved papers are kept.

Options:
    --no-browser   don't open the browser automatically
    --no-build     skip the image rebuild (faster when nothing changed)
    --airflow      also start the optional Airflow scheduler (port 8080)
    --port N       the host port the app is published on (default 8501)

Uses only the Python standard library, so no `pip install` is needed.
"""
from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
ENV_FILE = PROJECT_DIR / ".env"
ENV_EXAMPLE = PROJECT_DIR / ".env.example"
PLACEHOLDER_KEYS = {"", "your_api_key", "your-api-key", "your_key_here", "changeme", "change_me"}
READY_TIMEOUT_SECONDS = 15 * 60  # first build can take a while on slow connections


# ----------------------------------------------------------------------
# Small terminal helpers
# ----------------------------------------------------------------------
def _supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.name == "nt":
        os.system("")  # enables ANSI escape codes on Windows 10+ consoles
    return sys.stdout.isatty()


_COLOR = _supports_color()


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOR else text


def info(msg: str) -> None:
    print(_c("36", "[start] ") + msg, flush=True)


def ok(msg: str) -> None:
    print(_c("32", "[start] ") + msg, flush=True)


def warn(msg: str) -> None:
    print(_c("33", "[start] WARNING: ") + msg, flush=True)


def fail(msg: str) -> None:
    print(_c("31", "[start] ERROR: ") + msg, flush=True)
    sys.exit(1)


# ----------------------------------------------------------------------
# Pre-flight checks
# ----------------------------------------------------------------------
def find_compose() -> list[str]:
    """Returns the docker compose command for this machine."""
    if shutil.which("docker"):
        probe = subprocess.run(["docker", "compose", "version"], capture_output=True, text=True)
        if probe.returncode == 0:
            return ["docker", "compose"]
    if shutil.which("docker-compose"):
        return ["docker-compose"]
    if not shutil.which("docker"):
        fail("Docker is not installed. Install Docker Desktop: https://www.docker.com/products/docker-desktop/")
    fail("Docker Compose is not available. Update Docker Desktop to a recent version.")
    return []  # unreachable


def check_docker_running() -> None:
    result = subprocess.run(["docker", "info"], capture_output=True, text=True)
    if result.returncode != 0:
        fail("Docker is installed but not running. Start Docker Desktop, wait until it says "
             "it's running, then run this script again.")


def read_env_key(path: Path, name: str) -> str | None:
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line.startswith("export "):
                line = line[len("export "):].strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == name:
                value = value.split(" #", 1)[0].strip().strip('"').strip("'").strip()
                return value
    except OSError:
        return None
    return None


def check_env_file() -> None:
    if not ENV_FILE.exists():
        if not ENV_EXAMPLE.exists():
            fail("No .env or .env.example found. Run this script from the project folder.")
        shutil.copyfile(ENV_EXAMPLE, ENV_FILE)
        warn("No .env file found, so one was created from .env.example.")

    key = read_env_key(ENV_FILE, "OPENALEX_API_KEY")
    if not key or key.lower() in PLACEHOLDER_KEYS:
        warn("OPENALEX_API_KEY is not set in .env, so searches will use OpenAlex's small shared")
        warn("free quota and may fail. Get a free key at https://openalex.org/settings/api,")
        warn("then add it to .env like this:  OPENALEX_API_KEY=your_key")
        warn("(No restart needed: the app reads the key from .env on every search.)")
    else:
        ok(f"OpenAlex API key found in .env (ends with ...{key[-4:]}).")


# ----------------------------------------------------------------------
# Readiness watcher
# ----------------------------------------------------------------------
def wait_until_ready(url: str, proc: subprocess.Popen, open_browser: bool, stop: threading.Event) -> None:
    health = url.rstrip("/") + "/_stcore/health"
    deadline = time.monotonic() + READY_TIMEOUT_SECONDS
    while not stop.is_set() and time.monotonic() < deadline:
        if proc.poll() is not None:
            return  # docker compose exited (error or Ctrl+C)
        try:
            with urllib.request.urlopen(health, timeout=3) as resp:
                if resp.status == 200:
                    break
        except (urllib.error.URLError, ConnectionError, OSError):
            pass
        stop.wait(2)
    else:
        if not stop.is_set() and proc.poll() is None:
            warn(f"The app didn't become ready within {READY_TIMEOUT_SECONDS // 60} minutes. "
                 "Check the logs above.")
        return

    line = "=" * 62
    print("", flush=True)
    print(_c("32", line), flush=True)
    print(_c("32", "  Research Paper Intelligence is ready!"), flush=True)
    print(_c("32", f"  Open:  {url}"), flush=True)
    print(_c("32", "  Stop:  press Ctrl+C in this terminal"), flush=True)
    print(_c("32", line), flush=True)
    print("", flush=True)
    if open_browser:
        try:
            webbrowser.open(url, new=2)
        except Exception:  # noqa: BLE001 - a missing browser must not stop the app
            pass


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="Start Research Paper Intelligence with Docker.")
    parser.add_argument("--no-browser", action="store_true", help="don't open the browser automatically")
    parser.add_argument("--no-build", action="store_true", help="skip rebuilding the Docker image")
    parser.add_argument("--airflow", action="store_true", help="also start the optional Airflow scheduler")
    parser.add_argument("--port", type=int, default=8501, help="host port the app is published on (default 8501)")
    args = parser.parse_args()

    os.chdir(PROJECT_DIR)
    compose = find_compose()
    check_docker_running()
    check_env_file()

    profile_args = ["--profile", "airflow"] if args.airflow else []
    up_cmd = compose + profile_args + ["up"] + ([] if args.no_build else ["--build"])
    url = f"http://localhost:{args.port}"

    info("Starting: " + " ".join(up_cmd))
    info("The first run builds the image and can take several minutes. Live logs follow.")
    info("Press Ctrl+C at any time to stop.")
    print("", flush=True)

    proc = subprocess.Popen(up_cmd, cwd=PROJECT_DIR)
    stop = threading.Event()
    watcher = threading.Thread(
        target=wait_until_ready, args=(url, proc, not args.no_browser, stop), daemon=True
    )
    watcher.start()

    try:
        return_code = proc.wait()
    except KeyboardInterrupt:
        # Ctrl+C reaches docker compose too; it stops the containers gracefully.
        stop.set()
        print("", flush=True)
        info("Stopping... (press Ctrl+C again to force)")
        try:
            return_code = proc.wait(timeout=60)
        except (KeyboardInterrupt, subprocess.TimeoutExpired):
            if os.name != "nt":
                proc.send_signal(signal.SIGINT)
            try:
                proc.wait(timeout=10)
            except (KeyboardInterrupt, subprocess.TimeoutExpired):
                proc.kill()
        # Make sure nothing is left running in the background.
        subprocess.run(compose + profile_args + ["stop"], cwd=PROJECT_DIR,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ok("Stopped. Your data is kept. Run `python start.py` to start again.")
        return 0
    finally:
        stop.set()

    if return_code != 0:
        warn(f"docker compose exited with code {return_code}. Scroll up for the error.")
    return return_code


if __name__ == "__main__":
    sys.exit(main())
