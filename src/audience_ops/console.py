"""Loopback, read-only console. Its database role and receiver token cannot write."""
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .client import Client, Unknown
from .db import connect
from .oracle import check


def handler(config):
    client = Client(config["url"], config["read_token"])

    class Console(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, status, body, content_type="application/json"):
            raw = body if isinstance(body, bytes) else json.dumps(body, default=str).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(raw)

        def do_POST(self):
            self.reply(405, {"error": "read_only_console"})

        do_PUT = do_POST
        do_DELETE = do_POST
        do_PATCH = do_POST

        def do_GET(self):
            parsed = urlparse(self.path)
            if urlparse("http://" + self.headers.get("Host", "")).hostname not in {"127.0.0.1", "localhost", "console"}:
                return self.reply(403, {"error": "local_host_required"})
            origin = self.headers.get("Origin")
            if origin and urlparse(origin).hostname not in {"127.0.0.1", "localhost"}:
                return self.reply(403, {"error": "cross_origin_denied"})
            assets = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                      "/style.css": ("style.css", "text/css; charset=utf-8")}
            if parsed.path in assets:
                name, content_type = assets[parsed.path]
                return self.reply(200, (Path(__file__).parent / "web" / name).read_bytes(), content_type)
            if parsed.path == "/api/config":
                return self.reply(200, {"brands": config["brands"], "read_only": True, "synthetic": True})
            if parsed.path not in {"/api/state", "/api/receipt", "/health"}:
                return self.reply(404, {"error": "unknown_route"})
            try:
                if parsed.path == "/health":
                    with connect(config["dsn"]) as c:
                        c.execute("SELECT 1")
                    return self.reply(200, {"ready": True, "read_only": True})
                q = parse_qs(parsed.query)
                if len(q.get("brand", [])) != 1 or q["brand"][0] not in config["brands"]:
                    return self.reply(403, {"error": "brand_scope_denied"})
                brand = q["brand"][0]
                with connect(config["dsn"]) as c:
                    if parsed.path == "/api/receipt":
                        effect = q.get("effect", [""])[0]
                        if not re.fullmatch(r"[a-f0-9]{64}", effect):
                            return self.reply(400, {"error": "invalid_effect"})
                        row = c.execute("SELECT payload FROM intents WHERE id=%s AND brand=%s", (effect, brand)).fetchone()
                        if not row:
                            return self.reply(404, {"error": "unknown_scoped_intent"})
                        receipt = client.readback(row["payload"])
                        return self.reply(200, {"status": "historical_receipt_verified" if receipt else "confirmed_absent",
                                                "receipt": receipt, "new_action_authorized": False})
                    state = {"synthetic": True, "read_only": True, "brand": brand,
                             "brand_clock": c.execute("SELECT clock FROM brands WHERE brand=%s", (brand,)).fetchone()["clock"]}
                    # Closed table list; brand is always a bound parameter. No arbitrary query API.
                    for table in ["subjects", "inbox", "publications", "permissions", "intents", "audit", "reconciliations", "activation_eligibility"]:
                        state[table] = c.execute("SELECT * FROM " + table + " WHERE brand=%s", (brand,)).fetchall()
                    active = c.execute("SELECT publication FROM active WHERE brand=%s", (brand,)).fetchone()
                    state["active"] = active["publication"] if active else None
                state["receiver"] = client.membership(brand)
                state["oracle"] = check(config["dsn"], brand)
                return self.reply(200, state)
            except Unknown:
                return self.reply(503, {"error": "independent_destination_readback_unknown"})
            except Exception:
                return self.reply(503, {"error": "read_only_validation_unavailable"})

    return Console


def serve(config, host="127.0.0.1", port=0):
    return ThreadingHTTPServer((host, port), handler(config))
