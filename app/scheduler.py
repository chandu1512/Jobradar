import time

import redis

from app import config
from app.db import connect

DUE_SQL = """
SELECT id, ats, slug FROM companies
WHERE active AND (last_crawled_at IS NULL
  OR last_crawled_at < now() - %s::int * interval '1 minute')
"""

def main():
    r = redis.from_url(config.REDIS_URL, decode_responses=True)
    while True:
        with connect() as conn:
            rows = conn.execute(DUE_SQL, (config.CRAWL_INTERVAL_MIN,)).fetchall()
        n = 0
        for row in rows:
            if r.set(f"inflight:{row['id']}", 1, nx=True, ex=600):
                r.xadd(config.TASK_STREAM,
                       {"company_id": row["id"], "ats": row["ats"], "slug": row["slug"]},
                       maxlen=100000, approximate=True)
                n += 1
        print(f"scheduler: enqueued {n}", flush=True)
        time.sleep(60)

if __name__ == "__main__":
    main()
