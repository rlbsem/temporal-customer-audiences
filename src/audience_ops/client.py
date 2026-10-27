import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from temporal_audiences.contracts import Refused, digest, identifier


class Unknown(RuntimeError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_):
        return None


class Client:
    def __init__(self, url, read_token, write_token=None):
        parsed = urlparse(url)
        if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "receiver"}
                or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}):
            raise Refused("local_destination_only")
        self.url, self.read_token, self.write_token = url.rstrip("/"), read_token, write_token
        self.opener = build_opener(NoRedirect())

    def request(self, path, body=None, token=None):
        raw = None if body is None else json.dumps(body).encode()
        request = Request(self.url + path, data=raw, headers={"Authorization": "Bearer " + (token or self.read_token),
                                                           "Content-Type": "application/json"})
        try:
            with self.opener.open(request, timeout=2) as response:
                return response.status, json.loads(response.read(1000000))
        except HTTPError as e:
            try:
                return e.code, json.loads(e.read(1000000))
            except (ValueError, OSError) as exc:
                raise Unknown("unverified_http_response") from exc
        except (URLError, TimeoutError, ValueError, OSError) as exc:
            raise Unknown("destination_unavailable") from exc

    def readback(self, payload):
        query = urlencode({"brand": payload["brand"], "person": payload["person"]})
        status, receipt = self.request("/receipts/" + payload["effect_id"] + "?" + query)
        if status == 404 and receipt == {"contract": 1, "status": "absent", "effect_id": payload["effect_id"], "brand": payload["brand"]}:
            return None
        if status != 200:
            raise Unknown("receipt_readback_unknown")
        status, record = self.request("/records/" + payload["effect_id"] + "?" + query)
        expected = {k: payload[k] for k in ("brand", "person", "segment", "channel", "purpose", "seq", "desired", "effect_id")}
        if (status != 200 or receipt.get("effect_id") != payload["effect_id"]
                or receipt.get("payload_hash") != digest(payload) or receipt.get("record") != expected
                or receipt.get("record_hash") != digest(expected)
                or record != {"record": expected, "record_hash": digest(expected)}):
            raise Unknown("exact_content_readback_failed")
        return receipt

    def post(self, payload):
        if not self.write_token:
            raise Refused("writer_credential_required")
        status, body = self.request("/effects", payload, self.write_token)
        if status != 200:
            raise Unknown("post_unacknowledged_" + str(status))
        return body

    def membership(self, brand):
        status, body = self.request("/membership?" + urlencode({"brand": brand}))
        if status != 200 or body.get("brand") != brand or body.get("contract") != 1:
            raise Unknown("membership_unknown")
        rows = body.get("rows")
        if not isinstance(rows, list) or any(r.get("brand") != brand for r in rows):
            raise Unknown("membership_scope_mismatch")
        seen = set()
        for r in rows:
            if (set(r) != {"brand", "person", "segment", "channel", "purpose", "seq", "active", "effect"}
                    or r["segment"] not in {"engaged_trial", "quiet_trial"} or r["channel"] != "email"
                    or r["purpose"] != "trial_help" or type(r["seq"]) is not int or not 0 <= r["seq"] < 2**53
                    or type(r["active"]) is not bool or (r["effect"] is not None and not re.fullmatch(r"[a-f0-9]{64}", r["effect"]))):
                raise Unknown("membership_contract_unknown")
            try:
                identifier(r["person"])
            except Refused as exc:
                raise Unknown("membership_identity_unknown") from exc
            key = r["person"], r["segment"], r["channel"], r["purpose"]
            if key in seen:
                raise Unknown("membership_duplicate_grain")
            seen.add(key)
        return rows
