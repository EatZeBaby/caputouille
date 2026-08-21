"""
Bambin (1-6 ans) scraper for bambin.hamstouille.fr.

Reuses the existing www-scraper parsing logic (scraper.py, scrape_helpers.py)
but points BASE_URL/COOKIE at the bambin subdomain. Outputs live in data/
under bambin_*.json and are merged into the app by merge_bambin.py.

Sections handled:
  recipes  -> data/bambin_recipes.json      (listing like /recettes)
  blog     -> data/bambin_blog.json          (listing like /blog)
  batch    -> data/bambin_batch.json         (/batch-cooking + detail pages)
  assiette -> data/bambin_assiette.json      (accordion doc, one page)
  qcnmp    -> data/bambin_qcnmp.json          (accordion doc, one page)

Usage:
  python3 scraper_bambin.py recipes [--limit N | --all]
  python3 scraper_bambin.py blog [--limit N]
  python3 scraper_bambin.py batch [--limit N]
  python3 scraper_bambin.py assiette
  python3 scraper_bambin.py qcnmp
"""
import argparse
import json
import os
import re
import time
from pathlib import Path

import requests

# ── Point the shared modules at bambin BEFORE using their helpers ──
# The session cookie expires; pass a fresh one via BAMBIN_PHPSESSID
#   export BAMBIN_PHPSESSID=xxxxx   (grab it from a logged-in browser session)
BASE_URL = "https://bambin.hamstouille.fr"
COOKIE = {"PHPSESSID": os.environ.get("BAMBIN_PHPSESSID", "")}

import scrape_helpers
scrape_helpers.BASE_URL = BASE_URL
scrape_helpers.COOKIE = COOKIE
from scrape_helpers import sanitize, to_text, find_cross_refs, absolutize  # noqa: E402

import scraper as www_scraper  # noqa: E402
www_scraper.BASE_URL = BASE_URL
www_scraper.COOKIE = COOKIE

DATA_DIR = Path(__file__).parent / "data"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
})


def fetch(path, allow_redirects=False):
    r = SESSION.get(BASE_URL + path, cookies=COOKIE, timeout=30,
                    allow_redirects=allow_redirects)
    if not allow_redirects and r.status_code in (301, 302):
        raise RuntimeError(f"redirect from {path} to {r.headers.get('location')!r} — session expired?")
    r.raise_for_status()
    return r.text


# ── Recipes (reuse www_scraper parsing) ───────────────────────────

def scrape_recipes(limit=0):
    html = fetch("/recettes")
    index = _discover_recipes(html)
    print(f"Discovered {len(index)} recipes.")
    if limit:
        index = index[:limit]
    out = []
    for i, meta in enumerate(index, 1):
        rid = meta["id"]
        print(f"  [{i}/{len(index)}] {meta['title'][:50]} (id={rid})", end=" ", flush=True)
        try:
            page = fetch(f"/recettes/{rid}")
            # Bambin uses the orange theme; the shared parser keys off the green
            # class names, so normalise the colour before parsing.
            page = page.replace("text-color-orange", "text-color-green") \
                       .replace("separator-orange", "separator-green")
            rec = www_scraper.parse_recipe_page(page, meta)
            out.append(rec)
            print("OK")
        except Exception as e:
            print(f"FAIL: {e}")
        time.sleep(0.35)
    _save("bambin_recipes.json", out)


def _discover_recipes(html):
    """Same logic as www_scraper.discover_recipes but on a supplied page."""
    recipes = []
    for m in re.finditer(r'id="recette(\d+)"\s+data-filtres="([^"]*)"', html):
        recipe_id = m.group(1)
        filter_ids = [f for f in m.group(2).split(",") if f]
        pos = m.start()
        cat_match = None
        for cm in re.finditer(r'data-categorie="(\d+)"', html[:pos]):
            cat_match = cm
        category_id = cat_match.group(1) if cat_match else None
        card_html = html[pos:pos + 2000]
        title_match = re.search(r'title="([^"]+)"', card_html)
        title = title_match.group(1) if title_match else f"Recipe {recipe_id}"
        img_match = re.search(r'src="(/images/recettes/vignettes/[^"]+)"', card_html)
        thumbnail = f"{BASE_URL}{img_match.group(1)}" if img_match else None
        freezable = "fa-snowflake" in card_html
        recipes.append({
            "id": int(recipe_id),
            "title": title,
            "url": f"/recettes/{recipe_id}",
            "category_id": category_id,
            "category": www_scraper.CATEGORIES.get(category_id, category_id),
            "filter_ids": filter_ids,
            "filters": [www_scraper.FILTERS.get(f, f) for f in filter_ids],
            "thumbnail": thumbnail,
            "freezable": freezable,
        })
    recipes.sort(key=lambda r: r["id"])
    return recipes


