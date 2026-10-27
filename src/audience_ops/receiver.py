"""Finite local HTTP membership contract with separate durable receipt/record storage."""
import hmac
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from psycopg.types.json import Jsonb

from temporal_audiences.contracts import Refused, digest, identifier, integer

from .db import connect, lock

FIELDS = {"contract", "brand", "person", "segment", "channel", "purpose", "seq", "desired", "authority", "effect_id"}


def validate(payload):
    if not isinstance(payload, dict) or set(payload) != FIELDS or type(payload["contract"]) is not int or payload["contract"] != 1:
        raise Refused("invalid_effect_shape")
    for field in ("brand", "person"):
        identifier(payload[field])
    integer(payload["seq"], 1)
    if (payload["segment"] not in {"engaged_trial", "quiet_trial"} or payload["channel"] != "email"
            or payload["purpose"] != "trial_help" or type(payload["desired"]) is not bool):
        raise Refused("unsupported_effect")
    if payload["effect_id"] != digest({k: v for k, v in payload.items() if k != "effect_id"}):
        raise Refused("effect_identity_conflict")


def handler(config):
    class Receiver(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Never log authorization headers or private connection exceptions.

        def reply(self, status, body):
            raw = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def authorized(self, brand, role):
            supplied = self.headers.get("Authorization", "")
            return brand in config["brands"] and hmac.compare_digest(supplied, "Bearer " + config[role + "_token"])

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                return self.reply(200, {"service": "synthetic-receiver", "contract": 1})
            q = parse_qs(parsed.query)
            brand, person = q.get("brand", [""])[0], q.get("person", [""])[0]
            if not self.authorized(brand, "read"):
                return self.reply(403, {"error": "scope_or_role_denied"})
            with connect(config["dsn"]) as c:
                fault = c.execute("SELECT * FROM faults WHERE brand=%s AND person=%s", (brand, person)).fetchone()
                if fault and fault["mode"] == "unknown":
                    return self.reply(503, {"error": "readback_unknown"})
                if parsed.path == "/membership":
                    return self.reply(200, {"contract": 1, "brand": brand, "rows": c.execute(
                        "SELECT * FROM membership WHERE brand=%s ORDER BY person,segment", (brand,)).fetchall()})
                parts = parsed.path.strip("/").split("/")
                if len(parts) != 2 or parts[0] not in {"receipts", "records"}:
                    return self.reply(404, {"error": "unknown_route"})
                effect = c.execute("SELECT * FROM effects WHERE id=%s AND brand=%s", (parts[1], brand)).fetchone()
                if not effect:
                    return self.reply(404, {"contract": 1, "status": "absent", "effect_id": parts[1], "brand": brand})
                if parts[0] == "receipts":
                    body = effect["receipt"]
                    if fault and fault["mode"] == "bad_receipt":
                        body = {**body, "payload_hash": "0" * 64}
                else:
                    row = c.execute("SELECT body,hash FROM records WHERE id=%s", (parts[1],)).fetchone()
                    body = {"record": row["body"], "record_hash": row["hash"]}
            self.reply(200, body)

        def do_POST(self):
            if self.path != "/effects":
                return self.reply(404, {"error": "unknown_route"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 16384:
                    return self.reply(413, {"error": "bounded_body_required"})
                payload = json.loads(self.rfile.read(length))
                validate(payload)
                if not self.authorized(payload["brand"], "write"):
                    return self.reply(403, {"error": "scope_or_role_denied"})
                brand, person, effect = payload["brand"], payload["person"], payload["effect_id"]
                with connect(config["dsn"]) as c:
                    lock(c, brand)
                    fault = c.execute("SELECT * FROM faults WHERE brand=%s AND person=%s", (brand, person)).fetchone()
                    if fault and fault["mode"] == "reject":
                        c.execute("INSERT INTO requests(brand,effect,result) VALUES(%s,%s,'fault_rejected')", (brand, effect))
                        status, body = 503, {"error": "synthetic_unavailable"}
                    else:
                        old = c.execute("SELECT * FROM effects WHERE id=%s", (effect,)).fetchone()
                        key = tuple(payload[k] for k in ("brand", "person", "segment", "channel", "purpose"))
                        current = c.execute("SELECT * FROM membership WHERE (brand,person,segment,channel,purpose)=(%s,%s,%s,%s,%s)", key).fetchone()
                        if old:
                            status, body = (200, old["receipt"]) if old["payload"] == payload else (409, {"error": "effect_content_conflict"})
                            result = "duplicate_receipt" if status == 200 else "identity_conflict"
                        elif current and current["seq"] >= payload["seq"]:
                            status, body, result = 409, {"error": "stale_sequence"}, "stale_sequence"
                        else:
                            record = {k: payload[k] for k in ("brand", "person", "segment", "channel", "purpose", "seq", "desired", "effect_id")}
                            receipt = {"effect_id": effect, "payload_hash": digest(payload), "record_hash": digest(record), "record": record}
                            c.execute("INSERT INTO effects(id,brand,payload,hash,receipt) VALUES(%s,%s,%s,%s,%s)",
                                      (effect, brand, Jsonb(payload), digest(payload), Jsonb(receipt)))
                            c.execute("INSERT INTO records VALUES(%s,%s,%s)", (effect, Jsonb(record), digest(record)))
                            c.execute("INSERT INTO membership VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(brand,person,segment,channel,purpose) DO UPDATE SET seq=excluded.seq,active=excluded.active,effect=excluded.effect",
                                      (*key, payload["seq"], payload["desired"], effect))
                            status, body, result = 200, receipt, "committed"
                            if fault and fault["mode"] == "lost_ack" and fault["remaining"] > 0:
                                c.execute("UPDATE faults SET remaining=remaining-1 WHERE brand=%s AND person=%s", (brand, person))
                                status, body, result = 503, {"error": "acknowledgment_lost_after_commit"}, "committed_ack_lost"
                        c.execute("INSERT INTO requests(brand,effect,result) VALUES(%s,%s,%s)", (brand, effect, result))
                self.reply(status, body)  # Transaction commits before the deliberately lost acknowledgment.
            except (ValueError, TypeError, KeyError):
                self.reply(400, {"error": "invalid_effect"})

    return Receiver


def serve(config, host="127.0.0.1", port=0):
    return ThreadingHTTPServer((host, port), handler(config))
