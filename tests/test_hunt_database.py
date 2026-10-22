"""Opt-in real PostgreSQL checks using connection-local temporary tables only."""
import asyncio
import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import httpx
from psycopg.types.json import Jsonb

from app.api import app
from app.db import connect


@unittest.skipUnless(os.getenv('JOBRADAR_DB_TESTS') == '1', 'Opt-in PostgreSQL integration checks')
class HuntDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.conn = connect()
        for table in ('companies', 'jobs', 'workspaces', 'applications', 'sponsor_history'):
            self.conn.execute(f'CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL)')
        self.conn.execute("INSERT INTO companies(id,name,ats,slug) VALUES (1,'Example','greenhouse','example')")
        for jid, amount, unit, entry in [(1,65000,'year',True),(2,24,'hour',False),
                                         (3,85000,None,False),(4,90000,'year',True),(5,30,'hour',False)]:
            signal = {'salary': {'ranges': [{'min':amount,'max':amount,'currency':'USD','interval':unit}]},
                      'entry_level': {'status':'entry_evidence' if entry else 'unknown'}, 'start_dates':[]}
            self.conn.execute('INSERT INTO jobs(id,company_id,ext_id,title,url,canonical_url,is_us,signals) '
                              'VALUES (%s,1,%s,%s,%s,%s,true,%s)',
                              (jid,str(jid),'Machine Learning Engineer',f'https://example.com/job/{jid}',
                               f'https://example.com/job/{jid}',Jsonb(signal)))

        @contextmanager
        def shared():
            yield self.conn

        self.patches = [patch('app.api.connect',shared),patch('app.hunt.connect',shared)]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.conn.rollback()
        self.conn.close()

    def test_pay_units_unknowns_and_body_filter(self):
        async def run():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
                response = await client.get('/jobs?min_comp=70000&comp_interval=year')
                self.assertEqual(response.status_code,200,response.text)
                self.assertEqual({j['id'] for j in response.json()},{2,3,4,5})
                response = await client.get('/jobs?min_comp=70000&comp_interval=year&keep_unknown_pay=false')
                self.assertEqual({j['id'] for j in response.json()},{4})
                response = await client.get('/jobs?min_comp=25&comp_interval=hour&keep_unknown_pay=false')
                self.assertEqual({j['id'] for j in response.json()},{5})
                response = await client.get('/jobs?level=entry_body')
                self.assertEqual({j['id'] for j in response.json()},{1,4})
        asyncio.run(run())

    def test_application_sync_is_idempotent_private_and_undoable(self):
        async def run():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
                token = (await client.post('/workspaces')).json()['token']
                headers = {'Authorization':f'Bearer {token}'}
                item = {'company':'Example','title':'Machine Learning Engineer',
                        'url':'https://example.com/job/1?utm_source=email'}
                first = await client.post('/applications',json=[item],headers=headers)
                self.assertEqual(first.status_code,200,first.text)
                aid = first.json()['application_ids'][0]
                item['url'] = 'https://example.com/job/1?ref=muse'
                again = await client.post('/applications',json=[item],headers=headers)
                self.assertEqual(again.json()['application_ids'],[aid])
                response = await client.get('/jobs?applied=only',headers=headers)
                self.assertEqual({j['id'] for j in response.json()},{1})
                response = await client.get('/jobs?applied=exclude',headers=headers)
                self.assertNotIn(1,{j['id'] for j in response.json()})
                self.assertTrue(all(j['applied'] is None for j in (await client.get('/jobs')).json()))
                other = (await client.post('/workspaces')).json()['token']
                response = await client.get('/applications',headers={'Authorization':f'Bearer {other}'})
                self.assertEqual(response.json(),[])
                self.assertEqual((await client.delete(f'/applications/{aid}',headers=headers)).status_code,200)
                self.assertEqual((await client.get('/jobs?applied=only',headers=headers)).json(),[])
        asyncio.run(run())

    def test_history_and_repost_evidence_are_explicit(self):
        self.conn.execute("INSERT INTO sponsor_history(company_id,fiscal_year,filings_count,record_type,"
                          "source_url,employer_name) VALUES (1,2025,10,'lca_filings',"
                          "'https://example.com/source','Example Legal LLC')")
        self.conn.execute("INSERT INTO jobs(id,company_id,ext_id,title,url,first_seen,is_active) "
                          "VALUES (99,1,'old','Machine Learning Engineer','https://example.com/old',"
                          "now()-interval '2 days',false)")
        async def run():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
                rows = (await client.get('/jobs?sponsor_history_only=true')).json()
                self.assertEqual(len(rows),5)
                self.assertEqual(rows[0]['sponsor_history'][0]['record_type'],'lca_filings')
                self.assertEqual(rows[0]['sponsor_history'][0]['filings_count'],10)
                self.assertEqual(rows[0]['possible_repost_of'][0]['id'],99)
                self.assertEqual(rows[0]['reactivation_count'],0)
        asyncio.run(run())
