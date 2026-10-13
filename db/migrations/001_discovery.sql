ALTER TABLE companies ADD COLUMN IF NOT EXISTS source TEXT;

CREATE TABLE IF NOT EXISTS company_candidates (
  id BIGSERIAL PRIMARY KEY,
  ats TEXT NOT NULL,
  slug TEXT NOT NULL,
  name TEXT,
  source TEXT NOT NULL,
  guessed BOOLEAN NOT NULL DEFAULT FALSE,
  status TEXT NOT NULL DEFAULT 'pending',
  board_name TEXT,
  jobs_found INT,
  checked_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (ats, slug)
);
CREATE INDEX IF NOT EXISTS company_candidates_status ON company_candidates (status, id);
