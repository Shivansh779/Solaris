"""Solaris launcher — starts the local web interface.

    python chatbot.py              start the web app (default)
    python chatbot.py --terminal   run the original terminal interface
    python chatbot.py --port 7900  use a different port

The web app binds to 127.0.0.1 only: it is your machine's interface, not a website.
"""

import os
import runpy
import subprocess
import sys
import threading
import webbrowser

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PORT = 7900
PORT_RANGE = 10

BANNER = """
────────────────────────────────────────────────────────────
                            Solaris
────────────────────────────────────────────────────────────

  Web interface:  {url}
  Stop with:      Ctrl+C

  First run (or missing keys) opens the setup wizard automatically.
────────────────────────────────────────────────────────────
"""


def ensure_flask():
    """The launcher itself needs Flask before anything else can start."""
    try:
        import flask  # noqa: F401
        return
    except ImportError:
        print("Flask is not installed — installing it now (one time).\n")
        subprocess.run([sys.executable, "-m", "pip", "install", "flask"], check=True)


def pick_port(start=DEFAULT_PORT):
    """First free port in [start, start + PORT_RANGE)."""
    import socket

    for port in range(start, start + PORT_RANGE):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port between {start} and {start + PORT_RANGE - 1}.")


def launch_web(port=None):
    ensure_flask()
    sys.path.insert(0, BASE_DIR)
    os.chdir(BASE_DIR)

    # Import the app *before* announcing a URL. The first launch loads the model
    # SDKs and can take a minute or two; nothing is listening during that time, so
    # opening the browser early only produces a "can't connect" page.
    print("Solaris is starting up — loading models, keys and databases…")
    print("(The first launch after a restart can take a minute or two.)\n", flush=True)

    from web.app import app

    port = port or pick_port()
    url = f"http://127.0.0.1:{port}"
    print(BANNER.format(url=url), flush=True)

    threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    app.run(host="127.0.0.1", port=port, threaded=True, use_reloader=False)


def launch_terminal():
    sys.path.insert(0, BASE_DIR)
    os.chdir(BASE_DIR)
    runpy.run_path(os.path.join(BASE_DIR, "terminal.py"), run_name="__main__")


def main(argv):
    if "--terminal" in argv:
        launch_terminal()
        return

    port = None
    if "--port" in argv:
        try:
            port = int(argv[argv.index("--port") + 1])
        except (IndexError, ValueError):
            print("Usage: --port <number>")
            return

    launch_web(port)


if __name__ == "__main__":
    main(sys.argv[1:])
