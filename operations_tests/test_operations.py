import copy
import json
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest

from audience_ops.bridge import Operations
from audience_ops.client import Client
from audience_ops.db import Principal, connect
from audience_ops.oracle import check
from audience_ops.runtime import initialize
from audience_ops.scenario import actor, run
from temporal_audiences.contracts import Refused, digest
from temporal_audiences.fixtures import BASE, DAY, fact

from operations_tests.helpers import approved


def test_executed_end_to_end_with_real_process_termination_and_reconciliation(runtime):
    report = run(runtime.config, runtime.receiver_config["dsn"], runtime.path / "private/controller.json")
    assert len(report["checks"]) == 36 and all(c["passed"] for c in report["checks"])
    assert sum(r["decision_rows_compared"] for r in report["oracle"]) == 164
    assert sum(r["eligibility_rows"] for r in report["oracle"]) == 20
    assert all(r["row_differences"] == 0 for r in report["oracle"])
    assert all(not r["active"] for r in report["snapshot"]["receiver"]["membership"])
    with connect(runtime.config["dsn"]) as c:
        assert {r["status"] for r in c.execute("SELECT status FROM destination_sync")} == {"matched_last_observation"}
        assert c.execute("SELECT count(*) AS n FROM reconciliation_findings").fetchone()["n"] > 0


@pytest.mark.parametrize("scope", ["other_brand", "wrong_role", "wrong_stream"])
def test_source_authority_is_scoped_before_any_ingestion(primed, scope):
    actor_value = Principal("restricted", "source", frozenset({"atlas"}), frozenset({"activity"}))
    brand, body = "atlas", [fact("profile", "new", "100", 2)]
    if scope == "other_brand":
        brand = "nova"
    if scope == "wrong_role":
        actor_value = actor("approver")
    with pytest.raises(Refused):
        primed.ops.ingest(actor_value, brand, "rejected", "facts", body)
    with connect(primed.config["dsn"]) as c:
        assert c.execute("SELECT count(*) AS n FROM inbox").fetchone()["n"] == 2


@pytest.mark.parametrize("case,reason", [("missing", "missing_permission"), ("withdrawn", "withdrawn"),
    ("suppressed", "suppressed"), ("expired", "permission_expired"), ("future", "permission_not_yet_valid"),
    ("purpose", "missing_permission"), ("channel", "missing_permission")])
def test_membership_does_not_grant_scoped_contact_permission(primed, case, reason):
    if case != "missing":
        primed.ops.permission(actor("privacy"), "atlas", "200", 1, case != "withdrawn",
                              BASE + 4 * DAY if case == "future" else BASE,
                              BASE + (2 if case == "expired" else 30) * DAY,
                              suppressed=case == "suppressed", channel="sms" if case == "channel" else "email",
                              purpose="news" if case == "purpose" else "trial_help")
    with connect(primed.config["dsn"]) as c:
        row = c.execute("SELECT * FROM activation_eligibility WHERE brand='atlas' AND person='200' AND segment='engaged_trial'").fetchone()
        assert row["member"] and row["reason"] == reason
    with pytest.raises(Refused):
        primed.activation.plan(actor("controller"), "atlas", "200", "engaged_trial", True)
    assert check(primed.config["dsn"], "atlas")["row_differences"] == 0


def test_exact_approval_and_present_policy_are_rechecked(primed):
    row = primed.activation.plan(actor("controller"), "atlas", "400", "engaged_trial", True)
    with pytest.raises(Refused):
        primed.activation.approve(actor("controller"), "atlas", row["id"], row["hash"])
    with pytest.raises(Refused):
        primed.activation.approve(actor("approver"), "atlas", row["id"], "0" * 64)
    primed.activation.approve(actor("approver"), "atlas", row["id"], row["hash"])
    primed.ops.permission(actor("privacy"), "atlas", "400", 2, False, BASE, BASE + 30 * DAY)
    assert primed.activation.dispatch(actor("controller"), "atlas", row["id"]) == "blocked"
    with connect(primed.receiver_config["dsn"]) as c:
        assert c.execute("SELECT count(*) AS n FROM requests").fetchone()["n"] == 0


def test_new_source_head_invalidates_old_approval_until_republication(primed):
    row = approved(primed)
    primed.ops.ingest(actor("source"), "atlas", "new-source", "facts", [fact("activity", "new-100", "100", 2)])
    assert primed.activation.dispatch(actor("controller"), "atlas", row["id"]) == "blocked"
    assert check(primed.config["dsn"], "atlas")["eligible"] == []


