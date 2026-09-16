import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .contracts import Refused, digest, identifier, validate_fact
from .coverage import validate_coverage


@contextmanager
def transaction(path, write=True):
    c = sqlite3.connect(path, timeout=15, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=FULL")
    try:
        c.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        yield c
        c.commit()
    except BaseException:
        c.rollback()
        raise
    finally:
        c.close()


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with transaction(self.path) as c:
            c.executescript(Path(__file__).with_name("schema.sql").read_text())
            c.execute("INSERT OR IGNORE INTO meta VALUES ('lineage',?)", (str(uuid4()),))
            c.execute("INSERT OR IGNORE INTO meta VALUES ('active','0')")

    def ingest(self, batch_id, facts):
        identifier(batch_id)
        if not isinstance(facts, list) or not 1 <= len(facts) <= 10000:
            raise Refused("invalid_batch_size")
        for fact in facts:
            validate_fact(fact)
        identities = [(f["source"], f["fact_id"], f["revision"]) for f in facts]
        if len(identities) != len(set(identities)):
            raise Refused("duplicate_revision_in_batch")
        fingerprint = digest(facts)
        with transaction(self.path) as c:
            old = c.execute("SELECT seq,hash FROM batches WHERE batch_id=?", (batch_id,)).fetchone()
            if old:
                if old["hash"] != fingerprint:
                    raise Refused("batch_identity_conflict")
                return old["seq"]
            seq = c.execute("INSERT INTO batches(batch_id,hash,received_at) VALUES (?,?,?) RETURNING seq",
                            (batch_id, fingerprint, datetime.now(UTC).isoformat())).fetchone()[0]
            for fact in facts:
                owner = c.execute("SELECT person_id FROM facts WHERE source=? AND fact_id=? LIMIT 1",
                                  (fact["source"], fact["fact_id"])).fetchone()
                if owner and owner["person_id"] != fact["person_id"]:
                    raise Refused("fact_owner_cannot_change")
                old = c.execute("SELECT hash FROM facts WHERE source=? AND fact_id=? AND revision=?",
                                (fact["source"], fact["fact_id"], fact["revision"])).fetchone()
                if old and old["hash"] != digest(fact):
                    raise Refused("fact_revision_conflict")
                if not old:
                    c.execute("INSERT INTO facts VALUES (?,?,?,?,?,?,?,?,?)", (fact["source"], fact["fact_id"], fact["revision"],
                              fact["person_id"], fact["effective_at"], fact["value"], int(fact["retracted"]), seq, digest(fact)))
        return seq

    def ingest_coverage(self, batch_id, assertion):
        """Replace coverage for the single, whole synthetic activity source at a new K."""
        identifier(batch_id)
        validate_coverage(assertion)
        fingerprint = digest({"activity_coverage": assertion})
        with transaction(self.path) as c:
            old = c.execute("SELECT seq,hash FROM batches WHERE batch_id=?", (batch_id,)).fetchone()
            if old:
                if old["hash"] != fingerprint:
                    raise Refused("batch_identity_conflict")
                return old["seq"]
            seq = c.execute("INSERT INTO batches(batch_id,hash,received_at) VALUES (?,?,?) RETURNING seq",
                            (batch_id, fingerprint, datetime.now(UTC).isoformat())).fetchone()[0]
            old = c.execute("SELECT hash FROM coverage WHERE revision=?", (assertion["revision"],)).fetchone()
            if old and old["hash"] != digest(assertion):
                raise Refused("coverage_revision_conflict")
            if not old:
                c.execute("INSERT INTO coverage VALUES (?,?,?,?,?,?)",
                          (assertion["revision"], assertion["covered_after"], assertion["covered_through"],
                           int(assertion["retracted"]), seq, digest(assertion)))
        return seq

    def head(self):
        with transaction(self.path, False) as c:
            return c.execute("SELECT COALESCE(MAX(seq),0) FROM batches").fetchone()[0]

    def get(self, generation=None):
        with transaction(self.path, False) as c:
            if generation is None:
                generation = int(c.execute("SELECT value FROM meta WHERE key='active'").fetchone()[0])
            row = c.execute("SELECT body FROM generations WHERE id=?", (generation,)).fetchone()
            return json.loads(row["body"]) if row else None
