"""
Scrape Hamstouille blog (https://www.hamstouille.fr/blog and /blog/{id}).

Outputs:
    data/blog.json  — list of articles with sanitised content
"""
import argparse
import json
import re
import time
from pathlib import Path

import requests

from scrape_helpers import (
    BASE_URL, COOKIE,
    sanitize, to_text, find_cross_refs, absolutize,
)

DATA_DIR = Path(__file__).parent / "data"
OUT_FILE = DATA_DIR / "blog.json"
LISTING_CACHE = "/tmp/ht_blog.html"


def fetch(path, session):
    r = session.get(BASE_URL + path, cookies=COOKIE, timeout=20, allow_redirects=False)
    if r.status_code in (301, 302):
        raise RuntimeError(f"redirect from {path} to {r.headers.get('location')!r} — session expired?")
    r.raise_for_status()
    return r.text


def discover_articles(html):
    """Return [{id, url, title, thumbnail, category}] from the listing.

    Categories are delimited by:
        <h3 class="text-color-green text-center mt-4 mb-4">CATEGORY NAME</h3>
    Each article appears as an <a href="/blog/{id}"> further along.
    Walk the document linearly so each article is tagged with the most recent
    preceding category.
    """
    articles = []
    seen = set()

    # The page starts with a "Voir les catégories" nav accordion that lists
    # every article as quick-links — those would shadow the real category
    # h3s. Skip ahead to the first real category h3.
    first_h3 = re.search(
        r'<h3[^>]*class="[^"]*text-color-green[^"]*text-center[^"]*"[^>]*>',
        html,
    )
    if first_h3:
        html = html[first_h3.start():]

    # Collect (position, kind, payload) markers for both categories and cards.
    markers = []
    for cm in re.finditer(
        r'<h3[^>]*class="[^"]*text-color-green[^"]*text-center[^"]*"[^>]*>(.*?)</h3>',
        html, re.DOTALL,
    ):
        markers.append((cm.start(), "cat", re.sub(r"\s+", " ", cm.group(1)).strip()))
    for am in re.finditer(
        r'<a[^>]+href="(/blog/(\d+))"[^>]*>(.*?)</a>',
        html, re.DOTALL,
    ):
        markers.append((am.start(), "art", am))
    markers.sort(key=lambda x: x[0])

    current_cat = None
    for _, kind, payload in markers:
        if kind == "cat":
            current_cat = payload
            continue
        am = payload
        path = am.group(1)
        aid = int(am.group(2))
        if aid in seen:
            continue
        seen.add(aid)
        inner = am.group(3)
        title_m = re.search(r'title="([^"]+)"', inner) or re.search(r'<h[1-6][^>]*>([^<]+)</h', inner)
        title = (title_m.group(1).strip() if title_m else "").replace("&nbsp;", " ")
        img_m = re.search(r'src="([^"]+)"', inner)
        thumbnail = absolutize(img_m.group(1)) if img_m else None
        articles.append({
            "id": aid,
            "url": path,
            "title": title,
            "thumbnail": thumbnail,
            "category": current_cat,
        })
    articles.sort(key=lambda a: a["id"])
    return articles


def parse_article(html, meta):
    """Parse a /blog/{id} page into a structured record."""
    rec = dict(meta)

    title_m = re.search(
        r'<h1[^>]*class="[^"]*blog-title[^"]*"[^>]*>(.*?)</h1>',
        html, re.DOTALL,
    )
    if title_m:
        rec["title"] = re.sub(r"\s+", " ", title_m.group(1)).strip()

    # Hero image (first content-blog row contains a top img)
    hero_m = re.search(
        r'class="row[^"]*content-blog"[^>]*>(.*?)</div>\s*</div>',
        html, re.DOTALL,
    )
    hero_html = hero_m.group(1) if hero_m else ""
    hero_img_m = re.search(r'<img[^>]+class="img-fluid"[^>]+src="([^"]+)"', hero_html)
    if hero_img_m:
        rec["hero_image"] = absolutize(hero_img_m.group(1))
    # Intro (text in col-md-8 of hero row)
    intro_m = re.search(r'<div class="col-md-8">(.*?)</div>\s*</div>', hero_html, re.DOTALL)
    intro_html = intro_m.group(1) if intro_m else ""

    # Body: the SECOND content-blog (no "row" prefix), spanning until the
    # SECOND "Retour au blog" button (the first one sits above the title).
    body_section = html[hero_m.end():] if hero_m else html
    end_matches = list(re.finditer(
        r'<a[^>]+href="/blog#article\d+"[^>]*>Retour au blog</a>',
        body_section,
    ))
    if end_matches:
        body_section = body_section[:end_matches[-1].start()]
    body_m = re.search(
        r'<div class="content-blog">(.*)',
        body_section, re.DOTALL,
    )
    body_html = body_m.group(1) if body_m else ""
    # The body block is open-ended — close it at the Retour-au-blog button context
    # by trimming any trailing site-chrome (a footer ul listing bebe/bambin).
    body_html = re.sub(
        r'<ul[^>]*>\s*<li[^>]*>\s*<a[^>]*href="/[^"]*"[^>]*>(?:bebe|bambin)[^<]*</a>.*$',
        "", body_html, flags=re.DOTALL | re.IGNORECASE,
    )

    # Sanitise + plaintext
    rec["intro_html"] = sanitize(intro_html)
    rec["intro_text"] = to_text(intro_html)
    rec["content_html"] = sanitize(body_html)
    rec["content_text"] = to_text(body_html)
    rec["cross_references"] = find_cross_refs(intro_html + body_html)

    return rec


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", action="store_true",
                        help="Use cached /tmp listing instead of fetching live")
    parser.add_argument("--limit", type=int, default=0,
                        help="Limit number of articles (0 = all)")
    args = parser.parse_args()

    DATA_DIR.mkdir(exist_ok=True)
    sess = requests.Session()

    if args.cache and Path(LISTING_CACHE).exists():
        listing_html = Path(LISTING_CACHE).read_text()
        print(f"Using cached listing {LISTING_CACHE}")
    else:
        print("Fetching /blog listing...")
        listing_html = fetch("/blog", sess)

    articles = discover_articles(listing_html)
    print(f"Discovered {len(articles)} articles.")

    if args.limit:
        articles = articles[:args.limit]

    out = []
    for i, a in enumerate(articles, 1):
        print(f"  [{i}/{len(articles)}] /blog/{a['id']} — {a.get('title','')[:60]}", end=" ", flush=True)
        try:
            html = fetch(a["url"], sess)
            rec = parse_article(html, a)
            out.append(rec)
            print("OK")
        except Exception as e:
            print(f"FAIL: {e}")
        time.sleep(0.4)

    OUT_FILE.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"\nSaved {len(out)} articles to {OUT_FILE} ({OUT_FILE.stat().st_size//1024} KB)")


if __name__ == "__main__":
    main()
