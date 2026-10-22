"""Enrich stored postings without changing discovery dates or publishing events."""
from psycopg.types.json import Jsonb

from app.db import connect
from app.signals import enrich


def main():
    cursor = 0
    while True:
        with connect() as conn:
            rows = conn.execute(
                'SELECT id, raw, url FROM jobs WHERE id > %s ORDER BY id LIMIT 500', (cursor,)).fetchall()
            if not rows:
                break
            for row in rows:
                conn.execute('UPDATE jobs SET signals=%s WHERE id=%s',
                             (Jsonb(enrich(row['raw'] or {}, row['url'])), row['id']))
            cursor = rows[-1]['id']
    print('Posting evidence backfill complete', flush=True)


if __name__ == '__main__':
    main()
