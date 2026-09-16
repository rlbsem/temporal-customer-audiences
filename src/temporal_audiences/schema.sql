CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS batches(seq INTEGER PRIMARY KEY AUTOINCREMENT,batch_id TEXT UNIQUE NOT NULL,
  hash TEXT NOT NULL,received_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS facts(source TEXT NOT NULL,fact_id TEXT NOT NULL,revision INTEGER NOT NULL,
  person_id TEXT NOT NULL,effective_at INTEGER NOT NULL,value TEXT NOT NULL,retracted INTEGER NOT NULL,
  known_seq INTEGER NOT NULL REFERENCES batches(seq),hash TEXT NOT NULL,PRIMARY KEY(source,fact_id,revision));
CREATE INDEX IF NOT EXISTS person_knowledge ON facts(person_id,known_seq);
CREATE INDEX IF NOT EXISTS changed_subjects ON facts(known_seq,person_id);
CREATE TABLE IF NOT EXISTS coverage(revision INTEGER PRIMARY KEY,covered_after INTEGER NOT NULL,
  covered_through INTEGER NOT NULL,retracted INTEGER NOT NULL,known_seq INTEGER NOT NULL REFERENCES batches(seq),
  hash TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS coverage_no_update BEFORE UPDATE ON coverage BEGIN SELECT RAISE(ABORT,'immutable coverage'); END;
CREATE TRIGGER IF NOT EXISTS coverage_no_delete BEFORE DELETE ON coverage BEGIN SELECT RAISE(ABORT,'immutable coverage'); END;
CREATE TABLE IF NOT EXISTS generations(id INTEGER PRIMARY KEY AUTOINCREMENT,run_key TEXT UNIQUE NOT NULL,
  request_hash TEXT NOT NULL,mode TEXT NOT NULL,body TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS facts_no_update BEFORE UPDATE ON facts BEGIN SELECT RAISE(ABORT,'immutable facts'); END;
CREATE TRIGGER IF NOT EXISTS facts_no_delete BEFORE DELETE ON facts BEGIN SELECT RAISE(ABORT,'immutable facts'); END;
CREATE TRIGGER IF NOT EXISTS batches_no_update BEFORE UPDATE ON batches BEGIN SELECT RAISE(ABORT,'immutable batches'); END;
CREATE TRIGGER IF NOT EXISTS batches_no_delete BEFORE DELETE ON batches BEGIN SELECT RAISE(ABORT,'immutable batches'); END;
CREATE TRIGGER IF NOT EXISTS generations_no_update BEFORE UPDATE ON generations BEGIN SELECT RAISE(ABORT,'immutable generation'); END;
CREATE TRIGGER IF NOT EXISTS generations_no_delete BEFORE DELETE ON generations BEGIN SELECT RAISE(ABORT,'immutable generation'); END;
