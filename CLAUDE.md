# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Goal

Job aggregator that surfaces fresh US openings from companies of every size within minutes of posting, with direct apply links. Niche: new grad and international student roles, with visa sponsorship prediction. Long term it grows into a serious AI/ML system.

## Running

Everything runs via Docker Compose (OrbStack on macOS). Services: `postgres`, `redis`, `scheduler`, `worker`, `api` on :8000.

- Start: `docker compose up -d --build`
- Seed companies from `data/companies.csv`: `docker compose run --rm api python -m app.seed` (path is relative to repo root)
- Scale crawlers: `docker compose up -d --scale worker=4`
- psql: `docker compose exec postgres psql -U jobradar`
- Company discovery (`app/discovery/`): `docker compose run --rm api python -m app.discovery collect {commoncrawl,yc,sec}`, then `... probe [--source commoncrawl] [--limit N]`, then `... stats`. Candidates land in `company_candidates`; probe promotes boards with at least one open job into `companies`. `sec` needs `SEC_USER_AGENT` set to a name plus contact email.
- Web UI: `http://localhost:8000/` (`app/static/index.html`, vanilla JS). Live updates come over SSE at `/jobs/stream`, which tails `jobs:new`.
- After changing `app/location.py`: `docker compose run --rm api python -m app.backfill_location`.
- App code is baked into the image (`COPY . .`), so run `docker compose build` after code changes before `docker compose run`.

Lint: `docker run --rm -v "$PWD":/src -w /src ghcr.io/astral-sh/ruff:0.6.9 check .` (config in `ruff.toml`; ruff is not installed on the host or in `requirements.txt`). Discovery tests: `docker compose run --rm --no-deps api python -m unittest discover -s tests -v` (build the API image first). Tests use HTTP fixtures, without public requests or database writes.

## Gotchas

- `db/schema.sql` runs only when the `pgdata` volume is first created. For schema changes, add a file under `db/migrations/`, apply it with `docker compose exec -T postgres psql -U jobradar < db/migrations/NNN_name.sql`, and mirror the change in `schema.sql` for fresh installs. `docker compose down -v` destroys data.
- Pipeline: scheduler (every 60s) enqueues companies not crawled within `CRAWL_INTERVAL_MIN` to Redis stream `crawl:tasks`, guarded by an `inflight:{company_id}` key (SET NX EX 600). Workers (consumer group `crawlers`) fetch, upsert into `jobs` (`RETURNING (xmax = 0)` detects inserts), log to `crawl_runs`, and publish new job IDs to `jobs:new`. The worker must always delete the inflight key.
- A company's first crawl is a backfill: jobs get `discovered_live = FALSE` and are not published to `jobs:new`. `/stats` latency metrics depend on this.
- Job deactivation (`last_seen < now()`) relies on the upserts and the deactivate UPDATE sharing one transaction (same `now()`). Don't split them across connections or transactions.
- Worker Redis client needs `socket_timeout` above the XREADGROUP `block` (5000 ms) plus the retry loop around `xreadgroup`; without them idle workers crash with `TimeoutError`.
- Lever slugs are case sensitive; Greenhouse and Ashby slugs are lowercased on discovery. Name guessed candidates (yc, sec) can hit an unrelated company's board; only Greenhouse exposes a board name to check against.
- Location normalization (`app/location.py`) is rule based: `is_us` is TRUE, FALSE, or NULL (unknown, e.g. bare "Remote"). `/jobs` defaults to `us=true`, so NULL rows are hidden. Bare two letter codes lose to a foreign word in the same segment ("Toronto, ON, CA").
- `level=newgrad|intern` on `/jobs` is a title regex in `app/api.py` with a senior title exclusion; it is a placeholder for a learned seniority classifier.
- Adding an ATS: add a fetcher in `app/fetchers.py` returning dicts with `ext_id, title, location, url, posted_at, raw`, and register it in `FETCHERS`. The `ats` column value must match the key. For discovery, also add a probe in `app/discovery/probe.py` and its board host to `CC_HOSTS` in `app/discovery/sources.py`.

## Roadmap

1. Company discovery: grow from 7 companies to thousands (YC list, SEC EDGAR, state registries, Common Crawl links to Greenhouse/Lever/Ashby boards). Validate each slug by probing the ATS API before inserting.
2. Workday and SmartRecruiters fetchers.
3. ~~US location filter and normalized state field.~~ Done (rule based). Web UI with live SSE feed done.
4. Reliability: XAUTOCLAIM for pending messages from dead workers, per ATS rate limiting.
5. Alerts consumer on `jobs:new` (email first), then a frontend.

Later: dedup (MinHash plus embeddings), ghost job detector, O*NET title normalization, skill extraction, H1B sponsorship predictor on DOL LCA data, hybrid search with cross encoder reranker, resume matching, agentic search and resume tailoring, MLOps.

## Git

Solo project: commit directly to `main`.

## Company discovery architecture

- `app/discovery/sources.py` owns collection and slug normalization. Common Crawl supplies observed board URLs; YC and SEC supply company names used to generate guesses for each supported ATS. These sources do not guarantee US coverage; job location filtering happens after crawling.
- `app/discovery/__main__.py` writes candidates in batches of 1,000. The `(ats, slug)` unique key makes repeated collection safe. Counts report candidates offered, not newly inserted rows. The first source retained for a candidate is its provenance.
- `app/discovery/probe.py` validates batches of 500 with a separate concurrency semaphore for each ATS. A semaphore caps simultaneous requests; this is not a strict requests per second rate limit. Each request also has a short pacing delay.
- Probe states are `pending`, `valid`, `empty`, `invalid`, `mismatch`, and `error`. Only `valid` boards are promoted. Candidate updates and company promotion share a transaction. Malformed responses become `error` without aborting the batch.
- Greenhouse guessed names are compared with the board name. Lever and Ashby lack this identity check, so guessed matches remain a known source of false positives. State registry collection is not implemented yet.
- A probe run captures its start time so retries visit each candidate at most once during that run. Concurrent probe processes are not coordinated; run one probe process at a time.

Start with a bounded discovery run:

```sh
docker compose build api
docker compose run --rm api python -m app.discovery collect commoncrawl --crawls 1 --max-pages 1
docker compose run --rm api python -m app.discovery probe --source commoncrawl --limit 100 --concurrency 4
docker compose run --rm api python -m app.discovery stats
```

Retry transient failures or revisit empty boards with `probe --retry error,empty --limit 100`.
For SEC collection, pass the contact header into the container explicitly:
`docker compose run --rm -e SEC_USER_AGENT='JobRadar your@email.com' api python -m app.discovery collect sec`.
The scheduler automatically picks up promoted companies for their first backfill.

## Job categories

`app/categories.py` owns title rules for role families such as AI/ML, software, data analysis,
healthcare, and trades. A job can match multiple categories. These describe the role rather
than the employer industry. They are rule based and can miss unusual titles; they are not an ML classifier.
`GET /categories` lists category IDs and labels. `/jobs?category=ai_ml` combines the category
with existing filters in SQL before pagination. Both `/jobs` and SSE payloads include `categories`
so the UI applies the same category rules to incoming jobs. Existing jobs work immediately,
without a schema change or backfill. Add patterns compatible with Python and PostgreSQL regexes.
Run the full test suite with the unittest command above.

`/jobs?company=Stripe` adds a separate company name filter. `/companies?q=str` supplies
company name suggestions from active companies, capped at 100 results. The UI combines
company search with category, title, location, and level filters.