# ── Blog (reuse scraper_blog parsing) ─────────────────────────────

def discover_blog(html):
    """Bambin listing cards: <a href="/blog/N">Title</a> (title is the link text)."""
    articles, titles = [], {}
    for m in re.finditer(r'<a[^>]+href="/blog/(\d+)"[^>]*>(.*?)</a>', html, re.DOTALL):
        aid = int(m.group(1))
        title = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', m.group(2))).replace("&nbsp;", " ").strip()
        if title and aid not in titles:
            titles[aid] = title
    for aid, title in titles.items():
        articles.append({"id": aid, "url": f"/blog/{aid}", "title": title,
                         "thumbnail": None, "category": None})
    articles.sort(key=lambda a: a["id"])
    return articles


def parse_blog(html, meta):
    """Bambin blog detail: hero row (content-blog-bambin) + standalone body block."""
    rec = dict(meta)
    tm = re.search(r'blog-title[^>]*>(.*?)</h1>', html, re.DOTALL)
    if tm:
        rec["title"] = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', tm.group(1))).strip()
    foot = html.find("<footer")
    region = html[:foot] if foot != -1 else html

    hero = re.search(r'<div class="row[^"]*content-blog[^"]*">(.*?)(?=<div class="content-blog)',
                     region, re.DOTALL)
    hero_html = hero.group(1) if hero else ""
    him = re.search(r'<img[^>]+src="([^"]+)"', hero_html)
    if him:
        rec["hero_image"] = absolutize(him.group(1))
    intro_m = re.search(r'<div class="col-md-8">(.*?)</div>\s*</div>', hero_html, re.DOTALL)
    intro_html = intro_m.group(1) if intro_m else ""

    body_m = re.search(r'<div class="content-blog[^"]*">(.*)', region, re.DOTALL)
    body_html = body_m.group(1) if body_m else ""
    body_html = re.split(r'<a[^>]+href="/blog#article', body_html)[0]

    rec["intro_html"] = sanitize(intro_html)
    rec["intro_text"] = to_text(intro_html)
    rec["content_html"] = sanitize(body_html)
    rec["content_text"] = to_text(body_html)
    rec["cross_references"] = find_cross_refs(intro_html + body_html)
    return rec


def scrape_blog(limit=0):
    listing = fetch("/blog")
    articles = discover_blog(listing)
    print(f"Discovered {len(articles)} blog articles.")
    if limit:
        articles = articles[:limit]
    out = []
    for i, a in enumerate(articles, 1):
        print(f"  [{i}/{len(articles)}] /blog/{a['id']} — {a.get('title','')[:50]}", end=" ", flush=True)
        try:
            page = fetch(a["url"])
            rec = parse_blog(page, a)
            out.append(rec)
            print("OK")
        except Exception as e:
            print(f"FAIL: {e}")
        time.sleep(0.35)
    _save("bambin_blog.json", out)


# ── Batch cooking (listing + detail pages) ────────────────────────

def discover_batch(html):
    """Walk the listing: h3 month headers + batch-cooking links (title attr)."""
    markers = []
    for m in re.finditer(r'<h3[^>]*>(.*?)</h3>', html, re.DOTALL):
        t = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', m.group(1))).strip()
        if t:
            markers.append((m.start(), "month", t))
    for m in re.finditer(r'<a[^>]+href="/batch-cooking/(\d+)"[^>]*title="([^"]*)"', html):
        markers.append((m.start(), "batch", (int(m.group(1)), m.group(2).strip())))
    markers.sort(key=lambda x: x[0])
    items, month = [], None
    for _, kind, payload in markers:
        if kind == "month":
            month = payload
        else:
            bid, title = payload
            items.append({"id": bid, "title": title, "month": month,
                          "url": f"/batch-cooking/{bid}"})
    return items


def parse_batch_detail(html, meta):
    rec = dict(meta)
    h1 = re.search(r'<h1[^>]*class="[^"]*blog-title[^"]*"[^>]*>(.*?)</h1>', html, re.DOTALL)
    # Content = from just after the H1 up to the footer
    start = h1.end() if h1 else 0
    foot = html.find("<footer")
    body = html[start:foot if foot != -1 else len(html)]
    # thumbnail = first carousel image
    img = re.search(r'<img[^>]+class="[^"]*d-block[^"]*"[^>]*src="([^"]+)"', body) \
        or re.search(r'<img[^>]+src="([^"]+)"', body)
    if img:
        rec["thumbnail"] = re.sub(r"(?<!:)//", "/", absolutize(img.group(1)))
    rec["content_html"] = sanitize(body)
    rec["content_text"] = to_text(body)
    rec["cross_references"] = find_cross_refs(body)
    return rec