def test_reordered_retracted_and_duplicate_revisions_preserve_engine_semantics(primed):
    body = [fact("activity", "use-a-100", "100", 1, revision=3, retracted=True)]
    seq = primed.ops.ingest(actor("source"), "atlas", "revision3", "facts", body)
    assert primed.ops.ingest(actor("source"), "atlas", "revision3", "facts", body) == seq
    with pytest.raises(Refused):
        primed.ops.ingest(actor("source"), "atlas", "revision3", "facts", [fact("activity", "use-a-100", "100", 1, revision=2)])
    primed.ops.ingest(actor("source"), "atlas", "late-revision2", "facts", [fact("activity", "use-a-100", "100", 1, revision=2)])
    pub = primed.ops.publish(actor("controller"), "atlas", "after-revisions", BASE + 3 * DAY)
    assert pub["body"]["people"]["100"]["features"]["engaged_events"] == 0
    with pytest.raises(Refused):
        primed.ops.ingest(actor("source"), "atlas", "wrong-owner", "facts", [fact("activity", "use-a-100", "200", 1, revision=4)])
    assert check(primed.config["dsn"], "atlas")["row_differences"] == 0


def test_coverage_expiry_and_historical_publication_are_not_new_authority(primed):
    primed.ops.permission(actor("privacy"), "atlas", "300", 1, True, BASE, BASE + 30 * DAY)
    primed.ops.ingest(actor("source"), "atlas", "covered", "coverage", {"revision": 1, "covered_after": BASE,
                                                                      "covered_through": BASE + 3 * DAY, "retracted": False})
    prior = primed.ops.publish(actor("controller"), "atlas", "covered-now", BASE + 3 * DAY)
    row = approved(primed, "300", segment="quiet_trial")
    primed.ops.publish(actor("controller"), "atlas", "clock-only", BASE + 3 * DAY + 1)
    assert primed.activation.dispatch(actor("controller"), "atlas", row["id"]) == "blocked"
    past = primed.ops.publish(actor("controller"), "atlas", "historical", BASE + 3 * DAY, historical=True)
    assert past["body"]["activity_coverage"]["eligible"]
    with connect(primed.config["dsn"]) as c:
        current = c.execute("SELECT publication FROM active WHERE brand='atlas'").fetchone()["publication"]
        assert current != past["id"] and current != prior["id"]
    assert check(primed.config["dsn"], "atlas")["row_differences"] == 0


def test_concurrent_workers_generate_one_real_receiver_effect(primed):
    row = approved(primed)
    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(lambda _: primed.activation.dispatch(actor("controller"), "atlas", row["id"]), range(2)))
    assert "confirmed" in result
    with connect(primed.receiver_config["dsn"]) as c:
        assert c.execute("SELECT count(*) AS n FROM effects").fetchone()["n"] == 1
        assert c.execute("SELECT count(*) AS n FROM requests").fetchone()["n"] == 1


def test_third_unacknowledged_post_can_reconcile_without_a_fourth_post(primed):
    row = approved(primed)
    with connect(primed.receiver_config["dsn"]) as c:
        c.execute("INSERT INTO faults VALUES('atlas','400','reject',1)")
    for _ in range(2):
        assert primed.activation.dispatch(actor("controller"), "atlas", row["id"]) == "uncertain"
    with connect(primed.receiver_config["dsn"]) as c:
        c.execute("UPDATE faults SET mode='lost_ack' WHERE brand='atlas'")
    assert primed.activation.dispatch(actor("controller"), "atlas", row["id"]) == "uncertain"
    assert primed.activation.dispatch(actor("controller"), "atlas", row["id"]) == "confirmed"
    with connect(primed.receiver_config["dsn"]) as c:
        assert c.execute("SELECT count(*) AS n FROM requests").fetchone()["n"] == 3
        assert c.execute("SELECT count(*) AS n FROM effects").fetchone()["n"] == 1


def test_corrupt_independent_readback_is_not_replayed_or_reported_as_success(primed):
    row = approved(primed)
    primed.client.post(row["payload"])
    with connect(primed.receiver_config["dsn"]) as c:
        c.execute("INSERT INTO faults VALUES('atlas','400','bad_receipt',1)")
    for _ in range(3):
        primed.activation.dispatch(actor("controller"), "atlas", row["id"])
    with connect(primed.config["dsn"]) as c:
        record = c.execute("SELECT * FROM intents WHERE id=%s", (row["id"],)).fetchone()
        assert record["state"] == "excepted" and record["attempts"] == 0
    with connect(primed.receiver_config["dsn"]) as c:
        assert c.execute("SELECT count(*) AS n FROM requests").fetchone()["n"] == 1


