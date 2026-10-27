"""Actual console browser acceptance; no outbound communication or vendor actions."""
import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
VIEWS = ["people", "history", "delivery", "reconcile", "proof"]
AXE_SHA = "880970c081707360e64f34cea25ff91892f5bc95675b0776925b9709dd8a68bb"


def browser_check(url, output):
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"} or parsed.username or parsed.password:
        raise ValueError("local_console_only")
    output = Path(output)
    if output.exists():
        raise ValueError("fresh_browser_evidence_directory_required")
    output.mkdir(parents=True)
    axe = ROOT / "operations_tests/vendor/axe.min.js"
    assert hashlib.sha256(axe.read_bytes()).hexdigest() == AXE_SHA
    checks, scans, images, errors, writes, outside = [], [], {}, [], [], []

    def require(name, actual):
        assert actual, name
        checks.append({"check": name, "passed": True})

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1100}, reduced_motion="reduce")
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("request", lambda r: writes.append(r.method) if r.method != "GET" else None)
        page.on("request", lambda r: outside.append(r.url) if not r.url.startswith(url) else None)
        page.add_init_script(script=axe.read_text(encoding="utf-8"))
        page.goto(url)
        page.locator("#status").filter(has_text="Actual local evidence loaded").wait_for()
        for width in [1440, 1024, 768, 390, 320]:
            page.set_viewport_size({"width": width, "height": 1100 if width > 768 else 844})
            for brand in ["atlas", "nova"]:
                page.locator("#brand").select_option(brand)
                page.locator("#status").filter(has_text="scope: " + brand).wait_for()
                for view in VIEWS:
                    page.locator(f'[data-view="{view}"]').focus()
                    page.keyboard.press("Enter")
                    require(f"{width}:{brand}:{view}:selected", page.locator(f'[data-view="{view}"]').get_attribute("aria-pressed") == "true")
                    require(f"{width}:{brand}:{view}:no_page_overflow", not page.evaluate("document.documentElement.scrollWidth>innerWidth"))
                    if width in [1440, 390]:
                        result = page.evaluate("async()=>{const r=await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}});return {violations:r.violations,incomplete:r.incomplete,passes:r.passes.length}}")
                        assert not result["violations"], f"accessibility {width} {brand} {view}"
                        followups = []
                        for issue in result["incomplete"]:
                            for node in issue["nodes"]:
                                selector = node["target"][0]
                                target = page.locator(selector)
                                if target.count() != 1:
                                    raise AssertionError("accessibility_followup_target_not_unique")
                                target.evaluate("e=>e.scrollIntoView({block:'center',inline:'center'})")
                                detail = target.evaluate("async (e,rule)=>{const r=await axe.run(e,{runOnly:{type:'rule',values:[rule]}});return {violations:r.violations,incomplete:r.incomplete,passes:r.passes.length}}", issue["id"])
                                followups.append({"rule": issue["id"], "target": node["target"], **detail})
                        scans.append({"width": width, "brand": brand, "view": view, **result, "visibility_followups": followups})
        page.set_viewport_size({"width": 1440, "height": 1200})
        page.locator("#brand").select_option("atlas")
        page.locator("#status").filter(has_text="scope: atlas").wait_for()
        page.locator('[data-view="people"]').click()
        # Actual published snapshots, not client-generated historical calculations.
        options = page.locator("#publication option").evaluate_all("es=>es.map(e=>({value:e.value,text:e.textContent}))")
        original = next(o["value"] for o in options if "day3-original" in o["text"])
        restated = next(o["value"] for o in options if "day3-restated-history" in o["text"])
        page.locator("#publication").select_option(original)
        row=page.locator("tbody tr").filter(has=page.get_by_role("cell",name="100",exact=True)).filter(has=page.get_by_role("cell",name="engaged_trial",exact=True))
        require("original_publication_excludes_engaged_100",row.locator("td").nth(2).inner_text()=="false")
        page.locator("#publication").select_option(restated)
        row=page.locator("tbody tr").filter(has=page.get_by_role("cell",name="100",exact=True)).filter(has=page.get_by_role("cell",name="engaged_trial",exact=True))
        require("restated_publication_includes_engaged_100",row.locator("td").nth(2).inner_text()=="true")
        page.get_by_role("button", name="Inspect 100", exact=True).first.click()
        require("keyboard_inspection_moves_focus_to_person_evidence", page.evaluate("document.activeElement.id") == "person-detail")
        page.get_by_text("Original evaluator features, revisions and reasons", exact=True).click()
        require("source_evidence_opens", "event_threshold_met" in page.locator("#person-detail").inner_text())
        page.locator('[data-view="delivery"]').click()
        page.get_by_role("button", name="Read receipt · 400 / engaged_trial / 1", exact=True).click()
        page.locator("#receipt-result").filter(has_text="historical_receipt_verified").wait_for()
        require("real_independent_http_receipt_and_record_read", "new_action_authorized" in page.locator("#receipt-result").inner_text())
        page.locator('[data-view="history"]').click()
        require("clock_only_expiry_visible", "day8-engagement-expiry" in page.locator("#panel").inner_text())
        for name, view in [("operations-desktop.png", "people"), ("delivery-desktop.png", "delivery")]:
            page.locator(f'[data-view="{view}"]').click()
            page.evaluate("scrollTo(0,0)")
            page.screenshot(path=str(output / name))
            images[name] = {"width": 1440, "height": 1200, "view": view, "brand": "atlas"}
        page.set_viewport_size({"width": 390, "height": 1000})
        page.locator('[data-view="proof"]').click()
        page.locator("#panel").scroll_into_view_if_needed()
        page.screenshot(path=str(output / "operations-mobile.png"))
        images["operations-mobile.png"] = {"width": 390, "height": 1000, "view": "proof", "brand": "atlas"}
        require("all_browser_requests_read_only", not writes)
        require("no_external_network_requests", not outside)
        require("no_browser_runtime_errors", not errors)
        version = browser.version
        browser.close()
    report = {"executed_at": datetime.now(UTC).isoformat(), "browser": "Chromium " + version,
              "scope": "Actual local console backed by PostgreSQL and independent local HTTP receiver",
              "checks": checks, "accessibility": scans, "axe_version": "4.10.3", "axe_sha256": AXE_SHA,
              "images": images, "image_sha256": {n: hashlib.sha256((output / n).read_bytes()).hexdigest() for n in images},
              "source_sha256": {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in sorted((ROOT / "src/audience_ops/web").iterdir())},
              "page_errors": errors, "http_writes": writes, "external_requests": outside,
              "native_vendor_calls": 0}
    (output / "browser.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    assert all(not r["violations"] for r in scans)
    unresolved = [f for r in scans for f in r["visibility_followups"] if f["violations"] or f["incomplete"] or not f["passes"]]
    assert not unresolved, "accessibility visibility followup unresolved"
    print(json.dumps({"browser_checks": len(checks), "accessibility_states": len(scans), "screenshots": len(images), "status": "passed"}))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    browser_check(args.url, args.output)
