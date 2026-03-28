import json
import os
import sqlite3
from flask import (Flask, render_template, abort, request,
                   redirect, url_for, flash, g)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "book-club-dev-secret")

DATA_DIR    = os.path.join(os.path.dirname(__file__), "data")
AVATARS_DIR = os.path.join(os.path.dirname(__file__), "static", "avatars")
DATABASE    = os.path.join(DATA_DIR, "bookclub.db")
ALLOWED_AVATAR_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "svg"}

os.makedirs(AVATARS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# ── Schema ─────────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS members (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    nickname       TEXT    DEFAULT '',
    avatar_seed    TEXT    DEFAULT '',
    avatar_img     TEXT,
    fun_facts      TEXT    DEFAULT '[]',
    quotes         TEXT    DEFAULT '[]',
    favorite_genre TEXT    DEFAULT '',
    join_date      TEXT    DEFAULT '',
    signature_dish TEXT    DEFAULT ''
);

CREATE TABLE IF NOT EXISTS books (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    title            TEXT NOT NULL,
    author           TEXT    DEFAULT '',
    genre            TEXT    DEFAULT '',
    pages            INTEGER DEFAULT 0,
    goodreads_rating REAL    DEFAULT 0,
    year_published   INTEGER DEFAULT 0,
    date_read        TEXT    DEFAULT '',
    selected_by      INTEGER REFERENCES members(id) ON DELETE SET NULL,
    description      TEXT    DEFAULT '',
    cover_color      TEXT    DEFAULT '#444444',
    cover_accent     TEXT    DEFAULT '#888888',
    tags             TEXT    DEFAULT '[]',
    event_note       TEXT    DEFAULT '',
    goodreads_url    TEXT    DEFAULT '',
    cover_img        TEXT    DEFAULT ''
);

CREATE TABLE IF NOT EXISTS ratings (
    book_id   INTEGER NOT NULL REFERENCES books(id)   ON DELETE CASCADE,
    member_id INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    score     REAL    NOT NULL,
    review    TEXT    DEFAULT '',
    PRIMARY KEY (book_id, member_id)
);

CREATE TABLE IF NOT EXISTS meals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id     INTEGER REFERENCES books(id)   ON DELETE CASCADE,
    dish        TEXT NOT NULL,
    prepared_by INTEGER REFERENCES members(id) ON DELETE SET NULL,
    type        TEXT DEFAULT '',
    description TEXT DEFAULT '',
    recipe      TEXT
);
"""

# ── Database helpers ───────────────────────────────────────────────────────────

def init_db():
    """Create tables if they don't exist."""
    db = sqlite3.connect(DATABASE)
    db.executescript(SCHEMA)
    db.commit()
    db.close()

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def to_dict(r):
    """sqlite3.Row → plain dict; JSON fields decoded to Python objects."""
    if r is None:
        return None
    d = dict(r)
    for field in ("tags", "fun_facts", "quotes"):
        try:
            d[field] = json.loads(d[field] or "[]")
        except Exception:
            d[field] = []
    if "recipe" in d:
        try:
            d["recipe"] = json.loads(d["recipe"]) if d["recipe"] else None
        except Exception:
            d["recipe"] = None
    return d

def to_dicts(rs):
    return [to_dict(r) for r in rs]

# ── Query helpers ──────────────────────────────────────────────────────────────

def get_member(mid):
    if not mid:
        return None
    return to_dict(get_db().execute("SELECT * FROM members WHERE id=?", (mid,)).fetchone())

def get_book(bid):
    if not bid:
        return None
    return to_dict(get_db().execute("SELECT * FROM books WHERE id=?", (bid,)).fetchone())

def get_all_members():
    return to_dicts(get_db().execute("SELECT * FROM members ORDER BY name").fetchall())

def get_all_books():
    return to_dicts(get_db().execute("SELECT * FROM books ORDER BY date_read").fetchall())

def get_all_meals():
    return to_dicts(get_db().execute("SELECT * FROM meals ORDER BY id").fetchall())

def get_meals_for_book(book_id):
    return to_dicts(get_db().execute(
        "SELECT * FROM meals WHERE book_id=?", (book_id,)
    ).fetchall())

