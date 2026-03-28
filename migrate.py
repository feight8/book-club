"""
One-time migration: reads data/*.json and populates data/bookclub.db.

Run ONCE after pulling this version of the code:
    python migrate.py
"""

import json
import os
import sqlite3
import sys

BASE     = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE, "data")
DATABASE = os.path.join(DATA_DIR, "bookclub.db")

# Reuse the schema defined in app.py
sys.path.insert(0, BASE)
from app import SCHEMA


def load(name):
    path = os.path.join(DATA_DIR, f"{name}.json")
    if not os.path.exists(path):
        print(f"  WARNING: {path} not found — skipping")
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def run():
    if os.path.exists(DATABASE):
        answer = input(f"Database already exists at {DATABASE}.\nOverwrite? [y/N] ")
        if answer.strip().lower() != "y":
            print("Aborted — nothing changed.")
            return
        os.remove(DATABASE)

    db = sqlite3.connect(DATABASE)
    db.executescript(SCHEMA)

    members = load("members")
    books   = load("books")
    meals   = load("meals")

    # ── Members ──────────────────────────────────────────────────────────────
    for m in members:
        db.execute("""
            INSERT INTO members
                (id, name, nickname, avatar_seed, avatar_img,
                 fun_facts, quotes, favorite_genre, join_date, signature_dish)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (
            m["id"],
            m["name"],
            m.get("nickname", ""),
            m.get("avatar_seed", ""),
            m.get("avatar_img"),
            json.dumps(m.get("fun_facts", [])),
            json.dumps(m.get("quotes", [])),
            m.get("favorite_genre", ""),
            m.get("join_date", ""),
            m.get("signature_dish", ""),
        ))
    print(f"  Inserted {len(members)} members")

    # ── Books + ratings ───────────────────────────────────────────────────────
    rating_count = 0
    for b in books:
        db.execute("""
            INSERT INTO books
                (id, title, author, genre, pages, goodreads_rating, year_published,
                 date_read, selected_by, description, cover_color, cover_accent,
                 tags, event_note, goodreads_url, cover_img)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            b["id"],
            b["title"],
            b.get("author", ""),
            b.get("genre", ""),
            b.get("pages", 0),
            b.get("goodreads_rating", 0),
            b.get("year_published", 0),
            b.get("date_read", ""),
            b.get("selected_by"),
            b.get("description", ""),
            b.get("cover_color", "#444444"),
            b.get("cover_accent", "#888888"),
            json.dumps(b.get("tags", [])),
            b.get("event_note", ""),
            b.get("goodreads_url", ""),
            b.get("cover_img", ""),
        ))
        for mid_str, r in b.get("ratings", {}).items():
            db.execute("""
                INSERT OR IGNORE INTO ratings (book_id, member_id, score, review)
                VALUES (?,?,?,?)
            """, (b["id"], int(mid_str), r["score"], r.get("review", "")))
            rating_count += 1

    print(f"  Inserted {len(books)} books, {rating_count} ratings")

    # ── Meals ─────────────────────────────────────────────────────────────────
    for m in meals:
        recipe = m.get("recipe")
        db.execute("""
            INSERT INTO meals (id, book_id, dish, prepared_by, type, description, recipe)
            VALUES (?,?,?,?,?,?,?)
        """, (
            m["id"],
            m["book_id"],
            m["dish"],
            m.get("prepared_by"),
            m.get("type", ""),
            m.get("description", ""),
            json.dumps(recipe) if recipe else None,
        ))
    print(f"  Inserted {len(meals)} meals")

    db.commit()
    db.close()
    print(f"\nDone. Database written to {DATABASE}")
    print("You can now start the app with:  python app.py")


if __name__ == "__main__":
    run()
