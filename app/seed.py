import csv

from app.db import connect

with connect() as conn, open("data/companies.csv") as f:
    for row in csv.DictReader(f):
        conn.execute("INSERT INTO companies (name, ats, slug) VALUES (%s,%s,%s) "
                     "ON CONFLICT (ats, slug) DO NOTHING",
                     (row["name"], row["ats"], row["slug"]))
print("seeded")