# ── Avatar helper ──────────────────────────────────────────────────────────────

def save_avatar(member_id, file):
    if not file or not file.filename:
        return None
    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_AVATAR_EXTENSIONS:
        return None
    filename = f"member_{member_id}.{ext}"
    file.save(os.path.join(AVATARS_DIR, filename))
    return filename

@app.context_processor
def template_helpers():
    def avatar_url(member, bg="1a1826"):
        if not member:
            return f"https://api.dicebear.com/9.x/fun-emoji/svg?seed=default&backgroundColor={bg}"
        img = member.get("avatar_img") if isinstance(member, dict) else None
        if img:
            return url_for("static", filename=f"avatars/{img}")
        seed = member.get("avatar_seed") or member.get("name", "default")
        return f"https://api.dicebear.com/9.x/fun-emoji/svg?seed={seed}&backgroundColor={bg}"
    return dict(avatar_url=avatar_url)

# ── Enrichment helpers ─────────────────────────────────────────────────────────

def enrich_book(book):
    if not book:
        return None
    book = dict(book)
    book["selected_by_member"] = get_member(book.get("selected_by"))

    rating_rows = get_db().execute(
        "SELECT * FROM ratings WHERE book_id=?", (book["id"],)
    ).fetchall()

    if rating_rows:
        scores = [r["score"] for r in rating_rows]
        book["avg_member_rating"] = round(sum(scores) / len(scores), 2)
        book["member_ratings_list"] = [
            {
                "member":    get_member(r["member_id"]),
                "member_id": r["member_id"],
                "score":     r["score"],
                "review":    r["review"] or "",
            }
            for r in rating_rows
        ]
        book["ratings_by_member_id"] = {
            r["member_id"]: {"score": r["score"], "review": r["review"] or ""}
            for r in rating_rows
        }
    else:
        book["avg_member_rating"] = None
        book["member_ratings_list"] = []
        book["ratings_by_member_id"] = {}

    book["meals"] = [enrich_meal(m) for m in get_meals_for_book(book["id"])]
    return book


def enrich_meal(meal):
    if not meal:
        return None
    meal = dict(meal)
    meal["prepared_by_member"] = get_member(meal.get("prepared_by"))
    meal["book"] = get_book(meal.get("book_id"))
    return meal


def enrich_member(member):
    if not member:
        return None
    member = dict(member)
    db = get_db()

    member["books_selected_list"] = to_dicts(
        db.execute(
            "SELECT * FROM books WHERE selected_by=? ORDER BY date_read", (member["id"],)
        ).fetchall()
    )
    member["meals_cooked_list"] = [
        enrich_meal(m) for m in to_dicts(
            db.execute("SELECT * FROM meals WHERE prepared_by=?", (member["id"],)).fetchall()
        )
    ]

    rating_rows = db.execute(
        "SELECT book_id, score, review FROM ratings WHERE member_id=?", (member["id"],)
    ).fetchall()
    ratings_given = []
    for r in rating_rows:
        book = get_book(r["book_id"])
        if book:
            ratings_given.append({
                "book":   book,
                "score":  r["score"],
                "review": r["review"] or "",
            })
    member["ratings_given"] = ratings_given
    scores = [r["score"] for r in ratings_given]
    member["avg_rating_given"] = round(sum(scores) / len(scores), 2) if scores else None
    return member

# ── Form parsing ───────────────────────────────────────────────────────────────

def parse_lines(text):
    return [ln.strip() for ln in text.splitlines() if ln.strip()]

def parse_tags(text):
    return [t.strip() for t in text.split(",") if t.strip()]

def parse_book_form():
    selected_by_raw = request.form.get("selected_by", "")
    try:
        selected_by = int(selected_by_raw) if selected_by_raw else None
    except ValueError:
        selected_by = None
    return {
        "title":            request.form.get("title", "").strip(),
        "author":           request.form.get("author", "").strip(),
        "genre":            request.form.get("genre", "").strip(),
        "pages":            int(request.form.get("pages") or 0),
        "goodreads_rating": float(request.form.get("goodreads_rating") or 0),
        "year_published":   int(request.form.get("year_published") or 0),
        "date_read":        request.form.get("date_read", "").strip(),
        "selected_by":      selected_by,
        "description":      request.form.get("description", "").strip(),
        "cover_color":      request.form.get("cover_color", "#444444"),
        "cover_accent":     request.form.get("cover_accent", "#888888"),
        "tags":             json.dumps(parse_tags(request.form.get("tags", ""))),
        "event_note":       request.form.get("event_note", "").strip(),
        "goodreads_url":    request.form.get("goodreads_url", "").strip(),
    }

