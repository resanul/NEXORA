from __future__ import annotations

import threading
import time
import webbrowser

import uvicorn

from .web import app


def start_web(port: int = 8080) -> None:
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def launch(port: int = 8080) -> None:
    """Launch a local browser UI. PyWebView integration is optional for packaged builds."""
    thread = threading.Thread(target=start_web, args=(port,), daemon=True)
    thread.start()
    time.sleep(0.8)
    webbrowser.open(f"http://127.0.0.1:{port}")
    thread.join()


if __name__ == "__main__":
    launch()
