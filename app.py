import json
import os
from flask import Flask, render_template, abort, request, redirect, url_for, flash

app = Flask(__name__)
app.secret_key = "book-club-dev-secret"

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# ── Storage helpers ───────────────────────────────────────────────────────────

def load_json(name):
    with open(os.path.join(DATA_DIR, f"{name}.json"), encoding="utf-8") as f:
        return json.load(f)

def save_json(name, data):
    with open(os.path.join(DATA_DIR, f"{name}.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def next_id(items):
    return max((i["id"] for i in items), default=0) + 1

# Reload from disk on every request so edits are always fresh
MEMBERS, BOOKS, MEALS = [], [], []

@app.before_request
def reload_data():
    global MEMBERS, BOOKS, MEALS
    MEMBERS = load_json("members")
    BOOKS   = load_json("books")
    MEALS   = load_json("meals")

# ── Enrichment helpers ────────────────────────────────────────────────────────

def get_member(mid):
    return next((m for m in MEMBERS if m["id"] == mid), None)

def get_book(bid):
    return next((b for b in BOOKS if b["id"] == bid), None)

def get_meals_for_book(book_id):
    return [m for m in MEALS if m["book_id"] == book_id]

def enrich_book(book):
    book = dict(book)
    book["selected_by_member"] = get_member(book.get("selected_by"))
    ratings = book.get("ratings", {})  # dict with string keys
    if ratings:
        scores = [r["score"] for r in ratings.values()]
        book["avg_member_rating"] = round(sum(scores) / len(scores), 2)
        book["member_ratings_list"] = [
            {
                "member": get_member(int(mid)),
                "member_id": int(mid),
                "score": r["score"],
                "review": r.get("review", ""),
            }
            for mid, r in ratings.items()
        ]
    else:
        book["avg_member_rating"] = None
        book["member_ratings_list"] = []
    book["ratings_by_member_id"] = {int(mid): r for mid, r in ratings.items()}
    book["meals"] = [enrich_meal(m) for m in get_meals_for_book(book["id"])]
    return book

def enrich_meal(meal):
    meal = dict(meal)
    meal["prepared_by_member"] = get_member(meal["prepared_by"])
    meal["book"] = get_book(meal["book_id"])
    return meal

def enrich_member(member):
    member = dict(member)
    # Derive books/meals from source data
    member["books_selected_list"] = [b for b in BOOKS if b.get("selected_by") == member["id"]]
    member["meals_cooked_list"] = [enrich_meal(m) for m in MEALS if m["prepared_by"] == member["id"]]
    # Ratings given by this member across all books
    ratings_given = []
    for book in BOOKS:
        r = book.get("ratings", {}).get(str(member["id"]))
        if r:
            ratings_given.append({
                "book": book,
                "score": r["score"],
                "review": r.get("review", ""),
            })
    member["ratings_given"] = ratings_given
    scores = [r["score"] for r in ratings_given]
    member["avg_rating_given"] = round(sum(scores) / len(scores), 2) if scores else None
    return member

# ── Form parsing helpers ──────────────────────────────────────────────────────

def parse_lines(text):
    """Split textarea text into non-empty stripped lines."""
    return [ln.strip() for ln in text.splitlines() if ln.strip()]

def parse_tags(text):
    return [t.strip() for t in text.split(",") if t.strip()]

def parse_book_form():
    """Extract and coerce book fields from request.form."""
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
        "tags":             parse_tags(request.form.get("tags", "")),
    }

def parse_member_form():
    return {
        "name":           request.form.get("name", "").strip(),
        "nickname":       request.form.get("nickname", "").strip(),
        "tagline":        request.form.get("tagline", "").strip(),
        "avatar_seed":    request.form.get("avatar_seed", "").strip(),
        "fun_facts":      parse_lines(request.form.get("fun_facts", "")),
        "quotes":         parse_lines(request.form.get("quotes", "")),
        "favorite_genre": request.form.get("favorite_genre", "").strip(),
        "rating_style":   request.form.get("rating_style", "").strip(),
        "join_date":      request.form.get("join_date", "").strip(),
        "signature_dish": request.form.get("signature_dish", "").strip(),
        "chef_nickname":  request.form.get("chef_nickname", "").strip(),
    }

def parse_meal_form():
    ing_text = request.form.get("recipe_ingredients", "").strip()
    steps_text = request.form.get("recipe_steps", "").strip()
    ingredients = parse_lines(ing_text)
    steps = parse_lines(steps_text)
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
        "recipe":      recipe,
    }

