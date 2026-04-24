"""
Scrape Hamstouille weekly menus (https://www.hamstouille.fr/menus and /menus/{id}).

Outputs:
    data/menus.json  — list of menus with day-by-day meal breakdown
                       and recipe cross-references.
"""
import argparse
import json
import re
import time
from datetime import date, timedelta
from pathlib import Path

import requests

from scrape_helpers import BASE_URL, COOKIE, to_text, absolutize

# Anchor used to extrapolate missing week dates. This corresponds to menu #17
# (confirmed from the live site: "Semaine du 20/04/2026 au 26/04/2026").
# Every menu is a consecutive Monday-Sunday window, so menu N starts on
# ANCHOR_DATE + (N - ANCHOR_ID) × 7 days.
ANCHOR_ID = 17
ANCHOR_DATE = date(2026, 4, 20)  # Lundi

DATA_DIR = Path(__file__).parent / "data"
OUT_FILE = DATA_DIR / "menus.json"
LISTING_CACHE = "/tmp/ht_menus.html"

DAYS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
MEAL_HEADERS = {"petit déjeuner", "déjeuner", "goûter", "gouter", "dîner", "diner"}


def _french_to_iso(d):
    """'20/04/2026' -> '2026-04-20'."""
    dd, mm, yyyy = d.split("/")
    return f"{yyyy}-{mm}-{dd}"


def fetch(path, session):
    r = session.get(BASE_URL + path, cookies=COOKIE, timeout=20, allow_redirects=False)
    if r.status_code in (301, 302):
        raise RuntimeError(f"redirect from {path} — session expired?")
    r.raise_for_status()
    return r.text


def discover_menus(html):
    """Return [{id, week_label}] from the listing."""
    items = []
    seen = set()
    # Anchors look like <a href="menus/17">
    for a_match in re.finditer(
        r'<a[^>]+href="(?:/)?menus/(\d+)"[^>]*>(.*?)</a>',
        html, re.DOTALL,
    ):
        mid = int(a_match.group(1))
        if mid in seen:
            continue
        seen.add(mid)
        items.append({"id": mid, "url": f"/menus/{mid}"})
    # Pull week labels from h2 ordering
    h2_labels = re.findall(
        r'<h2[^>]*class="[^"]*text-color-green[^"]*"[^>]*>(.*?)</h2>',
        html, re.DOTALL,
    )
    h2_labels = [re.sub(r"\s+", " ", l).strip() for l in h2_labels]
    for it, label in zip(items, h2_labels):
        it["week_label"] = label
    items.sort(key=lambda x: x["id"])
    return items


def parse_items(li_html):
    """A meal cell <li>...</li>: split by <br>, each chunk is a span (with optional <a>)."""
    items = []
    # Split on <br/> or <br>
    chunks = re.split(r'<br\s*/?>', li_html)
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        # Recipe link?
        a_m = re.search(r"<a[^>]+href=['\"]/recettes/(\d+)['\"][^>]*>(.*?)</a>", chunk, re.DOTALL)
        if a_m:
            text = to_text(a_m.group(2)) or to_text(chunk)
            items.append({
                "text": text,
                "recipe_id": int(a_m.group(1)),
                "url": f"/recettes/{a_m.group(1)}",
            })
            continue
        text = to_text(chunk)
        if text:
            items.append({"text": text})
    return items


