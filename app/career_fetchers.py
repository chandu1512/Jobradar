"""Additional public careers sources. Partial feeds must never close unseen jobs."""
import time
from datetime import UTC, datetime


class PartialJobs(list):
    """A bounded discovery window rather than a complete inventory of open jobs."""

    complete = False


def amazon(client, slug):
    if slug != 'amazon':
        raise ValueError('Amazon source requires the amazon board')
    jobs, seen = PartialJobs(), set()
    # The public website endpoint caps search results. Poll a recent US window and
    # never infer closures from absence in this window.
    for offset in range(0, 1000, 100):
        response = client.get('https://www.amazon.jobs/en/search.json', params={
            'country': 'USA', 'sort': 'recent', 'offset': offset, 'result_limit': 100,
        })
        response.raise_for_status()
        payload = response.json()
        if payload.get('error') or not isinstance(payload.get('jobs'), list):
            raise ValueError('Invalid Amazon response')
        rows = payload['jobs']
        for row in rows:
            if row['country_code'] != 'USA':
                raise ValueError('Amazon country filter was not honored')
            ext_id = str(row['id_icims'])
            if ext_id in seen:
                continue
            seen.add(ext_id)
            path = row['job_path']
            if not path.startswith('/en/jobs/'):
                raise ValueError('Unexpected Amazon job URL')
            posted = None
            if row.get('posted_date'):
                try:
                    posted = datetime.strptime(row['posted_date'], '%B %d, %Y').replace(tzinfo=UTC)
                except ValueError:
                    pass
            jobs.append({'ext_id': ext_id, 'title': row['title'], 'location': row['location'],
                         'url': 'https://www.amazon.jobs' + path, 'posted_at': posted, 'raw': row})
        if len(rows) < 100:
            break
        time.sleep(0.2)
    return jobs


def smartrecruiters(client, slug):
    jobs, seen = [], set()
    offset = 0
    for _ in range(1000):
        response = client.get(f'https://api.smartrecruiters.com/v1/companies/{slug}/postings',
                              params={'offset': offset, 'limit': 100})
        response.raise_for_status()
        payload = response.json()
        rows, total = payload['content'], payload['totalFound']
        if not isinstance(rows, list) or not isinstance(total, int) or total < 0:
            raise ValueError('Invalid SmartRecruiters response')
        if not rows and offset < total:
            raise ValueError('Incomplete SmartRecruiters pagination')
        for row in rows:
            ext_id = str(row['id'])
            if ext_id in seen:
                raise ValueError('Repeated SmartRecruiters posting during pagination')
            seen.add(ext_id)
            loc = row.get('location') or {}
            location = loc.get('fullLocation') or ', '.join(
                str(loc[k]) for k in ('city', 'region', 'country') if loc.get(k))
            jobs.append({'ext_id': ext_id, 'title': row['name'], 'location': location,
                         'url': f'https://jobs.smartrecruiters.com/{slug}/{ext_id}',
                         'posted_at': row.get('releasedDate'), 'raw': row})
        offset += len(rows)
        if offset >= total:
            return jobs
        time.sleep(0.2)
    raise ValueError('SmartRecruiters pagination exceeded safety bound')
