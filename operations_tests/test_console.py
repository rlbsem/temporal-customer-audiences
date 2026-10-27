import json
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from playwright.sync_api import sync_playwright

from audience_ops.db import connect
from audience_ops.runtime import free_port, private_json


def request(url, body=None, headers=None):
    try:
        with urlopen(Request(url, data=body, headers=headers or {}), timeout=3) as r:
            return r.status, json.load(r)
    except HTTPError as e:
        return e.code, json.load(e)


def console(runtime, brands):
    config = json.loads((runtime.path / "private/console.json").read_bytes())
    config["brands"] = brands
    path = runtime.path / "private/scoped-console.json"
    private_json(path, config)
    port = free_port()
    runtime.spawn("console", path, port)
    url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            if request(url + "/health")[0] == 200:
                return url
        except OSError:
            time.sleep(0.1)
    raise AssertionError("console_start_failed")


def test_read_only_console_enforces_scope_and_exposes_no_credentials(primed):
    url = console(primed, ["nova"])
    status, body = request(url + "/api/state?brand=nova")
    assert status == 200 and body["brand"] == "nova"
    raw = json.dumps(body)
    assert "atlas" not in raw and primed.config["read_token"] not in raw and primed.config["write_token"] not in raw
    assert '"dsn"' not in raw
    assert request(url + "/api/state?brand=atlas")[0] == 403
    assert request(url + "/api/state?brand=nova&brand=atlas")[0] == 403
    assert request(url + "/api/state?brand=nova", headers={"Host": "unapproved.example"})[0] == 403
    assert request(url + "/api/state?brand=nova", headers={"Origin": "https://unapproved.example"})[0] == 403
    assert request(url + "/private/controller.json")[0] == 404
    with connect(primed.config["dsn"]) as c:
        before = c.execute("SELECT count(*) AS n FROM audit").fetchone()["n"]
    for path in ["/api/approve", "/api/publish", "/api/dispatch", "/api/state"]:
        assert request(url + path, b"{}")[0] == 405
    with connect(primed.config["dsn"]) as c:
        assert c.execute("SELECT count(*) AS n FROM audit").fetchone()["n"] == before


def test_receiver_unavailability_never_becomes_false_empty_state(primed):
    url = console(primed, ["atlas", "nova"])
    assert request(url + "/api/state?brand=atlas")[0] == 200
    receiver = primed.processes[0][0]
    receiver.terminate()
    receiver.wait(timeout=10)
    status, body = request(url + "/api/state?brand=atlas")
    assert status == 503 and body["error"] == "independent_destination_readback_unknown"


def test_browser_clears_prior_brand_evidence_when_next_scope_fails(primed):
    url = console(primed, ["atlas", "nova"])
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(url)
        page.locator("#status").filter(has_text="scope: atlas").wait_for()
        assert page.locator("#metrics .metric").count() == 4
        page.route("**/api/state?brand=nova", lambda r: r.fulfill(status=503, json={"error": "controlled_read_failure"}))
        page.locator("#brand").select_option("nova")
        page.locator("#status").filter(has_text="no absence is inferred").wait_for()
        assert page.locator("#metrics .metric").count() == 0
        assert "Evidence unavailable" in page.locator("#panel").inner_text()
        browser.close()
