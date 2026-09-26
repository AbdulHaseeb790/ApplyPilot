from src.applypilot.database import init_db, get_connection
from src.applypilot.discovery.rozee import scrape_rozee

init_db()
jobs = scrape_rozee('Python Developer', 'karachi', max_jobs=5)
print("Jobs scraped:", len(jobs))

with get_connection() as conn:
    for job in jobs:
        conn.execute(
            'INSERT OR IGNORE INTO jobs (url, title, location, description, site, strategy) VALUES (?, ?, ?, ?, ?, ?)',
            (job.url, job.title, job.location, job.description, 'rozee.pk', 'rozee')
        )
    conn.commit()
    rows = conn.execute('SELECT title, location, site FROM jobs LIMIT 5').fetchall()
    print("Rows in DB:", len(rows))
    for r in rows:
        print(dict(r))