# ── Main read routes ──────────────────────────────────────────────────────────

@app.route("/")
def index():
    books   = [enrich_book(b) for b in BOOKS]
    members = [enrich_member(m) for m in MEMBERS]
    genre_counts = {}
    for b in BOOKS:
        genre_counts[b["genre"]] = genre_counts.get(b["genre"], 0) + 1
    recent_book  = books[-1] if books else None
    meals_preview = [enrich_meal(m) for m in MEALS[-6:]]
    return render_template(
        "index.html",
        books=books, members=members, genre_counts=genre_counts,
        recent_book=recent_book,
        total_pages=sum(b["pages"] for b in BOOKS),
        total_meals=len(MEALS),
        meals_preview=meals_preview,
    )


@app.route("/books")
def books():
    all_books    = [enrich_book(b) for b in BOOKS]
    genres       = sorted(set(b["genre"] for b in BOOKS))
    genre_counts = {}
    for b in BOOKS:
        genre_counts[b["genre"]] = genre_counts.get(b["genre"], 0) + 1
    return render_template("books.html", books=all_books, genres=genres, genre_counts=genre_counts)


@app.route("/books/<int:book_id>")
def book_detail(book_id):
    book = get_book(book_id)
    if not book:
        abort(404)
    return render_template("book_detail.html", book=enrich_book(book), members=MEMBERS)


@app.route("/people")
def people():
    return render_template("people.html", members=[enrich_member(m) for m in MEMBERS])


@app.route("/people/<int:member_id>")
def person_detail(member_id):
    member = get_member(member_id)
    if not member:
        abort(404)
    return render_template("person_detail.html", member=enrich_member(member))


@app.route("/meals")
def meals():
    all_meals  = [enrich_meal(m) for m in MEALS]
    meal_types = sorted(set(m["type"] for m in MEALS))
    return render_template("meals.html", meals=all_meals, meal_types=meal_types)


@app.route("/meals/<int:meal_id>")
def meal_detail(meal_id):
    meal = next((m for m in MEALS if m["id"] == meal_id), None)
    if not meal:
        abort(404)
    return render_template("meal_detail.html", meal=enrich_meal(meal))

# ── Book CRUD ─────────────────────────────────────────────────────────────────

@app.route("/books/new", methods=["GET", "POST"])
def book_new():
    if request.method == "POST":
        data = load_json("books")
        new_book = {"id": next_id(data), "ratings": {}, **parse_book_form()}
        data.append(new_book)
        save_json("books", data)
        flash(f"'{new_book['title']}' added!", "success")
        return redirect(url_for("book_detail", book_id=new_book["id"]))
    return render_template("book_form.html", book=None, members=MEMBERS, action=url_for("book_new"))


@app.route("/books/<int:book_id>/edit", methods=["GET", "POST"])
def book_edit(book_id):
    data = load_json("books")
    book = next((b for b in data if b["id"] == book_id), None)
    if not book:
        abort(404)
    if request.method == "POST":
        updates = parse_book_form()
        book.update(updates)
        save_json("books", data)
        flash("Book updated.", "success")
        return redirect(url_for("book_detail", book_id=book_id))
    return render_template("book_form.html", book=book, members=MEMBERS,
                           action=url_for("book_edit", book_id=book_id))


@app.route("/books/<int:book_id>/delete", methods=["POST"])
def book_delete(book_id):
    books_data = load_json("books")
    book = next((b for b in books_data if b["id"] == book_id), None)
    title = book["title"] if book else "Book"
    books_data = [b for b in books_data if b["id"] != book_id]
    save_json("books", books_data)
    # Also remove meals for this book
    meals_data = [m for m in load_json("meals") if m["book_id"] != book_id]
    save_json("meals", meals_data)
    flash(f"'{title}' deleted.", "success")
    return redirect(url_for("books"))

# ── Rating CRUD (inline on book detail) ──────────────────────────────────────

