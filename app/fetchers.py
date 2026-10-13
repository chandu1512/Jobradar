from datetime import UTC, datetime


def _ms(ms):
    return datetime.fromtimestamp(ms / 1000, tz=UTC) if ms else None

def greenhouse(client, slug):
    r = client.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
    r.raise_for_status()
    return [{
        "ext_id": str(j["id"]),
        "title": j["title"],
        "location": (j.get("location") or {}).get("name"),
        "url": j["absolute_url"],
        "posted_at": j.get("first_published") or j.get("updated_at"),
        "raw": j,
    } for j in r.json().get("jobs", [])]

def lever(client, slug):
    r = client.get(f"https://api.lever.co/v0/postings/{slug}?mode=json")
    r.raise_for_status()
    return [{
        "ext_id": j["id"],
        "title": j["text"],
        "location": (j.get("categories") or {}).get("location"),
        "url": j["hostedUrl"],
        "posted_at": _ms(j.get("createdAt")),
        "raw": j,
    } for j in r.json()]

def ashby(client, slug):
    r = client.get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    r.raise_for_status()
    return [{
        "ext_id": j["id"],
        "title": j["title"],
        "location": j.get("location"),
        "url": j.get("jobUrl") or j.get("applyUrl"),
        "posted_at": j.get("publishedAt"),
        "raw": j,
    } for j in r.json().get("jobs", [])]

FETCHERS = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby}
