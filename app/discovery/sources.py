"""Candidate sources. Each yields dicts: ats, slug, name, source, guessed."""
import json
import os
import re
import time
from urllib.parse import parse_qs, unquote, urlparse

import httpx

ATSES = ("greenhouse", "lever", "ashby")
CC_HOSTS = {
    "boards.greenhouse.io": "greenhouse",
    "job-boards.greenhouse.io": "greenhouse",
    "jobs.lever.co": "lever",
    "jobs.ashbyhq.com": "ashby",
}
SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
NOT_SLUGS = {"embed", "api", "v1", "jobs", "favicon.ico", "robots.txt", "sitemap.xml"}
NAME_SUFFIXES = {
    "inc", "incorporated", "corp", "corporation", "co", "company", "ltd", "limited", "llc", "lp",
    "plc", "sa", "nv", "ag", "holdings", "holding", "group", "the", "trust", "bancorp",
}


def norm_slug(ats, slug):
    slug = unquote(slug).strip()
    if not SLUG_RE.match(slug) or slug.lower() in NOT_SLUGS:
        return None
    # Lever slugs are case sensitive; Greenhouse and Ashby are not.
    return slug if ats == "lever" else slug.lower()


def slug_from_url(url):
    u = urlparse(url if "://" in url else "https://" + url)
    ats = CC_HOSTS.get((u.hostname or "").lower())
    if not ats:
        return None, None
    parts = [p for p in u.path.split("/") if p]
    if ats == "greenhouse" and (not parts or parts[0] == "embed"):
        slug = (parse_qs(u.query).get("for") or [None])[0]
    else:
        slug = parts[0] if parts else None
    slug = norm_slug(ats, slug) if slug else None
    return (ats, slug) if slug else (None, None)


def name_guesses(name, *extra):
    """Slug guesses from a company name plus any extra hints (YC slug, domain stem)."""
    words = [w for w in re.split(r"[^a-z0-9]+", name.lower()) if w]
    core = [w for w in words if w not in NAME_SUFFIXES] or words
    guesses = {"".join(core), "-".join(core), *extra}
    return {g for g in guesses if g and SLUG_RE.match(g)}


def _guessed(name, source, guesses):
    for g in guesses:
        for ats in ATSES:
            slug = norm_slug(ats, g)
            if slug:
                yield {"ats": ats, "slug": slug, "name": name, "source": source, "guessed": True}


def _get(client, url, tries=6, **kw):
    for i in range(tries):
        try:
            r = client.get(url, **kw)
            if r.status_code < 500 and r.status_code != 429:
                if r.status_code != 404:
                    r.raise_for_status()
                return r
        except httpx.TransportError:
            pass
        if i + 1 < tries:
            time.sleep(min(60, 2 ** i))
    raise RuntimeError(f"gave up on {url}")


def commoncrawl(client, crawls=3, max_pages=None):
    """Board URLs from the Common Crawl CDX index. Slugs come straight from the URL."""
    if crawls < 1 or (max_pages is not None and max_pages < 1):
        raise ValueError("crawls and max_pages must be positive")
    infos = _get(client, "https://index.commoncrawl.org/collinfo.json").json()[:crawls]
    seen = set()
    for info in infos:
        api = info["cdx-api"]
        for host in CC_HOSTS:
            q = {"url": f"{host}/*", "output": "json", "fl": "url"}
            response = _get(client, api, params={**q, "showNumPages": "true"})
            if response.status_code == 404:
                continue
            pages = response.json()["pages"]
            for page in range(min(pages, max_pages or pages)):
                r = _get(client, api, params={**q, "page": page}, timeout=120)
                if r.status_code == 404:  # no captures for this host in this crawl
                    break
                for line in r.text.splitlines():
                    try:
                        ats, slug = slug_from_url(json.loads(line)["url"])
                    except (ValueError, KeyError):
                        continue
                    if slug and (ats, slug) not in seen:
                        seen.add((ats, slug))
                        yield {"ats": ats, "slug": slug, "name": None,
                               "source": f"commoncrawl:{info['id']}", "guessed": False}
                print(f"commoncrawl {info['id']} {host} page {page + 1}/{pages}: {len(seen)} slugs", flush=True)
                time.sleep(1)


def yc(client):
    """YC companies (yc-oss mirror). Skips inactive ones; guesses slugs from name, YC slug, and domain."""
    for c in _get(client, "https://yc-oss.github.io/api/companies/all.json").json():
        if c.get("status") == "Inactive" or not c.get("name"):
            continue
        host = urlparse(c.get("website") or "").hostname or ""
        stem = host.removeprefix("www.").split(".")[0]
        yield from _guessed(c["name"], "yc", name_guesses(c["name"], c.get("slug") or "", stem))


def sec(client):
    """Public companies from SEC EDGAR. SEC requires a User-Agent with contact info."""
    ua = os.getenv("SEC_USER_AGENT")
    if not ua:
        raise SystemExit('set SEC_USER_AGENT, e.g. "JobRadar you@example.com"')
    data = _get(client, "https://www.sec.gov/files/company_tickers.json", headers={"User-Agent": ua}).json()
    for c in data.values():
        yield from _guessed(c["title"], "sec", name_guesses(c["title"]))


SOURCES = {"commoncrawl": commoncrawl, "yc": yc, "sec": sec}
