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
