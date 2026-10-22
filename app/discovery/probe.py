"""Validate candidates against the ATS APIs and promote live boards into companies."""
import asyncio
import re

import httpx

from app.db import connect

PENDING_SQL = """
SELECT id, ats, slug, name, source, guessed FROM company_candidates
WHERE status = ANY(%s) AND source LIKE %s AND (checked_at IS NULL OR checked_at < %s)
ORDER BY id LIMIT %s
"""
UPDATE_SQL = """
UPDATE company_candidates
SET status = %(status)s, board_name = %(board_name)s, jobs_found = %(jobs_found)s, checked_at = now()
WHERE id = %(id)s
"""
PROMOTE_SQL = """
INSERT INTO companies (name, ats, slug, source) VALUES (%(name)s, %(ats)s, %(slug)s, %(source)s)
ON CONFLICT (ats, slug) DO NOTHING
"""


def _words(s):
    return {w for w in re.split(r"[^a-z0-9]+", (s or "").lower()) if len(w) > 2}


def _job_count(payload, key=None):
    jobs = payload[key] if key else payload
    if not isinstance(jobs, list) or any(not isinstance(job, dict) or "id" not in job for job in jobs):
        raise ValueError("invalid ATS jobs payload")
    return len(jobs)


async def _greenhouse(client, slug):
    r = await client.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
    if r.status_code != 200:
        return r.status_code, None, 0
    jobs = _job_count(r.json(), "jobs")
    b = await client.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}")
    return 200, (b.json().get("name") if b.status_code == 200 else None), jobs


async def _lever(client, slug):
    r = await client.get(f"https://api.lever.co/v0/postings/{slug}", params={"mode": "json", "limit": 1})
    return r.status_code, None, (_job_count(r.json()) if r.status_code == 200 else 0)


async def _ashby(client, slug):
    r = await client.get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    return r.status_code, None, (_job_count(r.json(), "jobs") if r.status_code == 200 else 0)


async def _smartrecruiters(client, slug):
    r = await client.get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings", params={"limit": 1})
    if r.status_code != 200:
        return r.status_code, None, 0
    payload = r.json()
    jobs = _job_count(payload, "content")
    name = payload["content"][0]["company"]["name"] if jobs else None
    return 200, name, jobs


async def _amazon(client, slug):
    if slug != "amazon":
        return 404, None, 0
    r = await client.get("https://www.amazon.jobs/en/search.json", params={"country": "USA", "result_limit": 1})
    if r.status_code != 200:
        return r.status_code, None, 0
    payload = r.json()
    if payload.get("error"):
        raise ValueError("Amazon search error")
    return 200, "Amazon", _job_count(payload, "jobs")


PROBES = {"greenhouse": _greenhouse, "lever": _lever, "ashby": _ashby,
          "smartrecruiters": _smartrecruiters, "amazon": _amazon}


def classify(c, code, board_name, jobs):
    if code == 404:
        return "invalid"
    if code != 200:
        return "error"
    # A guessed slug can land on an unrelated company's board. Greenhouse exposes the board
    # name, so require some overlap with the source name.
    if c["guessed"] and board_name and c["name"] and not (_words(board_name) & _words(c["name"])):
        return "mismatch"
    # Lever only returns limit=1 here, so jobs is 0 or 1; that is enough to tell live from empty.
    return "valid" if jobs > 0 else "empty"


async def _check(client, sems, c):
    async with sems[c["ats"]]:
        try:
            code, board_name, jobs = await PROBES[c["ats"]](client, c["slug"])
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
            code, board_name, jobs = None, None, None
        await asyncio.sleep(0.2)
    status = classify(c, code, board_name, jobs or 0)
    return {**c, "status": status, "board_name": board_name, "jobs_found": jobs}


async def run(statuses=("pending",), source="", limit=None, batch=500, concurrency=8):
    if concurrency < 1 or batch < 1 or (limit is not None and limit < 1):
        raise ValueError("concurrency, batch and limit must be positive")
    sems = {ats: asyncio.Semaphore(concurrency) for ats in PROBES}
    totals = {}
    headers = {"User-Agent": "JobRadar/0.1"}
    with connect() as conn:
        started = conn.execute("SELECT now() AS t").fetchone()["t"]
    async with httpx.AsyncClient(timeout=20, headers=headers, follow_redirects=True) as client:
        done = 0
        while limit is None or done < limit:
            n = batch if limit is None else min(batch, limit - done)
            with connect() as conn:
                rows = conn.execute(PENDING_SQL, (list(statuses), source + "%", started, n)).fetchall()
            if not rows:
                break
            results = await asyncio.gather(*(_check(client, sems, c) for c in rows))
            with connect() as conn, conn.cursor() as cur:
                cur.executemany(UPDATE_SQL, results)
                valid = [{**r, "name": r["name"] or r["board_name"] or r["slug"]}
                         for r in results if r["status"] == "valid"]
                if valid:
                    cur.executemany(PROMOTE_SQL, valid)
            for r in results:
                totals[r["status"]] = totals.get(r["status"], 0) + 1
            done += len(rows)
            print(f"probe: {done} checked {totals}", flush=True)
    return totals
