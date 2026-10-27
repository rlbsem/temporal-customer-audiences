CREATE TABLE brands(brand text PRIMARY KEY, legal_entity text NOT NULL UNIQUE, clock bigint NOT NULL CHECK(clock>=0));
CREATE TABLE subjects(brand text REFERENCES brands, person text NOT NULL, PRIMARY KEY(brand,person));
CREATE TABLE inbox(brand text REFERENCES brands, seq bigint NOT NULL, batch text NOT NULL,
 kind text NOT NULL CHECK(kind IN ('facts','coverage')), body jsonb NOT NULL, hash text NOT NULL,
 PRIMARY KEY(brand,seq), UNIQUE(brand,batch));
CREATE TABLE publications(id text PRIMARY KEY, brand text REFERENCES brands, request text NOT NULL,
 mode text NOT NULL CHECK(mode IN ('current','historical')), clock bigint NOT NULL, known bigint NOT NULL,
 rule_hash text NOT NULL, implementation text NOT NULL, body jsonb NOT NULL, hash text NOT NULL,
 UNIQUE(brand,request), UNIQUE(brand,id));
CREATE TABLE active(brand text PRIMARY KEY REFERENCES brands, publication text NOT NULL,
 FOREIGN KEY(brand,publication) REFERENCES publications(brand,id));
CREATE TABLE decisions(publication text NOT NULL,brand text NOT NULL,person text NOT NULL,
 segment text NOT NULL CHECK(segment IN ('engaged_trial','quiet_trial')),member boolean NOT NULL,
 covered boolean NOT NULL,evidence jsonb NOT NULL,
 PRIMARY KEY(publication,brand,person,segment),FOREIGN KEY(brand,person) REFERENCES subjects,
 FOREIGN KEY(brand,publication) REFERENCES publications(brand,id));
CREATE TABLE permissions(id bigserial PRIMARY KEY,brand text NOT NULL,person text NOT NULL,
 channel text NOT NULL,purpose text NOT NULL,revision bigint NOT NULL CHECK(revision>0),
 allowed boolean NOT NULL,suppressed boolean NOT NULL,valid_from bigint NOT NULL,expires bigint NOT NULL,
 body jsonb NOT NULL,hash text NOT NULL,actor text NOT NULL,
 CHECK(expires>valid_from),UNIQUE(brand,person,channel,purpose,revision),
 FOREIGN KEY(brand,person) REFERENCES subjects);
CREATE INDEX permission_latest ON permissions(brand,person,channel,purpose,revision DESC);
CREATE TABLE intents(id text PRIMARY KEY,brand text NOT NULL,person text NOT NULL,segment text NOT NULL,
 channel text NOT NULL,purpose text NOT NULL,seq bigint NOT NULL CHECK(seq>0),desired boolean NOT NULL,
 payload jsonb NOT NULL,hash text NOT NULL,authority text NOT NULL,approval jsonb,
 state text NOT NULL CHECK(state IN ('pending','approved','inflight','uncertain','confirmed','blocked','excepted')),
 attempts integer NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 3),
 checks integer NOT NULL DEFAULT 0 CHECK(checks BETWEEN 0 AND 3),
 lease text,lease_until timestamptz,receipt jsonb,reason text,
 UNIQUE(brand,person,segment,channel,purpose,seq),FOREIGN KEY(brand,person) REFERENCES subjects);
CREATE INDEX dispatch_ready ON intents(state,lease_until);
CREATE TABLE heads(brand text,person text,segment text,channel text,purpose text,seq bigint NOT NULL,
 intent text NOT NULL REFERENCES intents,PRIMARY KEY(brand,person,segment,channel,purpose));
CREATE TABLE audit(id bigserial PRIMARY KEY,brand text NOT NULL,actor text NOT NULL,
 action text NOT NULL,reference text NOT NULL,body jsonb NOT NULL,observed_at timestamptz DEFAULT clock_timestamp());
CREATE TABLE reconciliations(id bigserial PRIMARY KEY,brand text NOT NULL,body jsonb NOT NULL,
 observed_at timestamptz DEFAULT clock_timestamp());
CREATE TABLE destination_observations(id bigserial PRIMARY KEY,brand text NOT NULL REFERENCES brands,
 body jsonb NOT NULL,hash text NOT NULL,observed_at timestamptz DEFAULT clock_timestamp());
CREATE TABLE acceptance_reports(id text PRIMARY KEY,body jsonb NOT NULL,source_hash text NOT NULL);
CREATE FUNCTION immutable_record() RETURNS trigger LANGUAGE plpgsql AS $$
 BEGIN RAISE EXCEPTION 'immutable_record'; END $$;