def test_receiver_sequence_fence_blocks_reordered_add_after_removal(primed):
    row = approved(primed)
    assert primed.activation.dispatch(actor("controller"), "atlas", row["id"]) == "confirmed"
    primed.ops.permission(actor("privacy"), "atlas", "400", 2, False, BASE, BASE + 30 * DAY)
    remove = primed.activation.plan(actor("controller"), "atlas", "400", "engaged_trial", False)
    assert primed.activation.dispatch(actor("controller"), "atlas", remove["id"]) == "confirmed"
    primed.client.post(row["payload"])
    changed = copy.deepcopy(row["payload"])
    changed["authority"] = "new-content"
    changed["effect_id"] = digest({k: v for k, v in changed.items() if k != "effect_id"})
    status, body = primed.client.request("/effects", changed, primed.config["write_token"])
    assert status == 409 and body["error"] == "stale_sequence"
    assert not next(r for r in primed.client.membership("atlas") if r["person"] == "400")["active"]


def test_unknown_receiver_identity_becomes_manual_exception_not_identity_merge(primed):
    with connect(primed.receiver_config["dsn"]) as c:
        c.execute("INSERT INTO membership VALUES('atlas','outsider','quiet_trial','email','trial_help',1,true,NULL)")
    findings = primed.activation.reconcile(actor("controller"), "atlas")
    assert any(r["reason"] == "unknown_destination_identity_manual_exception" for r in findings)
    assert all(r["person"] != "outsider" or "intent" not in r for r in findings)


def test_sql_views_use_correct_grain_despite_multiple_permission_revisions(primed):
    primed.ops.permission(actor("privacy"), "atlas", "400", 2, True, BASE, BASE + 20 * DAY)
    with connect(primed.config["dsn"]) as c:
        correct = c.execute("SELECT count(*) AS n FROM activation_eligibility WHERE brand='atlas'").fetchone()["n"]
        naive = c.execute("SELECT count(*) AS n FROM current_audience a JOIN permissions p USING(brand,person) WHERE a.brand='atlas' AND a.person='400'").fetchone()["n"]
        assert correct == 18 and naive == 4
        assert c.execute("SELECT count(*) AS n FROM destination_sync WHERE status='unobserved'").fetchone()["n"] == 20
    assert check(primed.config["dsn"], "atlas")["eligibility_rows"] == 18


def test_operating_and_console_logins_cannot_mutate_independent_receipts(primed):
    receiver_info = psycopg.conninfo.conninfo_to_dict(primed.receiver_config["dsn"])
    wrong = psycopg.conninfo.make_conninfo(primed.config["dsn"], dbname=receiver_info["dbname"])
    with pytest.raises(psycopg.OperationalError):
        psycopg.connect(wrong)
    console = json.loads((primed.path / "private/console.json").read_bytes())
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with connect(console["dsn"]) as c:
            c.execute("UPDATE brands SET clock=0")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with connect(primed.config["dsn"]) as c:
            c.execute("DELETE FROM publications")
    row = approved(primed)
    with pytest.raises(psycopg.errors.RaiseException):
        with connect(primed.config["dsn"]) as c:
            c.execute("UPDATE intents SET hash='forged' WHERE id=%s", (row["id"],))
    status, _ = primed.client.request("/effects", row["payload"], primed.config["read_token"])
    assert status == 403


def test_restart_preserves_publication_and_configuration_identities(primed):
    old = primed.ops.publish(actor("controller"), "atlas", "baseline", BASE + 3 * DAY)
    restarted = Operations(primed.config["dsn"])
    assert restarted.publish(actor("controller"), "atlas", "baseline", BASE + 3 * DAY) == old
    config = initialize(primed.admin, primed.path / "private", primed.config["url"])
    assert config == primed.config


@pytest.mark.parametrize("url", ["https://api.example.com", "http://169.254.169.254", "http://user:pass@localhost:80", "http://localhost:80/?secret=x"])
def test_destination_is_local_and_cannot_exfiltrate_credentials(url):
    with pytest.raises(Refused):
        Client(url, "test-token")
