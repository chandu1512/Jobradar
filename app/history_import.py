"""Import reviewed company history JSON without fuzzy employer-name matching.

Input: [{company_id, fiscal_year, filings_count, record_type, source_url, employer_name}].
LCAs are filing history, not proof of an approved visa or a current sponsorship offer.
"""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from app.db import connect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', type=Path)
    args = parser.parse_args()
    rows = json.loads(args.path.read_text())
    if not isinstance(rows, list):
        raise ValueError('Expected a JSON array')
    with connect() as conn:
        for row in rows:
            if urlsplit(row['source_url']).scheme not in {'http', 'https'}:
                raise ValueError('Each record needs a source URL')
            conn.execute('''INSERT INTO sponsor_history
                (company_id,fiscal_year,filings_count,record_type,source_url,employer_name)
                VALUES (%(company_id)s,%(fiscal_year)s,%(filings_count)s,%(record_type)s,
                        %(source_url)s,%(employer_name)s)
                ON CONFLICT (company_id,fiscal_year,record_type,source_url) DO UPDATE
                SET filings_count=EXCLUDED.filings_count,employer_name=EXCLUDED.employer_name,imported_at=now()''', row)
    print(f'Imported {len(rows)} reviewed history records')


if __name__ == '__main__':
    main()
