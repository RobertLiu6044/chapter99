-- Chapter 99 — starting schema.
--
-- Script to seed database schema. Add columns, tables, etc as needed.
-- Should be runnable from a clean install. Should define the schema
-- needed for parts 1, 2, and 3.
--
-- Rerunnable: it drops what it creates first, so applying it twice is safe.
-- Postgres has no CREATE OR REPLACE TABLE, so a clean schema means dropping.
-- That also means applying this wipes your parsed data; it is a schema reset,
-- not a migration.
--
--   ./setup.sh
--
-- Order matters on the way down: rule_edge references rule.

BEGIN;

DROP TABLE IF EXISTS special CASCADE;
DROP TABLE IF EXISTS rule_edge CASCADE;
DROP TABLE IF EXISTS rule CASCADE;
DROP TABLE IF EXISTS hts_base CASCADE;
DROP TYPE IF EXISTS hts_code CASCADE;

-- Dotted HTS code as an integer 4-tuple, e.g.
--   0101           → (101, -1, -1, -1)
--   0101.21        → (101,  21, -1, -1)
--   0101.21.00     → (101,  21,  0, -1)
--   0101.21.00.10  → (101,  21,  0, 10)
--   9903.01.01     → (9903, 1, 1, -1)
-- Missing trailing segments are -1 (composite fields used in a PK cannot be NULL).
--
-- Prefix queries on a column `code hts_code`:
--   all under 0101:          WHERE (code).h0 = 101
--   all under 0101.21:       WHERE (code).h0 = 101 AND (code).h1 = 21
--   exact 0101.21.00.10:     WHERE code = ROW(101, 21, 0, 10)::hts_code
CREATE TYPE hts_code AS (
  h0 integer,
  h1 integer,
  h2 integer,
  h3 integer
);

-- Chapters 1-97: what Chapter 99 points back at.
CREATE TABLE hts_base (
  code          hts_code PRIMARY KEY,
  hts           text NOT NULL UNIQUE,
  description   text,
  mfn_rate      numeric,
  mfn_rate_unit text,
  CHECK (
    ((code).h1 = -1 AND (code).h2 = -1 AND (code).h3 = -1)
    OR ((code).h1 >= 0 AND (code).h2 = -1 AND (code).h3 = -1)
    OR ((code).h1 >= 0 AND (code).h2 >= 0 AND (code).h3 = -1)
    OR ((code).h1 >= 0 AND (code).h2 >= 0 AND (code).h3 >= 0)
  )
);

-- btree on the tuple segments: supports equality and left-prefix matches
--   (h0), (h0,h1), (h0,h1,h2), (h0,h1,h2,h3).
-- The PRIMARY KEY btree on `code` only helps whole-tuple equality; field
-- accessors like (code).h0 do not use it. GIN/GiST are the wrong tool here.
CREATE INDEX hts_base_code_prefix_idx
  ON hts_base
  USING btree (((code).h0), ((code).h1), ((code).h2), ((code).h3));

-- create a fuzzy search index on descriptions
CREATE INDEX hts_base_description_fuzzy_idx ON hts_base USING GIN (description gin_trgm_ops);

-- Chapter 99 provisions. rate_kind is the operator, rate_value the operand:
-- 'additive' with 25 means "base rate + 25", which a single numeric column
-- could not express.
CREATE TABLE rule (
  code        hts_code PRIMARY KEY,
  hts         text NOT NULL UNIQUE,
  subchapter  text NOT NULL,
  description text NOT NULL,
  rate_kind   text NOT NULL
    CHECK (rate_kind IN ('free','additive','ad_valorem','no_change','specific','other')),
  rate_value  numeric,
  note_ref    text,
  CHECK (
    ((code).h1 = -1 AND (code).h2 = -1 AND (code).h3 = -1)
    OR ((code).h1 >= 0 AND (code).h2 = -1 AND (code).h3 = -1)
    OR ((code).h1 >= 0 AND (code).h2 >= 0 AND (code).h3 = -1)
    OR ((code).h1 >= 0 AND (code).h2 >= 0 AND (code).h3 >= 0)
  )
);

-- The two relationships Chapter 99 states in prose.
--
-- target_hts is deliberately not a foreign key: a provision can name a base
-- code that no longer exists in the current revision, and those are worth
-- recording rather than dropping.
CREATE TABLE rule_edge (
  source_hts hts_code NOT NULL REFERENCES rule(code) ON DELETE CASCADE,
  edge_type  text NOT NULL CHECK (edge_type IN ('references','excludes')),
  target_hts hts_code NOT NULL,
  PRIMARY KEY (source_hts, edge_type, target_hts)
);

CREATE INDEX rule_edge_target_idx ON rule_edge (target_hts, edge_type);

-- Special provisions
CREATE TABLE special (
  hts text NOT NULL REFERENCES rule(hts) ON DELETE CASCADE,
  special_tag text NOT NULL,
  special_rate numeric NOT NULL,
  PRIMARY KEY (hts, special_tag)
);

CREATE INDEX special_hts_idx ON special (hts);

COMMIT;
