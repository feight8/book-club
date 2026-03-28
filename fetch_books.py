"""
Fetch real book data from Goodreads for every book in books.json.
Run once:  python fetch_books.py

Uses direct Goodreads book IDs for known books to avoid picking up
study guides and summary books from search results.
"""

import json, time, re, os
import requests
from bs4 import BeautifulSoup

DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "books.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Direct Goodreads URLs keyed by our book ID.
# These bypass the search step entirely to guarantee the right book.
KNOWN_URLS = {
    1:  "https://www.goodreads.com/book/show/270032.Seven_Years_in_Tibet",
    2:  "https://www.goodreads.com/book/show/58416952-the-will-of-the-many",
    3:  "https://www.goodreads.com/book/show/781182.Barbarians_at_the_Gate",
    4:  "https://www.goodreads.com/book/show/20518872-the-three-body-problem",
    5:  "https://www.goodreads.com/book/show/42389.Band_of_Brothers",
    6:  "https://www.goodreads.com/book/show/34454589-the-handmaid-s-tale",
    7:  "https://www.goodreads.com/book/show/375802.Ender_s_Game",
    8:  "https://www.goodreads.com/book/show/139069.Endurance",
    9:  "https://www.goodreads.com/book/show/37542581-the-spy-and-the-traitor",
    10: "https://www.goodreads.com/book/show/96647.Scar_Tissue",
    11: "https://www.goodreads.com/book/show/29588376-the-lies-of-locke-lamora",
    12: "https://www.goodreads.com/book/show/34066798-a-gentleman-in-moscow",
    13: "https://www.goodreads.com/book/show/220458600-the-fort-bragg-cartel",
    14: "https://www.goodreads.com/book/show/60194162-demon-copperhead",
    15: "https://www.goodreads.com/book/show/205478762-playground",
}

SKIP_TERMS = {
    "study guide", "supersummary", "summary", "workbook",
    "analysis", "review guide", "gradesaver", "sparknotes",
}


def search_goodreads(title: str, author: str = "") -> str | None:
    """Fallback search used when no known URL is available."""
    q = requests.utils.quote(f'"{title}" {author}'.strip())
    resp = requests.get(
        f"https://www.goodreads.com/search?q={q}",
        headers=HEADERS, timeout=15,
    )
    soup = BeautifulSoup(resp.text, "html.parser")
    for link in soup.select("a.bookTitle"):
        text = link.get_text(strip=True).lower()
        if any(skip in text for skip in SKIP_TERMS):
            continue
        href = link.get("href", "").split("?")[0]
        if href:
            return "https://www.goodreads.com" + href
    return None


def fetch_book_data(url: str) -> dict:
    """Extract metadata from a Goodreads book page via its Schema.org JSON-LD."""
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    canonical = resp.url

    # Goodreads pages have multiple JSON-LD blocks; find the one typed "Book"
    ld = None
    for script in soup.find_all("script", type="application/ld+json"):
        if not script.string:
            continue
        try:
            data = json.loads(script.string)
        except Exception:
            continue
        if isinstance(data, dict) and data.get("@type") == "Book":
            ld = data
            break
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("@type") == "Book":
                    ld = item
                    break
            if ld:
                break

    if not ld:
        return {}

    # Author(s)
    raw = ld.get("author", [])
    if isinstance(raw, dict):
        raw = [raw]
    author_str = ", ".join(
        a.get("name", "") for a in (raw or []) if isinstance(a, dict)
    )

    # Year — check JSON-LD datePublished, then "First published YYYY" in page text
    year = 0
    date_str = str(ld.get("datePublished", "") or "")
    m = re.search(r"\d{4}", date_str)
    if m:
        year = int(m.group())
    if not year:
        # Goodreads shows "First published Month DD, YYYY" in the details section
        for pattern in [
            r"First published\s+\w+\s+\d+,?\s+(\d{4})",
            r"First published\s+(\d{4})",
            r"Published\s+\w+\s+\d+\w*\s+(\d{4})",
            r"Published.*?(\d{4})",
        ]:
            m2 = re.search(pattern, soup.get_text(" "))
            if m2:
                year = int(m2.group(1))
                break

    # Rating
    agg = ld.get("aggregateRating", {}) or {}
    try:
        rating = round(float(agg.get("ratingValue") or 0), 2)
    except (ValueError, TypeError):
        rating = 0.0

    # Pages
    try:
        pages = int(ld.get("numberOfPages") or 0)
    except (ValueError, TypeError):
        pages = 0

    # Description — strip any embedded HTML
    raw_desc = ld.get("description", "") or ""
    desc = BeautifulSoup(raw_desc, "html.parser").get_text(separator=" ").strip()

    # Cover image
    cover_img = ld.get("image", "") or ""

    return {
        "author":           author_str,
        "pages":            pages,
        "description":      desc,
        "goodreads_rating": rating,
        "year_published":   year,
        "goodreads_url":    canonical,
        "cover_img":        cover_img,
    }


def run():
    with open(DATA_FILE, encoding="utf-8") as f:
        books = json.load(f)

    for book in books:
        bid   = book["id"]
        title = book["title"]
        print(f"\n[{bid:>2}] {title}")

        try:
            url = KNOWN_URLS.get(bid) or search_goodreads(title, book.get("author", ""))
            if not url:
                print("     NOT FOUND on Goodreads - skipping")
                continue
            print(f"     URL -> {url}")

            details = fetch_book_data(url)
            if not details:
                print("     Could not parse page - skipping")
                continue

            # Only update if Goodreads returned something sensible
            for field in ("author", "pages", "description",
                          "goodreads_rating", "year_published", "goodreads_url", "cover_img"):
                val = details.get(field)
                if val:
                    book[field] = val
            # Title: only update if ours looks wrong (e.g. still contains "Study Guide")
            gr_title = details.get("title", "")
            if gr_title and not any(s in book["title"].lower() for s in SKIP_TERMS):
                pass  # keep our clean title
            elif gr_title:
                book["title"] = gr_title

            print(
                f"     -> {details.get('author')} | "
                f"{details.get('pages')}p | "
                f"{details.get('goodreads_rating')} stars | "
                f"{details.get('year_published')}"
            )
        except Exception as e:
            print(f"     ERROR: {e}")

        time.sleep(1.5)   # be polite

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(books, f, indent=2, ensure_ascii=False)
    print("\nDone. books.json updated.")


if __name__ == "__main__":
    run()
