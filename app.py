from flask import Flask, render_template, abort
from data import MEMBERS, BOOKS, MEALS

app = Flask(__name__)


def get_member(member_id):
    return next((m for m in MEMBERS if m["id"] == member_id), None)


def get_book(book_id):
    return next((b for b in BOOKS if b["id"] == book_id), None)


def get_meals_for_book(book_id):
    return [m for m in MEALS if m["book_id"] == book_id]


def enrich_book(book):
    """Attach derived fields to a book dict."""
    book = dict(book)
    book["selected_by_member"] = get_member(book["selected_by"])
    ratings = book.get("ratings", {})
    if ratings:
        scores = [r["score"] for r in ratings.values()]
        book["avg_member_rating"] = round(sum(scores) / len(scores), 2)
        book["member_ratings_list"] = [
            {"member": get_member(mid), "score": r["score"], "review": r["review"]}
            for mid, r in ratings.items()
        ]
    else:
        book["avg_member_rating"] = None
        book["member_ratings_list"] = []
    book["meals"] = [enrich_meal(m) for m in get_meals_for_book(book["id"])]
    return book


def enrich_meal(meal):
    meal = dict(meal)
    meal["prepared_by_member"] = get_member(meal["prepared_by"])
    meal["book"] = get_book(meal["book_id"])
    return meal


def enrich_member(member):
    member = dict(member)
    member["books_selected_list"] = [get_book(bid) for bid in member["books_selected"]]
    member["meals_cooked_list"] = [
        enrich_meal(m) for m in MEALS if m["id"] in member["meals_cooked"]
    ]
    # Compute average rating given across all books
    all_ratings = []
    for book in BOOKS:
        r = book.get("ratings", {}).get(member["id"])
        if r:
            all_ratings.append(r["score"])
    member["avg_rating_given"] = (
        round(sum(all_ratings) / len(all_ratings), 2) if all_ratings else None
    )
    member["ratings_given"] = [
        {
            "book": get_book(book["id"]),
            "score": book["ratings"][member["id"]]["score"],
            "review": book["ratings"][member["id"]]["review"],
        }
        for book in BOOKS
        if member["id"] in book.get("ratings", {})
    ]
    return member


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    books = [enrich_book(b) for b in BOOKS]
    members = [enrich_member(m) for m in MEMBERS]

    # Genre breakdown for chart
    genre_counts = {}
    for b in BOOKS:
        genre_counts[b["genre"]] = genre_counts.get(b["genre"], 0) + 1

    # Recent book
    recent_book = books[-1] if books else None

    meals_preview = [enrich_meal(m) for m in MEALS[-6:]]

    return render_template(
        "index.html",
        books=books,
        members=members,
        genre_counts=genre_counts,
        recent_book=recent_book,
        total_pages=sum(b["pages"] for b in BOOKS),
        total_meals=len(MEALS),
        meals_preview=meals_preview,
    )


@app.route("/books")
def books():
    all_books = [enrich_book(b) for b in BOOKS]
    genres = sorted(set(b["genre"] for b in BOOKS))

    # Genre breakdown data for chart
    genre_counts = {}
    for b in BOOKS:
        genre_counts[b["genre"]] = genre_counts.get(b["genre"], 0) + 1

    return render_template("books.html", books=all_books, genres=genres, genre_counts=genre_counts)


@app.route("/books/<int:book_id>")
def book_detail(book_id):
    book = get_book(book_id)
    if not book:
        abort(404)
    book = enrich_book(book)
    return render_template("book_detail.html", book=book)


@app.route("/people")
def people():
    all_members = [enrich_member(m) for m in MEMBERS]
    return render_template("people.html", members=all_members)


@app.route("/people/<int:member_id>")
def person_detail(member_id):
    member = get_member(member_id)
    if not member:
        abort(404)
    member = enrich_member(member)
    return render_template("person_detail.html", member=member)


@app.route("/meals")
def meals():
    all_meals = [enrich_meal(m) for m in MEALS]
    meal_types = sorted(set(m["type"] for m in MEALS))
    return render_template("meals.html", meals=all_meals, meal_types=meal_types)


@app.route("/meals/<int:meal_id>")
def meal_detail(meal_id):
    meal = next((m for m in MEALS if m["id"] == meal_id), None)
    if not meal:
        abort(404)
    meal = enrich_meal(meal)
    return render_template("meal_detail.html", meal=meal)


if __name__ == "__main__":
    app.run(debug=True)
