import unittest
from unittest.mock import patch

import httpx

from app.career_fetchers import amazon, smartrecruiters
from app.discovery.sources import slug_from_url
from app.location import from_raw


def amazon_job(job_id='123'):
    return {'id_icims': job_id, 'title': 'Software Engineer', 'country_code': 'USA',
            'location': 'US, NJ, Newark', 'job_path': f'/en/jobs/{job_id}/software-engineer',
            'posted_date': 'October 22, 2026'}


class CareerTests(unittest.TestCase):
    def test_amazon_normalization_and_partial_inventory(self):
        def respond(request):
            self.assertEqual(request.url.params['country'], 'USA')
            return httpx.Response(200, json={'jobs': [amazon_job()], 'error': None})
        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            jobs = amazon(client, 'amazon')
        self.assertFalse(jobs.complete)
        self.assertEqual(jobs[0]['ext_id'], '123')
        self.assertEqual(jobs[0]['posted_at'].year, 2026)
        self.assertEqual(from_raw('amazon', jobs[0]['location'], jobs[0]['raw'])['states'], ['NJ'])

    def test_amazon_rejects_broken_country_filter(self):
        row = {**amazon_job(), 'country_code': 'ESP'}
        with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={'jobs': [row]}))) as c:
            with self.assertRaises(ValueError):
                amazon(c, 'amazon')

    def test_failed_page_does_not_return_partial_success(self):
        def respond(request):
            if request.url.params['offset'] == '0':
                return httpx.Response(200, json={'jobs': [amazon_job(str(i)) for i in range(100)]})
            return httpx.Response(503)
        with httpx.Client(transport=httpx.MockTransport(respond)) as c, patch('app.career_fetchers.time.sleep'):
            with self.assertRaises(httpx.HTTPStatusError):
                amazon(c, 'amazon')

    def test_smartrecruiters_pagination(self):
        def respond(request):
            offset = int(request.url.params['offset'])
            row = {'id': str(offset), 'name': 'Analyst', 'location': {'country': 'us', 'city': 'New York'}}
            return httpx.Response(200, json={'totalFound': 2, 'content': [row]})
        with httpx.Client(transport=httpx.MockTransport(respond)) as c, patch('app.career_fetchers.time.sleep'):
            jobs = smartrecruiters(c, 'Acme')
        self.assertEqual([j['ext_id'] for j in jobs], ['0', '1'])
        self.assertTrue(from_raw('smartrecruiters', jobs[0]['location'], jobs[0]['raw'])['is_us'])
        self.assertIn('/Acme/0', jobs[0]['url'])

    def test_smartrecruiters_incomplete_page_fails(self):
        payload = {'totalFound': 10, 'content': []}
        with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload))) as c:
            with self.assertRaises(ValueError):
                smartrecruiters(c, 'Acme')

    def test_career_urls_preserve_company_case(self):
        self.assertEqual(slug_from_url('https://careers.smartrecruiters.com/BoschGroup'),
                         ('smartrecruiters', 'BoschGroup'))
        self.assertEqual(slug_from_url('https://www.amazon.jobs/en/'), ('amazon', 'amazon'))
        self.assertEqual(slug_from_url('https://www.amazon.jobs.evil.example/en/'), (None, None))


class WorkerSnapshotTests(unittest.TestCase):
    def test_partial_feed_does_not_close_jobs_or_publish_first_backfill(self):
        from unittest.mock import MagicMock

        from app.career_fetchers import PartialJobs
        from app.worker import process

        conn = MagicMock()
        conn.execute.return_value.fetchone.side_effect = [{'first': True}, {'id': 1, 'inserted': True}]
        context = MagicMock()
        context.__enter__.return_value = conn
        rows = PartialJobs([{'ext_id': '1', 'title': 'Engineer', 'location': 'US, NJ, Newark',
                             'url': 'https://www.amazon.jobs/en/jobs/1/test', 'posted_at': None,
                             'raw': {'country_code': 'USA'}}])
        redis = MagicMock()
        with patch('app.worker.connect', return_value=context):
            with patch.dict('app.worker.FETCHERS', {'amazon': lambda client, slug: rows}):
                process(redis, None, {'company_id': '1', 'ats': 'amazon', 'slug': 'amazon'})
        sql = [call.args[0] for call in conn.execute.call_args_list]
        self.assertFalse(any('SET is_active = FALSE' in statement for statement in sql))
        redis.xadd.assert_not_called()
        redis.delete.assert_called_once_with('inflight:1')

    def test_complete_feed_still_closes_missing_jobs(self):
        from unittest.mock import MagicMock

        from app.worker import process

        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = {'first': False}
        context = MagicMock()
        context.__enter__.return_value = conn
        with patch('app.worker.connect', return_value=context):
            with patch.dict('app.worker.FETCHERS', {'smartrecruiters': lambda client, slug: []}):
                process(MagicMock(), None, {'company_id': '1', 'ats': 'smartrecruiters', 'slug': 'Acme'})
        sql = [call.args[0] for call in conn.execute.call_args_list]
        self.assertTrue(any('SET is_active = FALSE' in statement for statement in sql))
