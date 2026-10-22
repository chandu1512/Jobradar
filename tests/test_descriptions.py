import unittest
from unittest.mock import MagicMock, patch

from app.descriptions import batch


class DescriptionTests(unittest.TestCase):
    @patch('app.descriptions.time.sleep')
    @patch('app.descriptions.connect')
    def test_detail_updates_without_discovery_events(self, connect, sleep):
        conn = connect.return_value.__enter__.return_value
        conn.execute.return_value.fetchall.return_value = [
            {'id': 1, 'ext_id': '123', 'slug': 'Acme', 'url': 'https://example.com/job'}]
        conn.execute.return_value.fetchone.return_value = {'raw': {'id': '123'}}
        client = MagicMock()
        client.get.return_value.json.return_value = {
            'id': '123', 'jobAd': {'sections': {'jobDescription': {'text': 'Annual salary $85,000.'}}}}
        batch(client)
        sql = [call.args[0] for call in conn.execute.call_args_list]
        self.assertTrue(any('UPDATE jobs SET raw=' in query for query in sql))
        self.assertFalse(any('first_seen=' in query for query in sql))
        self.assertFalse(any('INSERT INTO jobs' in query for query in sql))

    @patch('app.descriptions.time.sleep')
    @patch('app.descriptions.connect')
    def test_mismatched_detail_is_not_saved(self, connect, sleep):
        conn = connect.return_value.__enter__.return_value
        conn.execute.return_value.fetchall.return_value = [
            {'id': 1, 'ext_id': '123', 'slug': 'Acme', 'url': 'https://example.com/job'}]
        client = MagicMock()
        client.get.return_value.json.return_value = {'id': 'wrong', 'jobAd': {}}
        batch(client)
        self.assertEqual(conn.execute.call_count, 1)
