"""
Export all app data to a timestamped JSON snapshot for on-demand download.
Called by the /export route.
"""

import json
import os
import tempfile
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

DATABASE_URL = os.environ["DATABASE_URL"]
TMP_DIR      = tempfile.gettempdir()


def do_export() -> str:
    """Write a full JSON snapshot to the system temp dir; return the path to the new file."""
    db = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cur = db.cursor()

    snapshot = {"exported_at": datetime.utcnow().isoformat() + "Z"}
    for table in ("members", "books", "ratings", "meals"):
        cur.execute(f"SELECT * FROM {table}")
        snapshot[table] = [dict(r) for r in cur.fetchall()]
    db.close()

    filename = f"backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    path = os.path.join(TMP_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)

    return path