def scrape_batch(limit=0):
    listing = fetch("/batch-cooking")
    items = discover_batch(listing)
    print(f"Discovered {len(items)} batch-cooking sessions.")
    if limit:
        items = items[:limit]
    out = []
    for i, meta in enumerate(items, 1):
        print(f"  [{i}/{len(items)}] /batch-cooking/{meta['id']} — {meta['title'][:40]}", end=" ", flush=True)
        try:
            page = fetch(meta["url"], allow_redirects=True)
            rec = parse_batch_detail(page, meta)
            out.append(rec)
            print("OK")
        except Exception as e:
            print(f"FAIL: {e}")
        time.sleep(0.35)
    _save("bambin_batch.json", out)


# ── Accordion document sections (dans-assiette, quand-ca-ne-marche-pas) ──

def parse_accordion_doc(html, url_path, title):
    """Flatten every btn-accordeon item into a section (heading + body + media)."""
    rec = {"url": url_path, "title": title}
    # Positions of all accordion toggle buttons
    buttons = list(re.finditer(
        r'<button[^>]*class="[^"]*btn-accordeon[^"]*"[^>]*>(.*?)</button>',
        html, re.DOTALL,
    ))
    foot = html.find("<footer")
    end_all = foot if foot != -1 else len(html)
    sections = []
    for i, b in enumerate(buttons):
        heading = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', b.group(1))).strip()
        if not heading:
            continue
        body_start = b.end()
        body_end = buttons[i + 1].start() if i + 1 < len(buttons) else end_all
        block = html[body_start:body_end]
        body_m = re.search(
            r'<div class="content-blog">(.*?)</div>\s*(?=<video|<div class="row|</div>\s*</div>\s*</div>)',
            block, re.DOTALL,
        )
        body_html = body_m.group(1) if body_m else ""
        videos = sorted({absolutize(m.group(1))
                         for m in re.finditer(r'<source[^>]+src="([^"]+)"', block)})
        images = sorted({absolutize(m.group(1))
                         for m in re.finditer(r'<img[^>]+src="([^"]+)"', block)})
        pdfs = sorted({absolutize(m.group(1))
                       for m in re.finditer(r'href="([^"]+\.pdf)"', block, re.IGNORECASE)})
        # A "point de vue" group header carries no video and starts a new expert block
        level = 1 if (not videos and heading.lower().startswith("le point de vue")) else 2
        sections.append({
            "index": i,
            "level": level,
            "heading": heading,
            "anchor": _slug(heading),
            "content_html": sanitize(body_html),
            "content_text": to_text(body_html),
            "videos": videos,
            "images": images,
            "pdfs": pdfs,
            "cross_references": find_cross_refs(block),
        })
    rec["sections"] = sections
    rec["raw_text"] = "\n\n".join(s["content_text"] for s in sections if s["content_text"])
    all_refs, seen = [], set()
    for s in sections:
        for ref in s["cross_references"]:
            key = (ref["type"], ref["id"])
            if key not in seen:
                seen.add(key)
                all_refs.append(ref)
    rec["cross_references"] = all_refs
    return rec


def _slug(text):
    s = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip().lower()
    return re.sub(r"[\s-]+", "-", s)[:64]


def scrape_assiette():
    html = fetch("/dans-assiette")
    rec = parse_accordion_doc(html, "/dans-assiette", "Dans l'assiette")
    _report_doc(rec)
    _save("bambin_assiette.json", rec)


def scrape_qcnmp():
    html = fetch("/quand-ca-ne-marche-pas")
    rec = parse_accordion_doc(html, "/quand-ca-ne-marche-pas", "Quand ça ne marche pas")
    _report_doc(rec)
    _save("bambin_qcnmp.json", rec)


def _report_doc(rec):
    print(f"Title: {rec['title']} — {len(rec['sections'])} sections")
    for s in rec["sections"]:
        print(f"  {s['index']:>2}. [{s['level']}] {s['heading'][:48]:48s} "
              f"({len(s['videos'])} vid, {len(s['pdfs'])} pdf)")


# ── IO ────────────────────────────────────────────────────────────

def _save(name, data):
    DATA_DIR.mkdir(exist_ok=True)
    p = DATA_DIR / name
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    n = len(data) if isinstance(data, list) else len(data.get("sections", []))
    print(f"\nSaved {n} items to {p} ({p.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("target", choices=["recipes", "blog", "batch", "assiette", "qcnmp"])
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    if args.target == "recipes":
        scrape_recipes(limit=0 if args.all else args.limit)
    elif args.target == "blog":
        scrape_blog(limit=args.limit)
    elif args.target == "batch":
        scrape_batch(limit=args.limit)
    elif args.target == "assiette":
        scrape_assiette()
    elif args.target == "qcnmp":
        scrape_qcnmp()
