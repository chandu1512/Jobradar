import json
from pathlib import Path

import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from app import config
from app.categories import CATEGORIES, PATTERNS, annotate
from app.db import connect

app = FastAPI(title="JobRadar")
STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.middleware("http")
async def mark_origin(request: Request, call_next):
    head = request.method == "HEAD"
    if head and request.url.path != "/jobs/stream":
        request.scope["method"] = "GET"
    response = await call_next(request)
    if head:
        async def empty():
            if False:
                yield b""
        response.body_iterator = empty()
    response.headers["X-JobRadar-Origin"] = "api"
    return response


LEVELS = {
    "newgrad": r"(new\s*grad|entry[\s-]*level|early[\s-]*career|graduate|university|campus|junior"
               r"|\massociate\M|\m(i|1)\M\s*$|engineer\s+(i|1)\M)",
    "intern": r"\m(intern|internship|co-?op)\M",
}
SENIOR = r"\m(senior|sr\.?|staff|principal|lead|manager|director|head|vp|architect)\M"

JOB_COLS = """
j.id, c.name AS company, c.ats, j.title, j.location, j.states, j.remote, j.is_us,
j.url, j.posted_at, j.first_seen, j.discovered_live, j.signals,
j.signals->'requirements' AS requirements, j.signals->'salary' AS salary,
j.signals->'sponsorship' AS sponsorship, j.signals->'opt' AS opt
"""


def _filters(q, location, state, us, remote, level, hours, category="", company=""):
    where = ["j.is_active", "j.first_seen > now() - %(hours)s::int * interval '1 hour'"]
    args = {"hours": hours}
    if q:
        where.append("(j.title ILIKE %(q)s OR c.name ILIKE %(q)s)")
        args["q"] = f"%{q}%"
    if company:
        where.append("c.name ILIKE %(company)s")
        args["company"] = f"%{company}%"
    if location:
        where.append("j.location ILIKE %(loc)s")
        args["loc"] = f"%{location}%"
    if state:
        where.append("j.states && %(states)s")
        args["states"] = [s.strip().upper() for s in state.split(",") if s.strip()]
    if us:
        where.append("j.is_us")
    if remote:
        where.append("j.remote")
    if level in LEVELS:
        where.append("j.title ~* %(lvl)s AND j.title !~* %(senior)s")
        args |= {"lvl": LEVELS[level], "senior": SENIOR}
    if category:
        if category not in PATTERNS:
            raise HTTPException(status_code=422, detail="Unknown job category")
        where.append("j.title ~* %(category_pattern)s")
        args["category_pattern"] = PATTERNS[category]
    return " AND ".join(where), args


@app.get("/jobs")
def list_jobs(q: str = "", location: str = "", state: str = "", us: bool = True, remote: bool = False,
              level: str = "", hours: int = Query(24, le=24 * 90), limit: int = Query(50, le=200),
              before_id: int | None = None, category: str = "", company: str = "",
              sponsorship: str = "", opt_mentioned: bool = False, salary_disclosed: bool = False,
              requirement: str = ""):
    # Requirement filters surface evidence, never assert personal eligibility.
    where, args = _filters(q, location, state, us, remote, level, hours, category, company)
    if requirement:
        if requirement not in {"experience", "doctoral_degree", "work_authorization",
                               "enrollment", "graduation_window"}:
            raise HTTPException(status_code=422, detail="Unknown requirement type")
        where += " AND j.signals->'requirements'->'findings' @> %(requirement)s::jsonb"
        args["requirement"] = json.dumps([{"type": requirement}])
    if sponsorship:
        if sponsorship not in {"offered", "not_offered", "unknown", "conflicting"}:
            raise HTTPException(status_code=422, detail="Unknown sponsorship status")
        where += " AND coalesce(j.signals->'sponsorship'->>'status', 'unknown') = %(sponsorship)s"
        args["sponsorship"] = sponsorship
    if opt_mentioned:
        where += " AND j.signals->'opt'->>'mentioned' = 'true'"
    if salary_disclosed:
        where += " AND jsonb_array_length(coalesce(j.signals->'salary'->'ranges', '[]'::jsonb)) > 0"
    if before_id:
        where += " AND j.id < %(before_id)s"
        args["before_id"] = before_id
    sql = f"""
    SELECT {JOB_COLS} FROM jobs j JOIN companies c ON c.id = j.company_id
    WHERE {where} ORDER BY j.first_seen DESC, j.id DESC LIMIT %(limit)s
    """
    with connect() as conn:
        return annotate(conn.execute(sql, {**args, "limit": limit}).fetchall())


