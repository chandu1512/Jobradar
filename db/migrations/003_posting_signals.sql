ALTER TABLE companies ADD COLUMN IF NOT EXISTS last_successful_crawl_at TIMESTAMPTZ;
UPDATE companies c SET last_successful_crawl_at = r.last_ok
FROM (SELECT company_id, max(created_at) AS last_ok FROM crawl_runs WHERE status='ok' GROUP BY company_id) r
WHERE c.id=r.company_id AND c.last_successful_crawl_at IS NULL;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS signals JSONB NOT NULL DEFAULT '{}';
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS previous_successful_crawl_at TIMESTAMPTZ;
