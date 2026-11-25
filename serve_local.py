#!/usr/bin/env python3
"""Serve the recovered Kaori storefront on http://127.0.0.1:8000."""

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import os
import posixpath
from urllib.parse import urlsplit
from urllib.parse import unquote

from tools.local_site import prepare_html

PROJECT_ROOT = Path(__file__).resolve().parent
ROOT = PROJECT_ROOT / "site"


class KaoriHandler(SimpleHTTPRequestHandler):
    redirects = {
        "/products/deodorizing-persimmon-soap1": "/products/deodorizing-persimmon-soap",
        "/apps/parcelpanel": "/?feature=order-tracking",
        "/customer_authentication/redirect": "/?feature=customer-account",
        "/a/loop_subscriptions/customer": "/?feature=subscription-management",
        "/cart": "/?feature=checkout",
    }
    font_fallbacks = {
        "/cdn/fonts/poppins/poppins_i4.846ad1e22474f856bd6b81ba4585a60799a9f5d2.woff2":
            "cdn/fonts/poppins/poppins_n4.0ba78fa5af9b0e1a374041b3ceaadf0a43b41362.woff2",
        "/cdn/fonts/poppins/poppins_i7.42fd71da11e9d101e1e6c7932199f925f9eea42d.woff2":
            "cdn/fonts/poppins/poppins_n7.56758dcf284489feb014a026f3727f2f20a54626.woff2",
        "/cdn/fonts/inter/inter_n4.b2a3f24c19b4de56e8871f609e73ca7f6d2e2bb9.woff2":
            "cdn/fonts/poppins/poppins_n4.0ba78fa5af9b0e1a374041b3ceaadf0a43b41362.woff2",
        "/cdn/fonts/ebgaramond/ebgaramond_n7.d08d282a03b4a9cde493a0a5c170eb41fd0a48a6.woff2":
            "cdn/fonts/poppins/poppins_n7.56758dcf284489feb014a026f3727f2f20a54626.woff2",
    }

    def _send_bytes(self, payload, content_type, status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _html_file(self, request_path):
        clean = posixpath.normpath(unquote(request_path)).lstrip("/")
        target = (ROOT / clean).resolve()
        try:
            target.relative_to(ROOT.resolve())
        except ValueError:
            return None
        if target.is_dir():
            target = target / "index.html"
        elif not target.suffix:
            target = target / "index.html"
        return target if target.is_file() and target.suffix.lower() == ".html" else None

    def do_GET(self):
        override_files = {
            "/local-mode.js": "local-mode.js",
            "/storefront-config.js": "storefront-config.js",
        }
        request_path = urlsplit(self.path).path
        redirect = self.redirects.get(request_path)
        if redirect:
            self.send_response(302)
            self.send_header("Location", redirect)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if request_path in override_files:
            override = PROJECT_ROOT / "overrides" / override_files[request_path]
            payload = override.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)
            return
        if request_path in self.font_fallbacks:
            payload = (ROOT / self.font_fallbacks[request_path]).read_bytes()
            self._send_bytes(payload, "font/woff2")
            return
        if request_path == "/cart.js":
            payload = json.dumps({"items": [], "item_count": 0, "total_price": 0}).encode()
            self._send_bytes(payload, "application/json; charset=utf-8")
            return
        if request_path in ("/browsing_context_suggestions.json", "/apps/load/v1/r"):
            self._send_bytes(b"{}", "application/json; charset=utf-8")
            return
        if request_path.startswith("/search/suggest"):
            self._send_bytes(b'{"resources":{"results":{}}}', "application/json; charset=utf-8")
            return
        html_file = self._html_file(request_path)
        if html_file:
            payload = prepare_html(html_file.read_text(encoding="utf-8", errors="replace")).encode("utf-8")
            self._send_bytes(payload, "text/html; charset=utf-8")
            return
        super().do_GET()

    def do_POST(self):
        request_path = urlsplit(self.path).path
        if request_path.startswith(("/.well-known/shopify/", "/api/collect")):
            self._send_bytes(b"", "text/plain; charset=utf-8", status=204)
            return
        if request_path.startswith(("/cart", "/contact", "/localization", "/apps/load/", "/api/unstable/")):
            payload = json.dumps({"ok": False, "local_preview": True}).encode()
            self._send_bytes(payload, "application/json; charset=utf-8")
            return
        self.send_error(404)


os.chdir(ROOT)
print("Kaori local: http://127.0.0.1:8000")
print("Pressione Ctrl+C para parar.")
ThreadingHTTPServer(("127.0.0.1", 8000), KaoriHandler).serve_forever()
