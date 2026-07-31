"""A tiny in-process HTTP site used by the integration and e2e suites.

The mocked unit suite never exercises the real dependency stack, so lockfile
bumps (requests, aiohttp, bs4/soupsieve, playwright, and the mcp transport
chain) used to merge on faith. These tests need a real server to talk to —
but hitting the public internet from CI is flaky and rude, so we serve a
deterministic fixture site on a loopback ephemeral port instead.

Lives outside conftest.py so both tests/integration and tests/e2e can share
it without pushing niche fixtures into the top-level conftest.
"""

import http.server
import json
import threading
from contextlib import contextmanager

FIXTURE_PRODUCTS = [
    {"id": 1, "name": "Widget", "price": 9.99},
    {"id": 2, "name": "Gadget", "price": 19.99},
    {"id": 3, "name": "Doohickey", "price": 4.99},
]

FIXTURE_HTML = """<!doctype html>
<html>
  <head><title>Fixture Store</title></head>
  <body>
    <h1>Products</h1>
    <div id="catalog">
      <div class="product"><span class="name">Widget</span><span class="price">9.99</span></div>
      <div class="product"><span class="name">Gadget</span><span class="price">19.99</span></div>
      <div class="product"><span class="name">Doohickey</span><span class="price">4.99</span></div>
    </div>
  </body>
</html>
"""


class _FixtureHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - http.server API name
        if self.path == "/api/products":
            body = json.dumps({"products": FIXTURE_PRODUCTS}).encode()
            content_type = "application/json"
        elif self.path == "/page":
            body = FIXTURE_HTML.encode()
            content_type = "text/html; charset=utf-8"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):  # noqa: A002 - http.server API name
        pass  # keep pytest output clean


@contextmanager
def local_site():
    """Serve the fixture site on 127.0.0.1:<ephemeral>, yielding its base URL."""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _FixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
