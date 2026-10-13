"""Recompute is_us/states/remote for every job. Run after changing app/location.py."""
from app.db import connect
from app.location import from_raw

with connect() as conn:
    rows = conn.execute(
        "SELECT j.id, c.ats, j.location, j.raw FROM jobs j JOIN companies c ON c.id = j.company_id"
    ).fetchall()
    with conn.cursor() as cur:
        cur.executemany("UPDATE jobs SET is_us=%(is_us)s, states=%(states)s, remote=%(remote)s WHERE id=%(id)s",
                        [{**from_raw(r["ats"], r["location"], r["raw"]), "id": r["id"]} for r in rows])
print(f"backfilled {len(rows)} jobs")
