"""
Export all app data to a timestamped JSON backup file.
Called both by the weekly scheduler and the /export route.
"""

import json
import os
import sqlite3
from datetime import datetime

DATA_DIR   = os.path.join(os.path.dirname(__file__), "data")
DATABASE   = os.path.join(DATA_DIR, "bookclub.db")
BACKUP_DIR = os.path.join(DATA_DIR, "backups")
KEEP       = 10   # number of rolling backups to retain


def do_export() -> str:
    """Write a full JSON snapshot; return the path to the new file."""
    os.makedirs(BACKUP_DIR, exist_ok=True)

    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row

    snapshot = {
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "members": [dict(r) for r in db.execute("SELECT * FROM members").fetchall()],
        "books":   [dict(r) for r in db.execute("SELECT * FROM books").fetchall()],
        "ratings": [dict(r) for r in db.execute("SELECT * FROM ratings").fetchall()],
        "meals":   [dict(r) for r in db.execute("SELECT * FROM meals").fetchall()],
    }
    db.close()

    filename = f"backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    path = os.path.join(BACKUP_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)

    # Keep only the N most recent backups
    all_backups = sorted(
        f for f in os.listdir(BACKUP_DIR) if f.startswith("backup_")
    )
    for old in all_backups[:-KEEP]:
        os.remove(os.path.join(BACKUP_DIR, old))

    return path
