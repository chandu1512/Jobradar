"""Enrich stored postings without changing discovery dates or publishing events."""
import argparse

from psycopg.types.json import Jsonb

from app.db import connect
from app.signals import enrich


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--company', help='Reprocess only matching company names')
    args = parser.parse_args()
    company = f'%{args.company}%' if args.company else None
    cursor = 0
    updated = 0
    while True:
        with connect() as conn:
            rows = conn.execute(
                "SELECT j.id, j.raw, j.url FROM jobs j JOIN companies c ON c.id=j.company_id "
                "WHERE j.id > %s AND (%s::text IS NULL OR c.name ILIKE %s) ORDER BY j.id LIMIT 500",
                (cursor, company, company)).fetchall()
            if not rows:
                break
            for row in rows:
                conn.execute('UPDATE jobs SET signals=%s WHERE id=%s',
                             (Jsonb(enrich(row['raw'] or {}, row['url'])), row['id']))
            cursor = rows[-1]['id']
            updated += len(rows)
    print(f'Posting evidence backfill complete: {updated} postings', flush=True)


if __name__ == '__main__':
    main()
