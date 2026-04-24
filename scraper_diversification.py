"""
Scrape Hamstouille "Ma méthode de diversification"
(https://www.hamstouille.fr/ma-methode-de-diversification).

Single page with a Bootstrap accordion holding 6 cards (étapes).

Outputs:
    data/diversification.json
"""
import argparse
import json
import re
from pathlib import Path

import requests

from scrape_helpers import (
    BASE_URL, COOKIE,
    sanitize, to_text, find_cross_refs, absolutize,
)

DATA_DIR = Path(__file__).parent / "data"
OUT_FILE = DATA_DIR / "diversification.json"
URL_PATH = "/ma-methode-de-diversification"
CACHE = "/tmp/ht_method.html"


def fetch(path):
    r = requests.get(BASE_URL + path, cookies=COOKIE, timeout=20, allow_redirects=False)
    if r.status_code in (301, 302):
        raise RuntimeError(f"redirect from {path} — session expired?")
    r.raise_for_status()
    return r.text


def slugify(text):
    s = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip().lower()
    return re.sub(r"[\s-]+", "-", s)[:64]


def parse(html):
    rec = {"url": URL_PATH}

    # Title
    title_m = re.search(
        r'<h1[^>]*class="[^"]*blog-title[^"]*"[^>]*>(.*?)</h1>',
        html, re.DOTALL,
    )
    if title_m:
        rec["title"] = re.sub(r"\s+", " ", title_m.group(1)).strip()

    # Locate the accordion container
    acc_m = re.search(
        r'<div[^>]*class="[^"]*accordion[^"]*"[^>]*id="accordionExample"[^>]*>(.*?)(?=<footer|<div class="footer|$)',
        html, re.DOTALL,
    )
    accordion_html = acc_m.group(1) if acc_m else ""

    # Optional intro: anything between the h1 and the accordion's first card
    intro_html = ""
    if title_m and acc_m:
        between = html[title_m.end():acc_m.start()]
        # strip surrounding navigation rows (col-sm-12 mb-5 with nothing, etc.)
        intro_m = re.search(r'<div[^>]*class="[^"]*col-sm-12[^"]*"[^>]*>(.*)$',
                            between, re.DOTALL)
        intro_html = intro_m.group(1) if intro_m else ""
    rec["intro_html"] = sanitize(intro_html) if intro_html else ""
    rec["intro_text"] = to_text(intro_html)

    # Split the accordion on each card boundary and process segments.
    sections = []
    chunks = re.split(r'<div class="card mb-3">', accordion_html)[1:]
    for card_html in chunks:
        head_m = re.search(
            r'<button[^>]*class="[^"]*btn-accordeon-mde[^"]*"[^>]*>\s*(.*?)\s*</button>',
            card_html, re.DOTALL,
        )
        heading = re.sub(r"\s+", " ", head_m.group(1)).strip() if head_m else ""

        # Body is the content-blog div; capture greedily and then trim
        # to whatever ends the card-body (the next collapse-end or accordion-end).
        body_m = re.search(
            r'<div class="content-blog">(.*?)(?=</div>\s*</div>\s*</div>|<div class="card-header|<div class="col-sm-12 mb-5 accordion)',
            card_html, re.DOTALL,
        )
        body_html = body_m.group(1) if body_m else ""

        # Collect images and videos referenced inside
        images = sorted({
            absolutize(m.group(1))
            for m in re.finditer(r'<img[^>]+src="([^"]+)"', body_html)
        })
        videos = sorted({
            absolutize(m.group(1))
            for m in re.finditer(r'<source[^>]+src="([^"]+)"', body_html)
        })
        pdfs = sorted({
            absolutize(m.group(1))
            for m in re.finditer(r'href="([^"]+\.pdf)"', body_html, re.IGNORECASE)
        })

        sections.append({
            "level": 2,
            "heading": heading,
            "anchor": slugify(heading),
            "content_html": sanitize(body_html),
            "content_text": to_text(body_html),
            "images": images,
            "videos": videos,
            "pdfs": pdfs,
            "cross_references": find_cross_refs(body_html),
        })

    rec["sections"] = sections
    rec["raw_text"] = "\n\n".join(s["content_text"] for s in sections if s["content_text"])

    # All cross-refs aggregated
    all_refs = []
    seen = set()
    for s in sections:
        for ref in s["cross_references"]:
            key = (ref["type"], ref["id"])
            if key in seen:
                continue
            seen.add(key)
            all_refs.append(ref)
    rec["cross_references"] = all_refs

    return rec


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", action="store_true")
    args = parser.parse_args()

    DATA_DIR.mkdir(exist_ok=True)

    if args.cache and Path(CACHE).exists():
        html = Path(CACHE).read_text()
        print(f"Using cached {CACHE}")
    else:
        print(f"Fetching {URL_PATH}...")
        html = fetch(URL_PATH)

    rec = parse(html)
    OUT_FILE.write_text(json.dumps(rec, indent=2, ensure_ascii=False))
    print(f"Title: {rec.get('title')}")
    print(f"Sections: {len(rec.get('sections', []))}")
    for s in rec.get("sections", []):
        print(f"  - {s['heading']}  ({len(s['images'])} img, {len(s['videos'])} vid, {len(s['pdfs'])} pdf)")
    print(f"Saved to {OUT_FILE} ({OUT_FILE.stat().st_size//1024} KB)")


if __name__ == "__main__":
    main()
