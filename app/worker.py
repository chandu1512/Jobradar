import os
import socket
import time

import httpx
import redis
from psycopg.types.json import Jsonb

from app import config
from app.db import connect
from app.fetchers import FETCHERS
from app.location import from_raw

CONSUMER = os.getenv("HOSTNAME", socket.gethostname())

UPSERT = """
INSERT INTO jobs (company_id, ext_id, title, location, url, posted_at, discovered_live, raw,
                  is_us, states, remote)
VALUES (%(company_id)s, %(ext_id)s, %(title)s, %(location)s, %(url)s, %(posted_at)s, %(live)s, %(raw)s,
        %(is_us)s, %(states)s, %(remote)s)
ON CONFLICT (company_id, ext_id) DO UPDATE
SET title = EXCLUDED.title, location = EXCLUDED.location, url = EXCLUDED.url,
    is_us = EXCLUDED.is_us, states = EXCLUDED.states, remote = EXCLUDED.remote,
    last_seen = now(), is_active = TRUE
RETURNING id, (xmax = 0) AS inserted
"""

def process(r, client, task):
    cid = int(task["company_id"])
    t0 = time.monotonic()
    status, found, new_ids, err = "ok", 0, [], None
    try:
        jobs = FETCHERS[task["ats"]](client, task["slug"])
        found = len(jobs)
        with connect() as conn:
            first = conn.execute(
                "SELECT last_crawled_at IS NULL AS first FROM companies WHERE id=%s", (cid,)
            ).fetchone()["first"]
            for j in jobs:
                loc = from_raw(task["ats"], j["location"], j["raw"])
                row = conn.execute(UPSERT, {**j, **loc, "company_id": cid,
                                            "live": not first, "raw": Jsonb(j["raw"])}).fetchone()
                if row["inserted"] and not first:
                    new_ids.append(row["id"])
            conn.execute("UPDATE jobs SET is_active = FALSE "
                         "WHERE company_id=%s AND is_active AND last_seen < now()", (cid,))
        for jid in new_ids:
            r.xadd(config.NEW_JOBS_STREAM, {"job_id": jid, "company_id": cid},
                   maxlen=100000, approximate=True)
    except Exception as e:
        status, err = "error", str(e)[:500]
    finally:
        ms = int((time.monotonic() - t0) * 1000)
        with connect() as conn:
            conn.execute("UPDATE companies SET last_crawled_at=now(), last_status=%s WHERE id=%s",
                         (status, cid))
            conn.execute("INSERT INTO crawl_runs (company_id, status, jobs_found, new_jobs, duration_ms, error) "
                         "VALUES (%s,%s,%s,%s,%s,%s)", (cid, status, found, len(new_ids), ms, err))
        r.delete(f"inflight:{cid}")
        print(f"{task['ats']}/{task['slug']}: {status} found={found} new={len(new_ids)} {ms}ms", flush=True)

def main():
    r = redis.from_url(config.REDIS_URL, decode_responses=True,
                       socket_timeout=30, health_check_interval=30)
    try:
        r.xgroup_create(config.TASK_STREAM, config.GROUP, id="0", mkstream=True)
    except redis.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise
    headers = {"User-Agent": "JobRadar/0.1"}
    with httpx.Client(timeout=20, headers=headers, follow_redirects=True) as client:
        while True:
            try:
                resp = r.xreadgroup(config.GROUP, CONSUMER, {config.TASK_STREAM: ">"}, count=1, block=5000)
            except (redis.TimeoutError, redis.ConnectionError) as e:
                print(f"redis retry: {e}", flush=True)
                time.sleep(1)
                continue
            for _, msgs in resp or []:
                for msg_id, task in msgs:
                    process(r, client, task)
                    r.xack(config.TASK_STREAM, config.GROUP, msg_id)

if __name__ == "__main__":
    main()
