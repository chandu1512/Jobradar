"""Discovery regression tests use HTTP fixtures, never public services or the live database."""
import argparse
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app.discovery import probe, sources
from app.discovery.__main__ import positive_int


class SourceTests(unittest.TestCase):
    def test_board_urls(self):
        cases = {
            'https://job-boards.greenhouse.io/Acme/jobs/12': ('greenhouse', 'acme'),
            'https://boards.greenhouse.io/embed/job_board?for=Acme': ('greenhouse', 'acme'),
            'jobs.lever.co/AcMe/12': ('lever', 'AcMe'),
            'https://jobs.ashbyhq.com/Acme/12': ('ashby', 'acme'),
            'https://jobs.lever.co.evil.example/acme': (None, None),
            'https://jobs.lever.co/%2Fbad': (None, None),
            'https://boards.greenhouse.io/embed': (None, None),
        }
        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(sources.slug_from_url(url), expected)

    def test_commoncrawl_missing_host_and_duplicate_urls(self):
        def respond(request):
            if request.url.path == '/collinfo.json':
                return httpx.Response(200, json=[{'id': 'fixture', 'cdx-api': 'https://index.example/cdx'}])
            if request.url.params['url'] != 'jobs.lever.co/*':
                return httpx.Response(404)
            if 'showNumPages' in request.url.params:
                return httpx.Response(200, json={'pages': 1})
            return httpx.Response(200, text='\n'.join([
                '{"url":"https://jobs.lever.co/AcMe/1"}',
                '{"url":"https://jobs.lever.co/AcMe/2"}',
                'bad json',
                '{"url":"https://example.com/unrelated"}',
            ]))

        with httpx.Client(transport=httpx.MockTransport(respond)) as client, patch.object(sources.time, 'sleep'):
            rows = list(sources.commoncrawl(client, crawls=1, max_pages=1))
        self.assertEqual(rows, [{'ats': 'lever', 'slug': 'AcMe', 'name': None,
                                 'source': 'commoncrawl:fixture', 'guessed': False}])

    def test_retry_transient_errors(self):
        responses = iter([httpx.Response(429), httpx.Response(503), httpx.Response(200, json=[])])
        with httpx.Client(transport=httpx.MockTransport(lambda r: next(responses))) as client:
            with patch.object(sources.time, 'sleep') as sleep:
                self.assertEqual(sources._get(client, 'https://example.com').status_code, 200)
        self.assertEqual(sleep.call_count, 2)

    def test_permanent_error_is_not_parsed_as_data(self):
        with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(403))) as client:
            with self.assertRaises(httpx.HTTPStatusError):
                sources._get(client, 'https://example.com')

    def test_yc_skips_inactive_and_generates_guesses(self):
        payload = [{'name': 'Acme Inc', 'website': 'https://acme.com', 'status': 'Active'},
                   {'name': 'Closed', 'status': 'Inactive'}]
        with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload))) as client:
            rows = list(sources.yc(client))
        self.assertEqual({r['ats'] for r in rows}, set(sources.ATSES))
        self.assertEqual({r['slug'] for r in rows}, {'acme'})
        self.assertTrue(all(r['guessed'] for r in rows))


class ProbeTests(unittest.IsolatedAsyncioTestCase):
    async def test_probe_results_and_malformed_payload_isolation(self):
        cases = [
            ('lever', [], 200, 'empty'),
            ('lever', [{'id': '1'}], 200, 'valid'),
            ('ashby', {'jobs': [{'id': '1'}]}, 200, 'valid'),
            ('ashby', {}, 200, 'error'),
            ('lever', {'error': 'unavailable'}, 200, 'error'),
            ('lever', ['not a job'], 200, 'error'),
            ('lever', {}, 404, 'invalid'),
            ('lever', {}, 429, 'error'),
        ]
        for ats, payload, code, expected in cases:
            with self.subTest(ats=ats, payload=payload, code=code):
                candidate = {'id': 1, 'ats': ats, 'slug': 'acme', 'name': 'Acme', 'guessed': False}
                transport = httpx.MockTransport(
                    lambda r, code=code, payload=payload: httpx.Response(code, json=payload)
                )
                async with httpx.AsyncClient(transport=transport) as client:
                    result = await probe._check(client, {ats: asyncio.Semaphore(1)}, candidate)
                self.assertEqual(result['status'], expected)

    async def test_greenhouse_guessed_name_mismatch(self):
        def respond(request):
            payload = {'jobs': [{'id': 1}]} if request.url.path.endswith('/jobs') else {'name': 'Unrelated'}
            return httpx.Response(200, json=payload)

        candidate = {'id': 1, 'ats': 'greenhouse', 'slug': 'acme', 'name': 'Acme', 'guessed': True}
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            result = await probe._check(client, {'greenhouse': asyncio.Semaphore(1)}, candidate)
        self.assertEqual(result['status'], 'mismatch')

    async def test_only_valid_boards_are_promoted_with_candidate_updates(self):
        candidates = [
            {'id': i, 'ats': 'lever', 'slug': f'company{i}', 'name': None, 'source': 'fixture',
             'guessed': False, 'board_name': None, 'jobs_found': 1, 'status': status}
            for i, status in enumerate(('valid', 'empty', 'invalid', 'mismatch', 'error'), 1)
        ]
        clock, read, write, finished = (MagicMock() for _ in range(4))
        clock.execute.return_value.fetchone.return_value = {'t': 'start'}
        read.execute.return_value.fetchall.return_value = candidates
        finished.execute.return_value.fetchall.return_value = []
        cursor = write.cursor.return_value.__enter__.return_value
        contexts = []
        for connection in (clock, read, write, finished):
            context = MagicMock()
            context.__enter__.return_value = connection
            contexts.append(context)
        with patch.object(probe, 'connect', side_effect=contexts):
            with patch.object(probe, '_check', new=AsyncMock(side_effect=lambda client, sems, c: c)):
                totals = await probe.run()
        self.assertEqual(totals, {status: 1 for status in ('valid', 'empty', 'invalid', 'mismatch', 'error')})
        calls = cursor.executemany.call_args_list
        self.assertEqual(calls[0].args, (probe.UPDATE_SQL, candidates))
        self.assertEqual(calls[1].args, (probe.PROMOTE_SQL, [{**candidates[0], 'name': 'company1'}]))

    async def test_invalid_limits_fail_before_database_access(self):
        for kwargs in ({'concurrency': 0}, {'limit': 0}, {'batch': 0}):
            with self.assertRaises(ValueError):
                await probe.run(**kwargs)


class ArgumentTests(unittest.TestCase):
    def test_positive_arguments(self):
        self.assertEqual(positive_int('2'), 2)
        for value in ('0', '-1'):
            with self.assertRaises(argparse.ArgumentTypeError):
                positive_int(value)
