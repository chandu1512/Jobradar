CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE companies (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  ats TEXT NOT NULL,
  slug TEXT NOT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  last_crawled_at TIMESTAMPTZ,
  last_successful_crawl_at TIMESTAMPTZ,
  last_status TEXT,
  source TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (ats, slug)
);

CREATE TABLE jobs (
  id BIGSERIAL PRIMARY KEY,
  company_id INT NOT NULL REFERENCES companies(id),
  ext_id TEXT NOT NULL,
  title TEXT NOT NULL,
  location TEXT,
  url TEXT NOT NULL,
  posted_at TIMESTAMPTZ,
  first_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  discovered_live BOOLEAN NOT NULL DEFAULT FALSE,
  raw JSONB,
  signals JSONB NOT NULL DEFAULT '{}',
  previous_successful_crawl_at TIMESTAMPTZ,
  is_us BOOLEAN,
  states TEXT[] NOT NULL DEFAULT '{}',
  remote BOOLEAN NOT NULL DEFAULT FALSE,
  UNIQUE (company_id, ext_id)
);
CREATE INDEX jobs_active_recent ON jobs (first_seen DESC) WHERE is_active;
CREATE INDEX jobs_title_trgm ON jobs USING gin (title gin_trgm_ops);
CREATE INDEX jobs_us_recent ON jobs (first_seen DESC) WHERE is_active AND is_us;
CREATE INDEX jobs_states ON jobs USING gin (states);

CREATE TABLE crawl_runs (
  id BIGSERIAL PRIMARY KEY,
  company_id INT NOT NULL REFERENCES companies(id),
  status TEXT NOT NULL,
  jobs_found INT,
  new_jobs INT,
  duration_ms INT,
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- status: pending | valid | empty | invalid | mismatch | error
CREATE TABLE company_candidates (
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
CREATE INDEX company_candidates_status ON company_candidates (status, id);
CREATE TABLE IF NOT EXISTS workspaces (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  token_hash TEXT UNIQUE NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS applications (
  id BIGSERIAL PRIMARY KEY,
  workspace_id UUID NOT NULL REFERENCES workspaces(id),
  company TEXT NOT NULL,
  title TEXT NOT NULL,
  url TEXT NOT NULL,
  canonical_url TEXT NOT NULL,
  company_key TEXT NOT NULL,
  title_key TEXT NOT NULL,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (workspace_id, canonical_url)
);
CREATE INDEX IF NOT EXISTS applications_title_match ON applications(workspace_id,company_key,title_key);
CREATE TABLE IF NOT EXISTS sponsor_history (
  company_id INT NOT NULL REFERENCES companies(id),
  fiscal_year INT NOT NULL CHECK (fiscal_year BETWEEN 2000 AND 2100),
  filings_count INT NOT NULL CHECK (filings_count >= 0),
  record_type TEXT NOT NULL CHECK (record_type IN ('lca_filings','petition_approvals','user_ranked_history')),
  source_url TEXT NOT NULL,
  employer_name TEXT NOT NULL,
  imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY(company_id, fiscal_year, record_type, source_url)
);
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS reactivated_at TIMESTAMPTZ;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS reactivation_count INT NOT NULL DEFAULT 0;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS canonical_url TEXT;
CREATE INDEX IF NOT EXISTS jobs_inactive_company_title ON jobs(company_id,title) WHERE NOT is_active;
