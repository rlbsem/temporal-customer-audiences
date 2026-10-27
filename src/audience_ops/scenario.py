"""Actual multi-brand synthetic workflow, assertions and sanitized source/receipt evidence."""
import copy
import json
import subprocess
import sys
import time


from temporal_audiences.contracts import DAY, Refused, digest
from temporal_audiences.fixtures import BASE, fact

from .activation import Activation
from .bridge import Operations
from .client import Client
from .db import Principal, connect
from .oracle import check

BRANDS = frozenset({"atlas", "nova"})


def actor(role, brands=BRANDS):
    return Principal("synthetic-" + role, role, brands,
                     frozenset({"profile", "activity", "coverage"}) if role == "source" else frozenset())


def seed(config):
    with connect(config["dsn"]) as c:
        if c.execute("SELECT 1 FROM brands LIMIT 1").fetchone():
            raise Refused("scenario_requires_fresh_database")
        for brand, entity in [("atlas", "SYN-ATLAS"), ("nova", "SYN-NOVA")]:
            c.execute("INSERT INTO brands VALUES(%s,%s,%s)", (brand, entity, BASE))
        for person in ("100", "200", "300", "400", "500", "600", "700", "800", "900"):
            c.execute("INSERT INTO subjects VALUES('atlas',%s)", (person,))
        c.execute("INSERT INTO subjects VALUES('nova','100')")
    ops = Operations(config["dsn"])
    rows = []
    for person in ("100", "200", "300", "400", "500", "600", "700", "800", "900"):
        rows.append(fact("profile", "profile-" + person, person, 0))
        if person != "300":
            rows.append(fact("activity", "use-a-" + person, person, 1))
            if person != "100":
                rows.append(fact("activity", "use-b-" + person, person, 2))
    ops.ingest(actor("source"), "atlas", "initial", "facts", rows)
    ops.ingest(actor("source"), "nova", "initial", "facts", [fact("profile", "profile-100", "100", 0),
                                                              fact("activity", "use-a-100", "100", 1),
                                                              fact("activity", "use-b-100", "100", 2)])
    for brand, people in [("atlas", ["100", "400", "500", "600", "700", "800"]), ("nova", ["100"])]:
        for person in people:
            ops.permission(actor("privacy"), brand, person, 1, True, BASE, BASE + 30 * DAY)
    # A channel/purpose grant does not imply email permission for trial assistance.
    ops.permission(actor("privacy"), "atlas", "900", 1, True, BASE, BASE + 30 * DAY, purpose="news")
    return ops