def parse_member_form():
    return {
        "name":           request.form.get("name", "").strip(),
        "nickname":       request.form.get("nickname", "").strip(),
        "avatar_seed":    request.form.get("avatar_seed", "").strip(),
        "fun_facts":      json.dumps(parse_lines(request.form.get("fun_facts", ""))),
        "quotes":         json.dumps(parse_lines(request.form.get("quotes", ""))),
        "favorite_genre": request.form.get("favorite_genre", "").strip(),
        "join_date":      request.form.get("join_date", "").strip(),
        "signature_dish": request.form.get("signature_dish", "").strip(),
    }

def parse_meal_form():
    ingredients = parse_lines(request.form.get("recipe_ingredients", ""))
    steps = parse_lines(request.form.get("recipe_steps", ""))
    recipe = {"ingredients": ingredients, "steps": steps} if (ingredients or steps) else None
    try:
        book_id = int(request.form.get("book_id") or 0)
    except ValueError:
        book_id = 0
    try:
        prepared_by = int(request.form.get("prepared_by") or 0)
    except ValueError:
        prepared_by = 0
    return {
        "book_id":     book_id,
        "dish":        request.form.get("dish", "").strip(),
        "prepared_by": prepared_by,
        "type":        request.form.get("type", "").strip(),
        "description": request.form.get("description", "").strip(),
        "recipe":      json.dumps(recipe) if recipe else None,
    }

# ── Read routes ────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    books   = [enrich_book(b) for b in get_all_books()]
    members = [enrich_member(m) for m in get_all_members()]
    genre_counts = {}
    for b in books:
        genre_counts[b["genre"]] = genre_counts.get(b["genre"], 0) + 1
    recent_book = to_dict(get_db().execute(
        "SELECT * FROM books ORDER BY date_read DESC LIMIT 1"
    ).fetchone())
    if recent_book:
        recent_book = enrich_book(recent_book)
    all_meals = get_all_meals()
    meals_preview = [enrich_meal(m) for m in all_meals[-6:]]
    return render_template(
        "index.html",
        books=books, members=members, genre_counts=genre_counts,
        recent_book=recent_book,
        total_pages=sum(b["pages"] for b in books),
        total_meals=len(all_meals),
        meals_preview=meals_preview,
    )


@app.route("/books")
def books():
    all_books = [enrich_book(b) for b in get_all_books()]
    genres    = sorted(set(b["genre"] for b in all_books if b["genre"]))
    genre_counts = {}
    for b in all_books:
        genre_counts[b["genre"]] = genre_counts.get(b["genre"], 0) + 1
    return render_template("books.html", books=all_books, genres=genres, genre_counts=genre_counts)


@app.route("/books/<int:book_id>")
def book_detail(book_id):
    book = enrich_book(get_book(book_id))
    if not book:
        abort(404)
    return render_template("book_detail.html", book=book, members=get_all_members())


@app.route("/people")
def people():
    return render_template("people.html", members=[enrich_member(m) for m in get_all_members()])


@app.route("/people/<int:member_id>")
def person_detail(member_id):
    member = enrich_member(get_member(member_id))
    if not member:
        abort(404)
    return render_template("person_detail.html", member=member)


@app.route("/meals")
def meals():
    all_meals  = [enrich_meal(m) for m in get_all_meals()]
    meal_types = sorted(set(m["type"] for m in all_meals if m["type"]))
    return render_template("meals.html", meals=all_meals, meal_types=meal_types)


@app.route("/meals/<int:meal_id>")
def meal_detail(meal_id):
    meal = to_dict(get_db().execute("SELECT * FROM meals WHERE id=?", (meal_id,)).fetchone())
    if not meal:
        abort(404)
    return render_template("meal_detail.html", meal=enrich_meal(meal))