@app.get("/jobs/stream")
async def stream(request: Request):
    """Server sent events: one event per job published to jobs:new after the client connects."""
    async def gen():
        r = aioredis.from_url(config.REDIS_URL, decode_responses=True, socket_timeout=30)
        last = "$"
        try:
            while not await request.is_disconnected():
                resp = await r.xread({config.NEW_JOBS_STREAM: last}, block=15000, count=100)
                if not resp:
                    yield ": ping\n\n"
                    continue
                msgs = resp[0][1]
                last = msgs[-1][0]
                ids = [int(m["job_id"]) for _, m in msgs]
                for row in await run_in_threadpool(_jobs_by_id, ids):
                    yield f"data: {json.dumps(row, default=str)}\n\n"
        finally:
            await r.aclose()

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _jobs_by_id(ids):
    with connect() as conn:
        return annotate(conn.execute(f"SELECT {JOB_COLS} FROM jobs j JOIN companies c ON c.id = j.company_id "
                            "WHERE j.id = ANY(%s)", (ids,)).fetchall())


@app.get("/companies")
def companies(q: str = "", limit: int = Query(30, ge=1, le=100)):
    with connect() as conn:
        return conn.execute(
            "SELECT DISTINCT name FROM companies WHERE active AND name ILIKE %s "
            "ORDER BY name LIMIT %s", (f"%{q}%", limit)
        ).fetchall()


@app.get("/coverage")
def coverage(company: str = Query(..., min_length=1, max_length=200)):
    with connect() as conn:
        rows = conn.execute(
            "SELECT c.id, c.name, c.ats, c.last_status, c.last_crawled_at, "
            "count(j.id) FILTER (WHERE j.is_active) AS active_jobs "
            "FROM companies c LEFT JOIN jobs j ON j.company_id=c.id "
            "WHERE c.active AND c.name ILIKE %s GROUP BY c.id ORDER BY c.name LIMIT 30",
            (f"%{company.strip()}%",)
        ).fetchall()
    return {"covered": bool(rows), "companies": rows}


@app.get("/categories")
def categories():
    return [{"id": key, "label": label} for key, (label, _) in CATEGORIES.items()]


@app.get("/states")
def states(hours: int = Query(24 * 7, le=24 * 90)):
    sql = """
    SELECT s AS state, count(*) AS n FROM jobs j, unnest(j.states) s
    WHERE j.is_active AND j.first_seen > now() - %s::int * interval '1 hour'
    GROUP BY 1 ORDER BY 2 DESC
    """
    with connect() as conn:
        return conn.execute(sql, (hours,)).fetchall()


@app.get("/stats")
def stats():
    sql = """
    SELECT
      (SELECT count(*) FROM companies WHERE active) AS companies,
      (SELECT count(*) FROM jobs WHERE is_active) AS active_jobs,
      (SELECT count(*) FROM jobs WHERE is_active AND is_us) AS active_us_jobs,
      (SELECT count(*) FROM jobs WHERE discovered_live
         AND first_seen > now() - interval '24 hours') AS new_last_24h,
      (SELECT percentile_cont(0.5) WITHIN GROUP
         (ORDER BY extract(epoch FROM first_seen - previous_successful_crawl_at) / 60)
       FROM jobs WHERE discovered_live AND previous_successful_crawl_at IS NOT NULL
         AND first_seen > now() - interval '24 hours') AS median_observation_gap_minutes,
      (SELECT count(*) FROM jobs WHERE discovered_live AND previous_successful_crawl_at IS NOT NULL
         AND first_seen > now() - interval '24 hours') AS observation_gap_samples,
      (SELECT percentile_cont(0.5) WITHIN GROUP
         (ORDER BY extract(epoch FROM first_seen - posted_at) / 60)
       FROM jobs WHERE discovered_live AND posted_at IS NOT NULL) AS median_detect_minutes
    """
    with connect() as conn:
        result = conn.execute(sql).fetchone()
        result["median_posting_age_at_detection_minutes"] = result["median_detect_minutes"]
        result["detection_metric_note"] = (
            "Posting age includes upstream publication delays; observation gap is an upper bound "
            "since the preceding successful full feed crawl. Historical jobs have no observation bound.")
        return result


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")
