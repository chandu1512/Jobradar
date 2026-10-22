"""Private application state and explicit, unit-aware pay filtering."""
import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import HTTPException

from app.db import connect


def canonical_url(value):
    parts = urlsplit(str(value))
    if parts.scheme not in {'https', 'http'} or not parts.hostname or parts.username or parts.password:
        raise ValueError('A public HTTP(S) job URL is required')
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not k.lower().startswith('utm_') and k.lower() not in {'source', 'ref', 'referrer', 'gclid', 'fbclid'}]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip('/') or '/',
                       urlencode(sorted(query)), ''))


def name_key(value):
    return re.sub(r'[^\w]+', ' ', value.lower()).strip()


def workspace(authorization, required=False):
    if not authorization:
        if required:
            raise HTTPException(401, 'Connect a private workspace first')
        return None
    if not authorization.startswith('Bearer '):
        raise HTTPException(401, 'Use a Bearer workspace token')
    digest = hashlib.sha256(authorization[7:].encode()).hexdigest()
    with connect() as conn:
        row = conn.execute('SELECT id FROM workspaces WHERE token_hash=%s', (digest,)).fetchone()
    if not row:
        raise HTTPException(401, 'Invalid workspace token')
    return str(row['id'])


def pay_filter(minimum, interval, currency, keep_unknown):
    units = {'year': ['year', 'annual', 'annually', 'annum', '1 year', 'yearly'],
             'hour': ['hour', 'hr', 'hourly', '1 hour']}
    if interval not in units:
        raise HTTPException(422, 'comp_interval must be year or hour')
    # Keep unknown-period/currency postings for review; never annualize by guessing hours.
    known = """SELECT 1 FROM jsonb_array_elements(coalesce(j.signals->'salary'->'ranges','[]'::jsonb)) s
        WHERE upper(s->>'currency')=%(comp_currency)s AND lower(s->>'interval')=ANY(%(comp_units)s)
        AND jsonb_typeof(s->'max')='number'"""
    above = known + " AND (s->>'max')::numeric >= %(min_comp)s"
    clause = f'EXISTS ({above})'
    if keep_unknown:
        clause = f'(NOT EXISTS ({known}) OR {clause})'
    return clause, {'comp_currency': currency.upper(), 'comp_units': units[interval], 'min_comp': minimum}


APPLIED_MATCH = """a.workspace_id=%(workspace_id)s::uuid
    AND (a.url=j.url OR a.canonical_url=coalesce(j.canonical_url,regexp_replace(split_part(j.url,'#',1), '/$', '')))"""
APPLIED_SQL = f'EXISTS (SELECT 1 FROM applications a WHERE {APPLIED_MATCH})'
APPLICATION_ID_SQL = f'(SELECT a.id FROM applications a WHERE {APPLIED_MATCH} LIMIT 1)'
SIMILAR_SQL = """EXISTS (SELECT 1 FROM applications a WHERE a.workspace_id=%(workspace_id)s::uuid
    AND a.company_key=trim(regexp_replace(lower(c.name),'[^[:alnum:]_]+',' ','g'))
    AND a.title_key=trim(regexp_replace(lower(j.title),'[^[:alnum:]_]+',' ','g')))"""
