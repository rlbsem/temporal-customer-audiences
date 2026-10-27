"""Durable PG inbox to disposable, brand-isolated original SQLite evaluation."""
import tempfile
from pathlib import Path

from psycopg.types.json import Jsonb

from temporal_audiences.contracts import Refused, digest, identifier, integer, validate_fact
from temporal_audiences.coverage import validate_coverage
from temporal_audiences.engine import build
from temporal_audiences.store import Store

from .db import audit, connect, lock


class Operations:
    def __init__(self, dsn):
        self.dsn = dsn

    @staticmethod
    def replay(rows, folder):
        store = Store(Path(folder) / "engine.sqlite")
        for row in rows:
            fn = store.ingest if row["kind"] == "facts" else store.ingest_coverage
            assert fn(row["batch"], row["body"]) == row["seq"]
        return store

    def ingest(self, principal, brand, batch, kind, body):
        principal.require(brand, {"source"})
        identifier(batch)
        if kind not in {"facts", "coverage"}:
            raise Refused("invalid_source_kind")
        if kind == "facts":
            if not isinstance(body, list) or not 1 <= len(body) <= 10000:
                raise Refused("invalid_batch_size")
            for fact in body:
                validate_fact(fact)
        else:
            validate_coverage(body)
        streams = {fact.get("source") for fact in body} if kind == "facts" else {"coverage"}
        if not streams.issubset(principal.streams):
            raise Refused("source_stream_authority_denied")
        with connect(self.dsn) as c:
            lock(c, brand)
            old = c.execute("SELECT * FROM inbox WHERE brand=%s AND batch=%s", (brand, batch)).fetchone()
            if old:
                if old["kind"] != kind or old["hash"] != digest(body):
                    raise Refused("batch_identity_conflict")
                return old["seq"]
            rows = c.execute("SELECT * FROM inbox WHERE brand=%s ORDER BY seq", (brand,)).fetchall()
            if kind == "facts":
                for fact in body:
                    if not c.execute("SELECT 1 FROM subjects WHERE brand=%s AND person=%s",
                                     (brand, fact.get("person_id"))).fetchone():
                        raise Refused("unregistered_scoped_subject")
            with tempfile.TemporaryDirectory() as folder:
                store = self.replay(rows, folder)
                fn = store.ingest if kind == "facts" else store.ingest_coverage
                seq = fn(batch, body)  # Original validation/revision semantics, before PG commit.
            c.execute("INSERT INTO inbox VALUES(%s,%s,%s,%s,%s,%s)",
                      (brand, seq, batch, kind, Jsonb(body), digest(body)))
            audit(c, brand, principal.name, "source_admitted", batch, {"seq": seq, "hash": digest(body)})
            return seq

    def publish(self, principal, brand, request, clock, known=None, historical=False):
        principal.require(brand, {"controller"})
        identifier(request)
        integer(clock)
        with connect(self.dsn) as c:
            lock(c, brand)
            state = c.execute("SELECT * FROM brands WHERE brand=%s", (brand,)).fetchone()
            if not state:
                raise Refused("unknown_brand")
            rows = c.execute("SELECT * FROM inbox WHERE brand=%s ORDER BY seq", (brand,)).fetchall()
            head = len(rows)
            known = head if known is None else known
            integer(known)
            if known > head or (not historical and (known != head or clock < state["clock"])):
                raise Refused("current_requires_latest_knowledge_and_monotone_clock")
            mode = "historical" if historical else "current"
            old = c.execute("SELECT * FROM publications WHERE brand=%s AND request=%s", (brand, request)).fetchone()
            if old:
                if (old["clock"], old["known"], old["mode"]) != (clock, known, mode):
                    raise Refused("publication_identity_conflict")
                return old
            with tempfile.TemporaryDirectory() as folder:
                store = self.replay(rows, folder)
                result = build(store, request, clock, known=known, mode=mode, force_full=True)
            # A replayed cache's random lineage is not an operational effect identity.
            publication = digest({"brand": brand, "request": request, "clock": clock,
                                  "known": known, "mode": mode, "rules": result["rules"],
                                  "implementation": result["implementation"]})
            c.execute("INSERT INTO publications VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                      (publication, brand, request, mode, clock, known, digest(result["rules"]),
                       result["implementation"], Jsonb(result), digest(result)))
            for person, row in result["people"].items():
                for segment, member in row["membership"].items():
                    c.execute("INSERT INTO decisions VALUES(%s,%s,%s,%s,%s,%s,%s)",
                              (publication, brand, person, segment, member,
                               segment != "quiet_trial" or result["activity_coverage"]["eligible"], Jsonb(row)))
            if not historical:
                c.execute("UPDATE brands SET clock=%s WHERE brand=%s", (clock, brand))
                c.execute("INSERT INTO active VALUES(%s,%s) ON CONFLICT(brand) DO UPDATE SET publication=excluded.publication",
                          (brand, publication))
            audit(c, brand, principal.name, "publication_" + mode, publication,
                  {"clock": clock, "known": known, "hash": digest(result)})
            return c.execute("SELECT * FROM publications WHERE id=%s", (publication,)).fetchone()

    def permission(self, principal, brand, person, revision, allowed, valid_from, expires,
                   suppressed=False, channel="email", purpose="trial_help"):
        principal.require(brand, {"privacy"})
        integer(revision, 1)
        integer(valid_from)
        integer(expires)
        if type(allowed) is not bool or type(suppressed) is not bool or expires <= valid_from:
            raise Refused("invalid_permission")
        if channel not in {"email", "sms"} or purpose not in {"trial_help", "news"}:
            raise Refused("unsupported_permission_scope")
        body = dict(brand=brand, person=person, revision=revision, allowed=allowed,
                    valid_from=valid_from, expires=expires, suppressed=suppressed, channel=channel, purpose=purpose)
        with connect(self.dsn) as c:
            lock(c, brand)
            latest = c.execute("SELECT * FROM permissions WHERE brand=%s AND person=%s AND channel=%s AND purpose=%s ORDER BY revision DESC LIMIT 1",
                               (brand, person, channel, purpose)).fetchone()
            if latest and latest["revision"] == revision and latest["hash"] == digest(body):
                return latest["id"]
            if revision != (latest["revision"] + 1 if latest else 1):
                raise Refused("permission_revision_conflict_or_gap")
            row = c.execute("INSERT INTO permissions(brand,person,channel,purpose,revision,allowed,suppressed,valid_from,expires,body,hash,actor) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                            (brand, person, channel, purpose, revision, allowed, suppressed, valid_from,
                             expires, Jsonb(body), digest(body), principal.name)).fetchone()
            audit(c, brand, principal.name, "permission_revision", str(row["id"]), body)
            return row["id"]
