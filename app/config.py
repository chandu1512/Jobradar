import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://jobradar:jobradar@localhost:5432/jobradar")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CRAWL_INTERVAL_MIN = int(os.getenv("CRAWL_INTERVAL_MIN", "15"))
TASK_STREAM = "crawl:tasks"
NEW_JOBS_STREAM = "jobs:new"
GROUP = "crawlers"
