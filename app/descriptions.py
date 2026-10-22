"""Rate-limited SmartRecruiters detail enrichment, independent of discovery."""
import time

import httpx
from psycopg.types.json import Jsonb

from app.db import connect
from app.signals import enrich


def batch(client):
    with connect() as conn:
        rows = conn.execute("""
            SELECT j.id,j.ext_id,j.url,c.slug FROM jobs j JOIN companies c ON c.id=j.company_id
            WHERE j.is_active AND j.is_us AND c.ats='smartrecruiters'
              AND NOT (j.raw ? '_detail')
            ORDER BY j.id DESC LIMIT 20
        """).fetchall()
    for row in rows:
        try:
            response = client.get(f"https://api.smartrecruiters.com/v1/companies/{row['slug']}/postings/{row['ext_id']}")
            response.raise_for_status()
            detail = response.json()
            if str(detail.get('id')) != row['ext_id'] or not isinstance(detail.get('jobAd'), dict):
                raise ValueError('Unexpected posting detail')
            with connect() as conn:
                current = conn.execute('SELECT raw FROM jobs WHERE id=%s FOR UPDATE', (row['id'],)).fetchone()
                raw = {**current['raw'], '_detail': detail}
                conn.execute('UPDATE jobs SET raw=%s,signals=%s WHERE id=%s',
                             (Jsonb(raw), Jsonb(enrich(raw, row['url'])), row['id']))
        except (httpx.HTTPError, ValueError) as error:
            print(f"description {row['id']}: {type(error).__name__}", flush=True)
        time.sleep(0.5)
    print(f'description batch: {len(rows)} attempted', flush=True)


def main():
    with httpx.Client(timeout=15, follow_redirects=True) as client:
        while True:
            try:
                batch(client)
            except Exception as error:
                print(f'description retry: {type(error).__name__}', flush=True)
            time.sleep(60)


if __name__ == '__main__':
    main()