def run(config, receiver_dsn, controller_file):
    ops = seed(config)
    client = Client(config["url"], config["read_token"], config["write_token"])
    activation = Activation(config["dsn"], client)
    checks, observations = [], {}

    def require(name, expected, observed):
        assert expected == observed, name
        checks.append({"check": name, "expected": expected, "observed": observed, "passed": True})

    def value(brand, person, segment, column):
        with connect(config["dsn"]) as c:
            return c.execute("SELECT * FROM activation_eligibility WHERE brand=%s AND person=%s AND segment=%s",
                             (brand, person, segment)).fetchone()[column]

    def approved(brand, person, segment="engaged_trial"):
        row = activation.plan(actor("controller"), brand, person, segment, True)
        activation.approve(actor("approver"), brand, row["id"], row["hash"])
        return row

    def state(effect):
        with connect(config["dsn"]) as c:
            return c.execute("SELECT * FROM intents WHERE id=%s", (effect,)).fetchone()

    original = ops.publish(actor("controller"), "atlas", "day3-original", BASE + 3 * DAY)
    ops.publish(actor("controller"), "nova", "day3-original", BASE + 3 * DAY)
    original_hash = digest(original["body"])
    require("same_local_100_different_brand_engagement", [False, True],
            [value("atlas", "100", "engaged_trial", "member"), value("nova", "100", "engaged_trial", "member")])
    require("member_without_permission_not_activatable", "missing_permission", value("atlas", "200", "engaged_trial", "reason"))
    require("absence_requires_coverage", "incomplete_coverage", value("atlas", "300", "quiet_trial", "reason"))
    require("wrong_purpose_is_not_permission", "missing_permission", value("atlas", "900", "engaged_trial", "reason"))
    try:
        ops.publish(actor("controller", frozenset({"nova"})), "atlas", "forbidden", BASE + 3 * DAY)
    except Refused:
        require("cross_brand_controller_denied", True, True)
    else:
        raise AssertionError("cross_brand_controller_allowed")
    with connect(receiver_dsn) as c:
        for person, mode in [("400", "lost_ack"), ("500", "reject"), ("600", "unknown")]:
            c.execute("INSERT INTO faults VALUES('atlas',%s,%s,1)", (person, mode))
    lost = approved("atlas", "400")
    require("lost_ack_sender_uncertain", "uncertain", activation.dispatch(actor("controller"), "atlas", lost["id"]))
    require("independent_receipt_after_lost_ack", True, client.readback(lost["payload"]) is not None)
    require("lost_ack_recovered_without_new_post", "confirmed", activation.dispatch(actor("controller"), "atlas", lost["id"]))
    require("exact_duplicate_receipt", client.readback(lost["payload"]), client.post(lost["payload"]))
    for person in ["500", "600"]:
        row = approved("atlas", person)
        for _ in range(4):
            activation.dispatch(actor("controller"), "atlas", row["id"])
        require("controlled_exception_" + person, "excepted", state(row["id"])["state"])
        require("bounded_post_reservations_" + person, 3 if person == "500" else 0, state(row["id"])["attempts"])
    withdrawn = approved("atlas", "800")
    ops.permission(actor("privacy"), "atlas", "800", 2, False, BASE, BASE + 30 * DAY)
    require("withdrawal_between_approval_and_dispatch", "blocked", activation.dispatch(actor("controller"), "atlas", withdrawn["id"]))
    crashed = approved("atlas", "700")
    child = subprocess.run([sys.executable, "-m", "audience_ops.worker", "--config", str(controller_file), "--brand", "atlas",
                            "--effect", crashed["id"], "--lease-seconds", "1", "--crash-after-post"], capture_output=True, timeout=30)
    require("real_worker_process_termination", 86, child.returncode)
    require("crash_leaves_durable_reservation", 1, state(crashed["id"])["attempts"])
    time.sleep(1.2)
    require("restart_reads_committed_effect", "confirmed", activation.dispatch(actor("controller"), "atlas", crashed["id"]))
    nova = approved("nova", "100")
    require("nova_initial_delivery", "confirmed", activation.dispatch(actor("controller"), "nova", nova["id"]))
    ops.permission(actor("privacy"), "nova", "100", 2, False, BASE, BASE + 30 * DAY)
    observations["nova_withdrawal"] = activation.reconcile(actor("controller"), "nova", repair=True)
    for finding in observations["nova_withdrawal"]:
        activation.dispatch(actor("controller"), "nova", finding["intent"])
    require("permission_withdrawal_removes_existing_membership", [], activation.reconcile(actor("controller"), "nova"))
    ops.ingest(actor("source"), "atlas", "late-second-event", "facts", [fact("activity", "use-b-100", "100", 2)])
    with connect(receiver_dsn) as c:
        requests_before_history = c.execute("SELECT count(*) AS n FROM requests").fetchone()["n"]
    historical = ops.publish(actor("controller"), "atlas", "day3-restated-history", BASE + 3 * DAY, historical=True)
    with connect(config["dsn"]) as c:
        active = c.execute("SELECT publication FROM active WHERE brand='atlas'").fetchone()["publication"]
        preserved = c.execute("SELECT body FROM publications WHERE id=%s", (original["id"],)).fetchone()["body"]
    require("restatement_does_not_change_active_pointer", original["id"], active)
    require("original_publication_preserved", original_hash, digest(preserved))
    require("late_event_changes_historical_engagement", True, historical["body"]["people"]["100"]["membership"]["engaged_trial"])
    with connect(receiver_dsn) as c:
        requests_after_history = c.execute("SELECT count(*) AS n FROM requests").fetchone()["n"]
    require("backfill_emits_no_http_action", 0, requests_after_history - requests_before_history)
    observations["history"] = {"original": original["id"], "restated": historical["id"],
                               "new_http_actions_from_backfill": requests_after_history - requests_before_history}
    ops.publish(actor("controller"), "atlas", "day3-current-corrected", BASE + 3 * DAY)
    current = approved("atlas", "100")
    require("separately_approved_current_delivery", "confirmed", activation.dispatch(actor("controller"), "atlas", current["id"]))
    ops.permission(actor("privacy"), "atlas", "900", 1, True, BASE, BASE + 3 * DAY + 1)
    expires = approved("atlas", "900")
    before_clock = ops.publish(actor("controller"), "atlas", "day6-no-ingestion", BASE + 6 * DAY)
    require("permission_expired_on_current_clock", "permission_expired", value("atlas", "900", "engaged_trial", "reason"))
    require("expired_permission_blocks_pending_effect", "blocked", activation.dispatch(actor("controller"), "atlas", expires["id"]))
    require("clock_alone_makes_quiet", True, before_clock["body"]["people"]["100"]["membership"]["quiet_trial"])
    require("quiet_still_needs_source_coverage", "incomplete_coverage", value("atlas", "100", "quiet_trial", "reason"))
    ops.ingest(actor("source"), "atlas", "coverage-day6", "coverage", {"revision": 1, "covered_after": BASE + 2 * DAY,
                                                                          "covered_through": BASE + 6 * DAY, "retracted": False})
    ops.permission(actor("privacy"), "atlas", "300", 1, True, BASE, BASE + 30 * DAY)
    ops.publish(actor("controller"), "atlas", "day6-covered", BASE + 6 * DAY)
    quiet = approved("atlas", "300", "quiet_trial")
    require("covered_quiet_explicitly_approved", "confirmed", activation.dispatch(actor("controller"), "atlas", quiet["id"]))
    ops.publish(actor("controller"), "atlas", "coverage-expired-clock-only", BASE + 6 * DAY + 1)
    require("coverage_expires_at_first_second_after_assertion", "incomplete_coverage", value("atlas", "300", "quiet_trial", "reason"))
    observations["coverage_removal"] = activation.reconcile(actor("controller"), "atlas", repair=True)
    # Do not automatically approve missing adds discovered by reconciliation.
    for finding in observations["coverage_removal"]:
        if not finding["expected"]:
            activation.dispatch(actor("controller"), "atlas", finding["intent"])
    client.post(quiet["payload"])  # Old duplicate returns historical receipt, never re-adds membership.
    require("old_delivery_cannot_resurrect_removed_member", False, next(r for r in client.membership("atlas") if r["person"] == "300" and r["segment"] == "quiet_trial")["active"])
    ops.publish(actor("controller"), "atlas", "day8-engagement-expiry", BASE + 8 * DAY)
    require("clock_alone_expires_engagement", False, value("atlas", "100", "engaged_trial", "member"))
    observations["expiry_removal"] = activation.reconcile(actor("controller"), "atlas", repair=True)
    for finding in observations["expiry_removal"]:
        if not finding["expected"]:
            activation.dispatch(actor("controller"), "atlas", finding["intent"])
    # Trusted acceptance fault, not an operator-facing or unauthenticated API.
    with connect(receiver_dsn) as c:
        c.execute("INSERT INTO membership VALUES('atlas','200','engaged_trial','email','trial_help',7,true,NULL)")
    observations["receiver_drift"] = activation.reconcile(actor("controller"), "atlas", repair=True)
    for finding in observations["receiver_drift"]:
        activation.dispatch(actor("controller"), "atlas", finding["intent"])
    prior_receipt = client.readback(lost["payload"])
    ops.ingest(actor("source"), "atlas", "late-source-revision", "facts",
               [fact("activity", "use-b-400", "400", 2, value="noise", revision=2)])
    corrected = ops.publish(actor("controller"), "atlas", "correct-completed-delivery-history", BASE + 3 * DAY, historical=True)
    require("source_correction_changes_past_qualification", False, corrected["body"]["people"]["400"]["membership"]["engaged_trial"])
    require("past_delivery_receipt_not_rewritten_by_correction", prior_receipt, client.readback(lost["payload"]))
    ops.publish(actor("controller"), "atlas", "day8-current-after-revision", BASE + 8 * DAY)
    require("reconciliation_restores_authorized_state_atlas", [], activation.reconcile(actor("controller"), "atlas"))
    require("reconciliation_restores_authorized_state_nova", [], activation.reconcile(actor("controller"), "nova"))
    oracle = [check(config["dsn"], brand) for brand in sorted(BRANDS)]
    snapshot = export(config, receiver_dsn)
    return {"schema_version": "activation-acceptance.v1", "synthetic": True, "native_vendor_calls": 0,
            "lane": "actual_local_postgresql_sqlite_bridge_http_and_worker_process", "checks": checks,
            "oracle": oracle, "observations": observations, "snapshot": snapshot}


def export(config, receiver_dsn):
    result = {"operating": {}, "receiver": {}}
    with connect(config["dsn"]) as c:
        for table in ["brands", "subjects", "inbox", "publications", "decisions", "permissions", "intents", "audit", "reconciliations", "activation_eligibility"]:
            result["operating"][table] = c.execute("SELECT * FROM " + table).fetchall()
    with connect(receiver_dsn) as c:
        for table in ["effects", "records", "membership", "requests"]:
            result["receiver"][table] = c.execute("SELECT * FROM " + table).fetchall()
    return json.loads(json.dumps(copy.deepcopy(result), default=str))
