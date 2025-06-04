"""Helpers to start the MCP server inside Google Colab/IPython notebooks."""

import itertools
import threading
import time

from server import run_servers


def launch_in_colab(api_port: int = 8000, ui_port: int | None = None) -> None:
    """Launch servers in background threads and keep cell alive."""

    def _run():
        run_servers(api_port=api_port, ui_port=ui_port)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    # keep cell alive
    for _ in itertools.count():
        time.sleep(3600)

