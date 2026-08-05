-- Append-only by convention and by index. Filings are facts the SEC published;
-- nothing here ever updates one, and INSERT OR IGNORE makes a repeated day a
-- no-op rather than a duplicate.

CREATE TABLE IF NOT EXISTS filings (
  accession    TEXT PRIMARY KEY,   -- the SEC's own identifier
  form         TEXT NOT NULL,
  cik          TEXT NOT NULL,      -- zero-padded to 10, so joins are exact
  company      TEXT NOT NULL,
  filed        TEXT NOT NULL,      -- YYYY-MM-DD, the date it became knowable
  path         TEXT NOT NULL,
  collected_at TEXT NOT NULL       -- when we saw it, never confused with above
);

CREATE INDEX IF NOT EXISTS idx_filings_form_filed ON filings (form, filed DESC);
CREATE INDEX IF NOT EXISTS idx_filings_cik        ON filings (cik, filed DESC);

-- One row per collected day, so a gap is visible rather than inferred from
-- absence. A day that legitimately had no filings and a day we failed to
-- collect must not look identical.
CREATE TABLE IF NOT EXISTS runs (
  day    TEXT PRIMARY KEY,
  rows   INTEGER NOT NULL,
  detail TEXT NOT NULL,
  ran_at TEXT NOT NULL
);