# ── Book CRUD ──────────────────────────────────────────────────────────────────

@app.route("/books/new", methods=["GET", "POST"])
def book_new():
    if request.method == "POST":
        f = parse_book_form()
        db = get_db()
        cur = db.execute("""
            INSERT INTO books
                (title, author, genre, pages, goodreads_rating, year_published,
                 date_read, selected_by, description, cover_color, cover_accent,
                 tags, event_note, goodreads_url)
            VALUES
                (:title, :author, :genre, :pages, :goodreads_rating, :year_published,
                 :date_read, :selected_by, :description, :cover_color, :cover_accent,
                 :tags, :event_note, :goodreads_url)
        """, f)
        db.commit()
        flash(f"'{f['title']}' added!", "success")
        return redirect(url_for("book_detail", book_id=cur.lastrowid))
    return render_template("book_form.html", book=None, members=get_all_members(),
                           action=url_for("book_new"))


@app.route("/books/<int:book_id>/edit", methods=["GET", "POST"])
def book_edit(book_id):
    book = get_book(book_id)
    if not book:
        abort(404)
    if request.method == "POST":
        f = {**parse_book_form(), "id": book_id}
        get_db().execute("""
            UPDATE books SET
                title=:title, author=:author, genre=:genre, pages=:pages,
                goodreads_rating=:goodreads_rating, year_published=:year_published,
                date_read=:date_read, selected_by=:selected_by, description=:description,
                cover_color=:cover_color, cover_accent=:cover_accent, tags=:tags,
                event_note=:event_note, goodreads_url=:goodreads_url
            WHERE id=:id
        """, f)
        get_db().commit()
        flash("Book updated.", "success")
        return redirect(url_for("book_detail", book_id=book_id))
    return render_template("book_form.html", book=book, members=get_all_members(),
                           action=url_for("book_edit", book_id=book_id))


@app.route("/books/<int:book_id>/delete", methods=["POST"])
def book_delete(book_id):
    book = get_book(book_id)
    title = book["title"] if book else "Book"
    db = get_db()
    db.execute("DELETE FROM books WHERE id=?", (book_id,))  # meals/ratings cascade
    db.commit()
    flash(f"'{title}' deleted.", "success")
    return redirect(url_for("books"))

# ── Rating CRUD ────────────────────────────────────────────────────────────────

@app.route("/books/<int:book_id>/ratings", methods=["POST"])
def rating_save(book_id):
    if not get_book(book_id):
        abort(404)
    try:
        member_id = int(request.form.get("member_id", 0))
        score     = float(request.form.get("score", 0))
    except ValueError:
        flash("Invalid rating data.", "error")
        return redirect(url_for("book_detail", book_id=book_id))
    review = request.form.get("review", "").strip()
    db = get_db()
    db.execute("""
        INSERT INTO ratings (book_id, member_id, score, review)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(book_id, member_id) DO UPDATE SET score=excluded.score, review=excluded.review
    """, (book_id, member_id, score, review))
    db.commit()
    flash("Rating saved.", "success")
    return redirect(url_for("book_detail", book_id=book_id) + "#ratings")


@app.route("/books/<int:book_id>/ratings/<int:member_id>/delete", methods=["POST"])
def rating_delete(book_id, member_id):
    if not get_book(book_id):
        abort(404)
    db = get_db()
    db.execute("DELETE FROM ratings WHERE book_id=? AND member_id=?", (book_id, member_id))
    db.commit()
    flash("Rating removed.", "success")
    return redirect(url_for("book_detail", book_id=book_id) + "#ratings")

# ── Member CRUD ────────────────────────────────────────────────────────────────

