"""Explicit approval, present-tense eligibility and a fenced durable outbox."""
import os
from uuid import uuid4

from psycopg.types.json import Jsonb

from temporal_audiences.contracts import Refused, digest

from .client import Unknown
from .db import audit, connect, lock

KEYS = ("brand", "person", "segment", "channel", "purpose")


def eligibility(c, brand, person, segment):
    row = c.execute("SELECT * FROM activation_eligibility WHERE brand=%s AND person=%s AND segment=%s",
                    (brand, person, segment)).fetchone()
    if not row:
        raise Refused("unknown_scoped_audience")
    return row


def authority(row):
    return digest({k: row[k] for k in ("brand", "person", "segment", "publication", "permission_id", "rule_hash", "reason")})


class Activation:
    def __init__(self, dsn, client):
        self.dsn, self.client = dsn, client

    def plan(self, principal, brand, person, segment, desired, remote_seq=0):
        principal.require(brand, {"controller"})
        if type(desired) is not bool or type(remote_seq) is not int or not 0 <= remote_seq < 2**53:
            raise Refused("invalid_target")
        with connect(self.dsn) as c:
            lock(c, brand)
            row = eligibility(c, brand, person, segment)
            if desired != (row["reason"] == "eligible"):
                raise Refused("desired_state_disagrees_with_current_policy")
            key = (brand, person, segment, "email", "trial_help")
            head = c.execute("SELECT i.* FROM heads h JOIN intents i ON i.id=h.intent WHERE (h.brand,h.person,h.segment,h.channel,h.purpose)=(%s,%s,%s,%s,%s)", key).fetchone()
            bound = authority(row)
            if head and head["authority"] == bound and head["desired"] == desired and head["seq"] > remote_seq:
                return head
            seq = max(head["seq"] if head else 0, remote_seq) + 1
            payload = dict(zip(KEYS, key)) | dict(contract=1, seq=seq, desired=desired, authority=bound)
            effect = digest(payload)
            payload["effect_id"] = effect
            approval = None if desired else {"actor": principal.name, "policy": "protective-removal-v1", "hash": digest(payload)}
            c.execute("INSERT INTO intents(id,brand,person,segment,channel,purpose,seq,desired,payload,hash,authority,approval,state) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                      (effect, *key, seq, desired, Jsonb(payload), digest(payload), bound,
                       Jsonb(approval) if approval else None, "pending" if desired else "approved"))
            c.execute("INSERT INTO heads VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(brand,person,segment,channel,purpose) DO UPDATE SET seq=excluded.seq,intent=excluded.intent",
                      (*key, seq, effect))
            audit(c, brand, principal.name, "intent_frozen", effect, {"payload_hash": digest(payload), "desired": desired, "reason": row["reason"]})
            return c.execute("SELECT * FROM intents WHERE id=%s", (effect,)).fetchone()

    def approve(self, principal, brand, effect, exact_hash):
        principal.require(brand, {"approver"})
        with connect(self.dsn) as c:
            lock(c, brand)
            row = c.execute("SELECT * FROM intents WHERE id=%s AND brand=%s FOR UPDATE", (effect, brand)).fetchone()
            if not row or row["hash"] != exact_hash or row["state"] not in {"pending", "approved"}:
                raise Refused("exact_approval_refused")
            current = eligibility(c, brand, row["person"], row["segment"])
            if current["reason"] != "eligible" or authority(current) != row["authority"]:
                raise Refused("approval_authority_changed")
            approval = {"actor": principal.name, "policy": "reviewed-add-v1", "hash": exact_hash}
            c.execute("UPDATE intents SET approval=%s,state='approved' WHERE id=%s", (Jsonb(approval), effect))
            audit(c, brand, principal.name, "exact_approval", effect, approval)

    def dispatch(self, principal, brand, effect=None, lease_seconds=30, crash_after_post=False):
        principal.require(brand, {"controller"})
        if not 1 <= lease_seconds <= 300:
            raise Refused("invalid_lease")
        lease = uuid4().hex
        with connect(self.dsn) as c:
            # Claim and commit before network I/O. Another worker skips active leases.
            row = c.execute("SELECT * FROM intents WHERE brand=%s AND (%s::text IS NULL OR id=%s) AND (state IN ('approved','uncertain') OR (state='inflight' AND lease_until<clock_timestamp())) ORDER BY seq,id FOR UPDATE SKIP LOCKED LIMIT 1",
                            (brand, effect, effect)).fetchone()
            if not row:
                return "idle"
            c.execute("UPDATE intents SET state='inflight',lease=%s,lease_until=clock_timestamp()+(%s * interval '1 second') WHERE id=%s",
                      (lease, lease_seconds, row["id"]))
        effect, payload = row["id"], row["payload"]
        try:
            receipt = self.client.readback(payload)
        except Unknown as exc:
            return self._unknown(principal, row, lease, str(exc), read_check=True)
        if receipt:
            # Historical truth is reconciled before checking authorization for a NEW request.
            return self._confirm(principal, row, lease, receipt, "independent_receipt_recovered")
        with connect(self.dsn) as c:
            lock(c, brand)
            held = c.execute("SELECT * FROM intents WHERE id=%s FOR UPDATE", (effect,)).fetchone()
            if held["lease"] != lease or held["state"] != "inflight":
                return "lease_lost"
            current = eligibility(c, brand, row["person"], row["segment"])
            head = c.execute("SELECT intent FROM heads WHERE (brand,person,segment,channel,purpose)=(%s,%s,%s,%s,%s)", tuple(row[k] for k in KEYS)).fetchone()
            allowed = (head["intent"] == effect and current["reason"] == "eligible" and row["desired"]
                       and authority(current) == row["authority"] and row["approval"]
                       and row["approval"]["hash"] == row["hash"])
            remove = head["intent"] == effect and not row["desired"] and current["reason"] != "eligible"
            if not (allowed or remove):
                c.execute("UPDATE intents SET state='blocked',reason='current_authority_changed',lease=NULL WHERE id=%s", (effect,))
                audit(c, brand, principal.name, "dispatch_blocked", effect, {"current_reason": current["reason"]})
                return "blocked"
            if held["attempts"] >= 3:
                c.execute("UPDATE intents SET state='excepted',reason='post_attempts_exhausted' WHERE id=%s", (effect,))
                return "excepted"
            c.execute("UPDATE intents SET attempts=attempts+1 WHERE id=%s", (effect,))
            audit(c, brand, principal.name, "authorized_http_attempt", effect, {"policy_clock": current["clock"], "attempt": held["attempts"] + 1})
            # Reserve the finite attempt budget durably BEFORE a process can die
            # after an external commit. Reservations may exceed actual HTTP calls.
            c.commit()
            lock(c, brand)
            held = c.execute("SELECT * FROM intents WHERE id=%s FOR UPDATE", (effect,)).fetchone()
            current = eligibility(c, brand, row["person"], row["segment"])
            head = c.execute("SELECT intent FROM heads WHERE (brand,person,segment,channel,purpose)=(%s,%s,%s,%s,%s)", tuple(row[k] for k in KEYS)).fetchone()
            if held["lease"] != lease or held["state"] != "inflight":
                return "lease_lost"
            allowed = (head["intent"] == effect and row["desired"] and current["reason"] == "eligible"
                       and authority(current) == row["authority"] and held["approval"]
                       and held["approval"]["hash"] == held["hash"])
            remove = head["intent"] == effect and not row["desired"] and current["reason"] != "eligible"
            if not (allowed or remove):
                c.execute("UPDATE intents SET state='blocked',reason='authority_changed_after_reservation',lease=NULL WHERE id=%s", (effect,))
                return "blocked"
            # Keep the brand authorization lock through the bounded request. A concurrent
            # permission change waits. This is not a distributed transaction with the receiver.
            try:
                self.client.post(payload)
            except Unknown as exc:
                # Even the third request may have committed. One further
                # reconciliation is allowed; it never grants a fourth POST.
                c.execute("UPDATE intents SET state='uncertain',reason=%s,lease=NULL WHERE id=%s", (str(exc), effect))
                return "uncertain"
            if crash_after_post:
                # Commit the durable attempt before genuinely terminating the process.
                c.commit()
                os._exit(86)
        try:
            receipt = self.client.readback(payload)
            if receipt is None:
                raise Unknown("ack_without_independent_receipt")
        except Unknown as exc:
            return self._unknown(principal, row, lease, str(exc), read_check=True)
        return self._confirm(principal, row, lease, receipt, "delivered_and_read_back")

    def _unknown(self, principal, row, lease, reason, read_check):
        with connect(self.dsn) as c:
            held = c.execute("SELECT * FROM intents WHERE id=%s FOR UPDATE", (row["id"],)).fetchone()
            if held["lease"] != lease or held["state"] != "inflight":
                return "lease_lost"
            checks = held["checks"] + int(read_check)
            state = "excepted" if checks >= 3 else "uncertain"
            c.execute("UPDATE intents SET checks=%s,state=%s,reason=%s,lease=NULL WHERE id=%s",
                      (checks, state, reason, row["id"]))
            audit(c, row["brand"], principal.name, "readback_exception", row["id"], {"reason": reason, "checks": checks})
            return state

    def _confirm(self, principal, row, lease, receipt, reason):
        with connect(self.dsn) as c:
            held = c.execute("SELECT * FROM intents WHERE id=%s FOR UPDATE", (row["id"],)).fetchone()
            if held["lease"] != lease or held["state"] != "inflight":
                return "lease_lost"
            c.execute("UPDATE intents SET state='confirmed',receipt=%s,reason=%s,lease=NULL WHERE id=%s",
                      (Jsonb(receipt), reason, row["id"]))
            audit(c, row["brand"], principal.name, "receipt_confirmed", row["id"], {"reason": reason, "payload_hash": row["hash"]})
            return "confirmed"

    def reconcile(self, principal, brand, repair=False):
        principal.require(brand, {"controller"})
        try:
            remote = self.client.membership(brand)
        except Unknown as exc:
            with connect(self.dsn) as c:
                finding = [{"brand": brand, "reason": "destination_membership_unknown", "detail": str(exc)}]
                c.execute("INSERT INTO reconciliations(brand,body) VALUES(%s,%s)", (brand, Jsonb(finding)))
                audit(c, brand, principal.name, "reconciliation_unknown", "destination", {"reason": str(exc)})
            raise
        with connect(self.dsn) as c:
            c.execute("INSERT INTO destination_observations(brand,body,hash) VALUES(%s,%s,%s)",
                      (brand, Jsonb(remote), digest(remote)))
            expected = c.execute("SELECT * FROM activation_eligibility WHERE brand=%s", (brand,)).fetchall()
        actual = {(r["person"], r["segment"]): r for r in remote}
        findings = []
        for row in expected:
            target = row["reason"] == "eligible"
            observed = actual.get((row["person"], row["segment"]))
            if target != bool(observed and observed["active"]):
                finding = {"brand": brand, "person": row["person"], "segment": row["segment"],
                           "expected": target, "actual": bool(observed and observed["active"]), "reason": row["reason"]}
                if repair:
                    intent = self.plan(principal, brand, row["person"], row["segment"], target,
                                       observed["seq"] if observed else 0)
                    finding["intent"] = intent["id"]  # Adds still need a separate exact approval.
                findings.append(finding)
        known = {(r["person"], r["segment"]) for r in expected}
        for row in remote:
            if (row["person"], row["segment"]) not in known:
                findings.append({"brand": brand, "person": row["person"], "segment": row["segment"],
                                 "reason": "unknown_destination_identity_manual_exception"})
        with connect(self.dsn) as c:
            c.execute("INSERT INTO reconciliations(brand,body) VALUES(%s,%s)", (brand, Jsonb(findings)))
        return findings
