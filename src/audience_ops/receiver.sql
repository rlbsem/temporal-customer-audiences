CREATE TABLE effects(id text PRIMARY KEY,brand text NOT NULL,payload jsonb NOT NULL,hash text NOT NULL,
 receipt jsonb NOT NULL,created_at timestamptz DEFAULT clock_timestamp());
CREATE TABLE records(id text PRIMARY KEY REFERENCES effects,body jsonb NOT NULL,hash text NOT NULL);
CREATE TABLE membership(brand text,person text,segment text,channel text,purpose text,
 seq bigint NOT NULL CHECK(seq>=0),active boolean NOT NULL,effect text,
 PRIMARY KEY(brand,person,segment,channel,purpose));
CREATE TABLE requests(id bigserial PRIMARY KEY,brand text NOT NULL,effect text NOT NULL,
 result text NOT NULL,observed_at timestamptz DEFAULT clock_timestamp());
CREATE TABLE faults(brand text,person text,mode text NOT NULL,remaining integer NOT NULL,
 PRIMARY KEY(brand,person));
CREATE FUNCTION immutable_record() RETURNS trigger LANGUAGE plpgsql AS $$
 BEGIN RAISE EXCEPTION 'immutable_record'; END $$;
CREATE TRIGGER immutable_effect BEFORE UPDATE OR DELETE ON effects FOR EACH ROW EXECUTE FUNCTION immutable_record();
CREATE TRIGGER immutable_receipt_record BEFORE UPDATE OR DELETE ON records FOR EACH ROW EXECUTE FUNCTION immutable_record();
