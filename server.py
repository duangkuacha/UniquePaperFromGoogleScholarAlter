"""Serve the generated static page locally for a quick preview."""

from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from functools import partial
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PORT = 8001


class CacheFreeHandler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


if __name__ == "__main__":
    handler = partial(CacheFreeHandler, directory=str(ROOT))
    server = ThreadingHTTPServer(("", PORT), handler)
    print(f"Preview: http://localhost:{PORT}/index.html")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
