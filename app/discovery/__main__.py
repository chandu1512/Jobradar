"""
python -m app.discovery collect {commoncrawl,yc,sec} [--crawls N] [--max-pages N]
python -m app.discovery probe [--source yc] [--retry empty,error] [--limit N] [--concurrency N]
python -m app.discovery stats
"""
import argparse
import asyncio
from itertools import islice

import httpx

from app.db import connect
from app.discovery import probe
from app.discovery.sources import SOURCES

INSERT_SQL = """
INSERT INTO company_candidates (ats, slug, name, source, guessed)
VALUES (%(ats)s, %(slug)s, %(name)s, %(source)s, %(guessed)s)
ON CONFLICT (ats, slug) DO NOTHING
"""


def collect(source, **kw):
    headers = {"User-Agent": "JobRadar/0.1"}
    total = 0
    with httpx.Client(timeout=60, headers=headers, follow_redirects=True) as client:
        it = SOURCES[source](client, **kw)
        while chunk := list(islice(it, 1000)):
            with connect() as conn, conn.cursor() as cur:
                cur.executemany(INSERT_SQL, chunk)
            total += len(chunk)
    print(f"collect {source}: {total} candidates offered (duplicates ignored)")


def stats():
    with connect() as conn:
        rows = conn.execute("""
            SELECT split_part(source, ':', 1) AS source, ats, status, count(*) AS n
            FROM company_candidates GROUP BY 1, 2, 3 ORDER BY 1, 2, 3
        """).fetchall()
        companies = conn.execute("SELECT count(*) AS n FROM companies WHERE active").fetchone()["n"]
    for r in rows:
        print(f"{r['source']:<12} {r['ats']:<11} {r['status']:<9} {r['n']}")
    print(f"active companies: {companies}")


def positive_int(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def main():
    p = argparse.ArgumentParser(prog="python -m app.discovery")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("source", choices=SOURCES)
    c.add_argument("--crawls", type=positive_int, default=3, help="commoncrawl: how many recent crawls")
    c.add_argument("--max-pages", type=positive_int, help="commoncrawl: cap index pages per host per crawl")
    pr = sub.add_parser("probe")
    pr.add_argument("--retry", default="", help="also reprobe these statuses, e.g. empty,error")
    pr.add_argument("--source", default="", help="only candidates whose source starts with this")
    pr.add_argument("--limit", type=positive_int)
    pr.add_argument("--concurrency", type=positive_int, default=8, help="parallel requests per ATS")
    sub.add_parser("stats")
    a = p.parse_args()

    if a.cmd == "collect":
        kw = {"crawls": a.crawls, "max_pages": a.max_pages} if a.source == "commoncrawl" else {}
        collect(a.source, **kw)
    elif a.cmd == "probe":
        statuses = ["pending", *filter(None, a.retry.split(","))]
        asyncio.run(probe.run(statuses, source=a.source, limit=a.limit, concurrency=a.concurrency))
    else:
        stats()


if __name__ == "__main__":
    main()