@app.route("/books/<int:book_id>/ratings", methods=["POST"])
def rating_save(book_id):
    books_data = load_json("books")
    book = next((b for b in books_data if b["id"] == book_id), None)
    if not book:
        abort(404)
    try:
        member_id = int(request.form.get("member_id", 0))
        score     = float(request.form.get("score", 0))
    except ValueError:
        flash("Invalid rating data.", "error")
        return redirect(url_for("book_detail", book_id=book_id))
    review = request.form.get("review", "").strip()
    if "ratings" not in book:
        book["ratings"] = {}
    book["ratings"][str(member_id)] = {"score": score, "review": review}
    save_json("books", books_data)
    flash("Rating saved.", "success")
    return redirect(url_for("book_detail", book_id=book_id) + "#ratings")


@app.route("/books/<int:book_id>/ratings/<int:member_id>/delete", methods=["POST"])
def rating_delete(book_id, member_id):
    books_data = load_json("books")
    book = next((b for b in books_data if b["id"] == book_id), None)
    if not book:
        abort(404)
    book.get("ratings", {}).pop(str(member_id), None)
    save_json("books", books_data)
    flash("Rating removed.", "success")
    return redirect(url_for("book_detail", book_id=book_id) + "#ratings")

# ── Member CRUD ───────────────────────────────────────────────────────────────

@app.route("/people/new", methods=["GET", "POST"])
def person_new():
    if request.method == "POST":
        data = load_json("members")
        new_member = {"id": next_id(data), **parse_member_form()}
        data.append(new_member)
        save_json("members", data)
        flash(f"Welcome, {new_member['name']}!", "success")
        return redirect(url_for("person_detail", member_id=new_member["id"]))
    return render_template("member_form.html", member=None, action=url_for("person_new"))


@app.route("/people/<int:member_id>/edit", methods=["GET", "POST"])
def person_edit(member_id):
    data = load_json("members")
    member = next((m for m in data if m["id"] == member_id), None)
    if not member:
        abort(404)
    if request.method == "POST":
        member.update(parse_member_form())
        save_json("members", data)
        flash("Profile updated.", "success")
        return redirect(url_for("person_detail", member_id=member_id))
    return render_template("member_form.html", member=member,
                           action=url_for("person_edit", member_id=member_id))


@app.route("/people/<int:member_id>/delete", methods=["POST"])
def person_delete(member_id):
    data = load_json("members")
    member = next((m for m in data if m["id"] == member_id), None)
    name = member["name"] if member else "Member"
    save_json("members", [m for m in data if m["id"] != member_id])
    flash(f"{name} removed.", "success")
    return redirect(url_for("people"))

# ── Meal CRUD ─────────────────────────────────────────────────────────────────

@app.route("/meals/new", methods=["GET", "POST"])
def meal_new():
    if request.method == "POST":
        data = load_json("meals")
        new_meal = {"id": next_id(data), **parse_meal_form()}
        data.append(new_meal)
        save_json("meals", data)
        flash(f"'{new_meal['dish']}' added!", "success")
        return redirect(url_for("meal_detail", meal_id=new_meal["id"]))
    book_id_hint = request.args.get("book_id", type=int)
    return render_template("meal_form.html", meal=None, members=MEMBERS, books=BOOKS,
                           action=url_for("meal_new"), book_id_hint=book_id_hint)


@app.route("/meals/<int:meal_id>/edit", methods=["GET", "POST"])
def meal_edit(meal_id):
    data = load_json("meals")
    meal = next((m for m in data if m["id"] == meal_id), None)
    if not meal:
        abort(404)
    if request.method == "POST":
        meal.update(parse_meal_form())
        save_json("meals", data)
        flash("Dish updated.", "success")
        return redirect(url_for("meal_detail", meal_id=meal_id))
    return render_template("meal_form.html", meal=meal, members=MEMBERS, books=BOOKS,
                           action=url_for("meal_edit", meal_id=meal_id), book_id_hint=None)


@app.route("/meals/<int:meal_id>/delete", methods=["POST"])
def meal_delete(meal_id):
    data = load_json("meals")
    meal = next((m for m in data if m["id"] == meal_id), None)
    dish = meal["dish"] if meal else "Dish"
    save_json("meals", [m for m in data if m["id"] != meal_id])
    flash(f"'{dish}' removed.", "success")
    return redirect(url_for("meals"))


if __name__ == "__main__":
    app.run(debug=True)