@app.route("/people/new", methods=["GET", "POST"])
def person_new():
    if request.method == "POST":
        f = parse_member_form()
        db = get_db()
        cur = db.execute("""
            INSERT INTO members
                (name, nickname, avatar_seed, fun_facts, quotes,
                 favorite_genre, join_date, signature_dish)
            VALUES
                (:name, :nickname, :avatar_seed, :fun_facts, :quotes,
                 :favorite_genre, :join_date, :signature_dish)
        """, f)
        db.commit()
        new_id = cur.lastrowid
        filename = save_avatar(new_id, request.files.get("avatar_file"))
        if filename:
            db.execute("UPDATE members SET avatar_img=? WHERE id=?", (filename, new_id))
            db.commit()
        flash(f"Welcome, {f['name']}!", "success")
        return redirect(url_for("person_detail", member_id=new_id))
    return render_template("member_form.html", member=None, action=url_for("person_new"))


@app.route("/people/<int:member_id>/edit", methods=["GET", "POST"])
def person_edit(member_id):
    member = get_member(member_id)
    if not member:
        abort(404)
    if request.method == "POST":
        f = {**parse_member_form(), "id": member_id}
        db = get_db()
        db.execute("""
            UPDATE members SET
                name=:name, nickname=:nickname, avatar_seed=:avatar_seed,
                fun_facts=:fun_facts, quotes=:quotes, favorite_genre=:favorite_genre,
                join_date=:join_date, signature_dish=:signature_dish
            WHERE id=:id
        """, f)
        filename = save_avatar(member_id, request.files.get("avatar_file"))
        if filename:
            db.execute("UPDATE members SET avatar_img=? WHERE id=?", (filename, member_id))
        db.commit()
        flash("Profile updated.", "success")
        return redirect(url_for("person_detail", member_id=member_id))
    return render_template("member_form.html", member=member,
                           action=url_for("person_edit", member_id=member_id))


@app.route("/people/<int:member_id>/delete", methods=["POST"])
def person_delete(member_id):
    member = get_member(member_id)
    name = member["name"] if member else "Member"
    db = get_db()
    db.execute("DELETE FROM members WHERE id=?", (member_id,))
    db.commit()
    flash(f"{name} removed.", "success")
    return redirect(url_for("people"))

# ── Meal CRUD ──────────────────────────────────────────────────────────────────

@app.route("/meals/new", methods=["GET", "POST"])
def meal_new():
    if request.method == "POST":
        f = parse_meal_form()
        db = get_db()
        cur = db.execute("""
            INSERT INTO meals (book_id, dish, prepared_by, type, description, recipe)
            VALUES (:book_id, :dish, :prepared_by, :type, :description, :recipe)
        """, f)
        db.commit()
        flash(f"'{f['dish']}' added!", "success")
        return redirect(url_for("meal_detail", meal_id=cur.lastrowid))
    book_id_hint = request.args.get("book_id", type=int)
    return render_template("meal_form.html", meal=None,
                           members=get_all_members(), books=get_all_books(),
                           action=url_for("meal_new"), book_id_hint=book_id_hint)


@app.route("/meals/<int:meal_id>/edit", methods=["GET", "POST"])
def meal_edit(meal_id):
    meal = to_dict(get_db().execute("SELECT * FROM meals WHERE id=?", (meal_id,)).fetchone())
    if not meal:
        abort(404)
    if request.method == "POST":
        f = {**parse_meal_form(), "id": meal_id}
        get_db().execute("""
            UPDATE meals SET book_id=:book_id, dish=:dish, prepared_by=:prepared_by,
                type=:type, description=:description, recipe=:recipe
            WHERE id=:id
        """, f)
        get_db().commit()
        flash("Dish updated.", "success")
        return redirect(url_for("meal_detail", meal_id=meal_id))
    return render_template("meal_form.html", meal=meal,
                           members=get_all_members(), books=get_all_books(),
                           action=url_for("meal_edit", meal_id=meal_id), book_id_hint=None)


@app.route("/meals/<int:meal_id>/delete", methods=["POST"])
def meal_delete(meal_id):
    meal = to_dict(get_db().execute("SELECT * FROM meals WHERE id=?", (meal_id,)).fetchone())
    dish = meal["dish"] if meal else "Dish"
    db = get_db()
    db.execute("DELETE FROM meals WHERE id=?", (meal_id,))
    db.commit()
    flash(f"'{dish}' removed.", "success")
    return redirect(url_for("meals"))


# ── Startup ────────────────────────────────────────────────────────────────────

with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(debug=True)