def parse_menu(html, meta):
    """Parse a /menus/{id} page into structured data."""
    rec = dict(meta)

    title_m = re.search(
        r'<h1[^>]*class="[^"]*text-color-green[^"]*"[^>]*>(.*?)</h1>',
        html, re.DOTALL,
    )
    raw_title = re.sub(r"\s+", " ", title_m.group(1)).strip() if title_m else ""
    # Parse real dates if present. Format: "Semaine du DD/MM/YYYY au DD/MM/YYYY".
    date_m = re.search(r"(\d{2}/\d{2}/\d{4})\s+au\s+(\d{2}/\d{2}/\d{4})", raw_title)
    if date_m:
        rec["week_start"] = _french_to_iso(date_m.group(1))
        rec["week_end"] = _french_to_iso(date_m.group(2))
        rec["title"] = raw_title
        rec["dates_computed"] = False
    else:
        # Missing in the source HTML — extrapolate from the anchor.
        start = ANCHOR_DATE + timedelta(days=7 * (meta["id"] - ANCHOR_ID))
        end = start + timedelta(days=6)
        rec["week_start"] = start.isoformat()
        rec["week_end"] = end.isoformat()
        rec["title"] = f"Semaine du {start.strftime('%d/%m/%Y')} au {end.strftime('%d/%m/%Y')}"
        rec["dates_computed"] = True

    # The desktop layout is a series of "row desktop-tab-menu" blocks.
    # Each block holds:
    #   - 7 day cards (col-md-2 col-menu) for ONE meal type
    #   - The day cards contain card-header (day name) + h5 (meal type) + li (items)
    # We want output keyed by day → list of {meal, items}.
    days_data = {d: [] for d in DAYS}
    ideas = []  # {meal_label, url} for /blog links surfacing in meal headers

    # First, capture the "Idées de petit déjeuner ici" / "Idées de goûter ici" blog links
    for h5_m in re.finditer(
        r'<h5[^>]*>\s*<a[^>]+href="(/blog/\d+)"[^>]*>([^<]+)</a>',
        html,
    ):
        ideas.append({
            "url": h5_m.group(1),
            "label": re.sub(r"\s+", " ", h5_m.group(2)).strip(),
        })

    # Walk the desktop-tab-menu rows
    for row_m in re.finditer(
        r'<div class="row desktop-tab-menu">(.*?)(?=<div class="row desktop-tab-menu">|<div class="row mobile-tab-menu">|$)',
        html, re.DOTALL,
    ):
        row_html = row_m.group(1)
        # Each day card
        cards = re.findall(
            r'<div class="col-md-2 col-menu[^"]*"[^>]*>(.*?)(?=<div class="col-md-2 col-menu|$)',
            row_html, re.DOTALL,
        )
        for card in cards:
            day_m = re.search(
                r'<div class="card-header"[^>]*>\s*([^\s<][^<]*?)\s*</div>',
                card,
            )
            day = day_m.group(1).strip() if day_m else None
            if not day or day not in days_data:
                continue
            # meal label (h5 with orange color)
            meal_m = re.search(r'<h5[^>]*>\s*([^<]+?)\s*</h5>', card)
            meal = re.sub(r"\s+", " ", meal_m.group(1)).strip() if meal_m else "Repas"
            # list-group-item content
            li_m = re.search(
                r'<li[^>]*class="list-group-item[^"]*"[^>]*>(.*?)</li>',
                card, re.DOTALL,
            )
            items = parse_items(li_m.group(1)) if li_m else []
            if items:
                days_data[day].append({"meal": meal, "items": items})

    rec["days"] = [{"day": d, "meals": days_data[d]} for d in DAYS if days_data[d]]
    rec["meal_ideas_links"] = ideas

    # Cross-refs: collect every recipe id appearing in this menu
    recipe_ids = sorted({
        int(m.group(1))
        for m in re.finditer(r"href=['\"]/recettes/(\d+)['\"]", html)
    })
    rec["recipe_ids"] = recipe_ids

    return rec


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", action="store_true")
    parser.add_argument("--range", type=str, default=None,
                        help="Explicit ID range, e.g. '1-53'. Overrides the listing.")
    args = parser.parse_args()

    DATA_DIR.mkdir(exist_ok=True)
    sess = requests.Session()

    if args.range:
        lo, hi = [int(x) for x in args.range.split("-")]
        menus = [{"id": i, "url": f"/menus/{i}"} for i in range(lo, hi + 1)]
        print(f"Using explicit range {lo}-{hi} ({len(menus)} menus)")
    else:
        if args.cache and Path(LISTING_CACHE).exists():
            listing_html = Path(LISTING_CACHE).read_text()
            print(f"Using cached listing {LISTING_CACHE}")
        else:
            print("Fetching /menus listing...")
            listing_html = fetch("/menus", sess)
        menus = discover_menus(listing_html)
        print(f"Discovered {len(menus)} menus: {[m['id'] for m in menus]}")

    out = []
    for i, m in enumerate(menus, 1):
        print(f"  [{i}/{len(menus)}] /menus/{m['id']}", end=" ", flush=True)
        try:
            html = fetch(m["url"], sess)
            rec = parse_menu(html, m)
            # Skip empty fallback pages (menus beyond the real range)
            if not rec.get("days") and not rec.get("recipe_ids"):
                print("empty page — skipped")
                continue
            out.append(rec)
            print(f"OK ({len(rec.get('days', []))} days, {len(rec.get('recipe_ids', []))} recipes)")
        except Exception as e:
            print(f"FAIL: {e}")
        time.sleep(0.4)

    OUT_FILE.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"\nSaved {len(out)} menus to {OUT_FILE} ({OUT_FILE.stat().st_size//1024} KB)")


if __name__ == "__main__":
    main()
