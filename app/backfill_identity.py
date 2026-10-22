"""Populate URL identities without changing discovery dates or applications."""
from psycopg.types.json import Jsonb

from app.db import connect
from app.hunt import canonical_url


def main():
    cursor = 0
    while True:
        with connect() as conn:
            rows = conn.execute('SELECT id,url FROM jobs WHERE id>%s ORDER BY id LIMIT 2000', (cursor,)).fetchall()
            if not rows:
                break
            values = []
            for row in rows:
                try:
                    values.append({'id': row['id'], 'url': canonical_url(row['url'])})
                except ValueError:
                    continue
            conn.execute('UPDATE jobs j SET canonical_url=r.url FROM '
                         'jsonb_to_recordset(%s) AS r(id bigint,url text) WHERE j.id=r.id', (Jsonb(values),))
            cursor = rows[-1]['id']
    print('URL identity backfill complete', flush=True)


if __name__ == '__main__':
    main()
