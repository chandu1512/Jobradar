import unittest

import httpx

from app.api import app


class HeadTests(unittest.IsolatedAsyncioTestCase):
    async def test_head_matches_get_headers_without_body(self):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            get = await client.get('/categories')
            head = await client.head('/categories')
            self.assertEqual(head.status_code, 200)
            self.assertEqual(head.content, b'')
            self.assertEqual(head.headers['content-type'], get.headers['content-type'])
            self.assertEqual(head.headers['content-length'], get.headers['content-length'])

    async def test_invalid_sponsorship_filter_rejected(self):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            response = await client.get('/jobs?sponsorship=guaranteed')
            self.assertEqual(response.status_code, 422)