CREATE TRIGGER immutable_inbox BEFORE UPDATE OR DELETE ON inbox FOR EACH ROW EXECUTE FUNCTION immutable_record();
CREATE TRIGGER immutable_publications BEFORE UPDATE OR DELETE ON publications FOR EACH ROW EXECUTE FUNCTION immutable_record();
CREATE TRIGGER immutable_decisions BEFORE UPDATE OR DELETE ON decisions FOR EACH ROW EXECUTE FUNCTION immutable_record();
CREATE TRIGGER immutable_permissions BEFORE UPDATE OR DELETE ON permissions FOR EACH ROW EXECUTE FUNCTION immutable_record();
CREATE TRIGGER immutable_audit BEFORE UPDATE OR DELETE ON audit FOR EACH ROW EXECUTE FUNCTION immutable_record();
CREATE TRIGGER immutable_destination_observation BEFORE UPDATE OR DELETE ON destination_observations FOR EACH ROW EXECUTE FUNCTION immutable_record();
CREATE TRIGGER immutable_acceptance_report BEFORE UPDATE OR DELETE ON acceptance_reports FOR EACH ROW EXECUTE FUNCTION immutable_record();
CREATE FUNCTION frozen_intent() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF (NEW.id,NEW.brand,NEW.person,NEW.segment,NEW.channel,NEW.purpose,NEW.seq,NEW.desired,NEW.payload,NEW.hash,NEW.authority)
 IS DISTINCT FROM (OLD.id,OLD.brand,OLD.person,OLD.segment,OLD.channel,OLD.purpose,OLD.seq,OLD.desired,OLD.payload,OLD.hash,OLD.authority)
 THEN RAISE EXCEPTION 'frozen_intent'; END IF; RETURN NEW; END $$;
CREATE TRIGGER frozen_intent BEFORE UPDATE ON intents FOR EACH ROW EXECUTE FUNCTION frozen_intent();
CREATE VIEW current_audience AS
 SELECT d.*,p.clock,p.known,p.rule_hash,p.implementation FROM active a
 JOIN publications p ON p.id=a.publication AND p.brand=a.brand
 JOIN decisions d ON d.publication=p.id AND d.brand=p.brand;
CREATE VIEW activation_eligibility AS
 SELECT s.brand,s.person,sg.segment,'email'::text AS channel,'trial_help'::text AS purpose,
 d.publication,d.rule_hash,d.member,d.covered,b.clock,pr.id AS permission_id,
 CASE WHEN d.publication IS NULL THEN 'missing_publication'
 WHEN d.clock<>b.clock OR d.known<>COALESCE((SELECT max(i.seq) FROM inbox i WHERE i.brand=s.brand),0) THEN 'stale_publication'
 WHEN NOT d.member THEN 'not_member'
 WHEN NOT d.covered THEN 'incomplete_coverage'
 WHEN pr.id IS NULL THEN 'missing_permission'
 WHEN pr.suppressed THEN 'suppressed'
 WHEN NOT pr.allowed THEN 'withdrawn'
 WHEN pr.valid_from>b.clock THEN 'permission_not_yet_valid'
 WHEN pr.expires<=b.clock THEN 'permission_expired'
 ELSE 'eligible' END AS reason
 FROM subjects s JOIN brands b USING(brand)
 CROSS JOIN (VALUES('engaged_trial'),('quiet_trial')) sg(segment)
 LEFT JOIN current_audience d ON (d.brand,d.person,d.segment)=(s.brand,s.person,sg.segment)
 LEFT JOIN LATERAL(SELECT * FROM permissions p WHERE (p.brand,p.person,p.channel,p.purpose)=
 (s.brand,s.person,'email','trial_help') ORDER BY revision DESC LIMIT 1) pr ON true;
CREATE VIEW permission_withdrawals AS SELECT * FROM permissions WHERE NOT allowed OR suppressed;
CREATE VIEW coverage_exceptions AS SELECT * FROM activation_eligibility WHERE reason='incomplete_coverage';
CREATE VIEW historical_decisions AS SELECT d.*,p.mode,p.clock,p.known FROM decisions d JOIN publications p ON p.id=d.publication;
CREATE VIEW delivery_exceptions AS SELECT * FROM intents WHERE state IN ('uncertain','excepted','blocked');
CREATE VIEW synchronization_status AS SELECT brand,state,count(*) AS operations FROM intents GROUP BY brand,state;
CREATE VIEW source_observations AS
 SELECT i.brand,i.seq,f->>'source' AS source,f->>'fact_id' AS fact_id,(f->>'revision')::bigint AS revision,
 f->>'person_id' AS person,f AS body FROM inbox i
 CROSS JOIN LATERAL jsonb_array_elements(CASE WHEN i.kind='facts' THEN i.body ELSE '[]'::jsonb END) f;
CREATE VIEW source_fact_versions AS SELECT DISTINCT ON(brand,source,fact_id,revision) *
 FROM source_observations ORDER BY brand,source,fact_id,revision,seq;
CREATE VIEW latest_destination_state AS
 SELECT o.brand,o.id AS observation,o.observed_at,r->>'person' AS person,r->>'segment' AS segment,
 (r->>'seq')::bigint AS seq,(r->>'active')::boolean AS active
 FROM (SELECT DISTINCT ON(brand) * FROM destination_observations ORDER BY brand,id DESC) o
 CROSS JOIN LATERAL jsonb_array_elements(o.body) r;
CREATE VIEW destination_sync AS
 SELECT e.brand,e.person,e.segment,e.reason,(e.reason='eligible') AS authorized,
 o.observation,o.observed_at,o.active AS receiver_active,
 CASE WHEN NOT EXISTS(SELECT 1 FROM destination_observations d WHERE d.brand=e.brand) THEN 'unobserved'
 WHEN (e.reason='eligible')=coalesce(o.active,false) THEN 'matched_last_observation' ELSE 'out_of_sync' END AS status
 FROM activation_eligibility e LEFT JOIN latest_destination_state o
 ON (e.brand,e.person,e.segment)=(o.brand,o.person,o.segment);
CREATE VIEW reconciliation_findings AS SELECT r.id,r.brand,r.observed_at,f AS finding
 FROM reconciliations r CROSS JOIN LATERAL jsonb_array_elements(r.body) f;
