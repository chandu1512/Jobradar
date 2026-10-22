"""Rate-limited SmartRecruiters detail enrichment, independent of discovery."""
import time

import httpx
from psycopg.types.json import Jsonb

from app.db import connect
from app.signals import enrich


def batch(client, before_id=None):
    with connect() as conn:
        rows = conn.execute("""
            SELECT j.id,j.ext_id,j.url,c.slug,c.ats FROM jobs j JOIN companies c ON c.id=j.company_id
            WHERE j.is_active AND j.is_us AND c.ats IN ('smartrecruiters','greenhouse','lever')
              AND j.signals->>'description_available'='false'
              AND NOT (j.raw ? '_detail')
              AND (%s::bigint IS NULL OR j.id<%s)
            ORDER BY j.id DESC LIMIT 20
        """, (before_id, before_id)).fetchall()
    for row in rows:
        try:
            url = (f"https://api.smartrecruiters.com/v1/companies/{row['slug']}/postings/{row['ext_id']}"
                   if row.get('ats', 'smartrecruiters') == 'smartrecruiters' else
                   f"https://boards-api.greenhouse.io/v1/boards/{row['slug']}/jobs/{row['ext_id']}")
            if row.get('ats') == 'lever':
                url = f"https://api.lever.co/v0/postings/{row['slug']}/{row['ext_id']}"
            response = client.get(url)
            response.raise_for_status()
            detail = response.json()
            body = detail.get('jobAd', detail.get('content', detail.get('descriptionPlain', detail.get('description'))))
            if (str(detail.get('id')) != row['ext_id']
                    or not isinstance(body, dict | str)):
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
    return rows[-1]['id'] if rows else None


def main():
    with httpx.Client(timeout=15, follow_redirects=True) as client:
        cursor = None
        while True:
            try:
                cursor = batch(client, cursor)
            except Exception as error:
                print(f'description retry: {type(error).__name__}', flush=True)
            time.sleep(60)


if __name__ == '__main__':
    main()
