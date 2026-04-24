"""
Scrape Hamstouille "Module tire-allaitement"
(https://www.hamstouille.fr/module-tire-allaitement).

Single page with 15 sequential accordion blocks (#accordion1..#accordion15),
each carrying a heading, body text, an MP4 video and optional PDF attachments.

Outputs:
    data/tire_allaitement.json
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
OUT_FILE = DATA_DIR / "tire_allaitement.json"
URL_PATH = "/module-tire-allaitement"
CACHE = "/tmp/ht_tire.html"


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

    title_m = re.search(
        r'<h1[^>]*class="[^"]*blog-title[^"]*"[^>]*>(.*?)</h1>',
        html, re.DOTALL,
    )
    if title_m:
        rec["title"] = re.sub(r"\s+", " ", title_m.group(1)).strip()

    sections = []
    # Each accordion block looks like:
    #   <div class="col-sm-12 mb-5 accordion" id="accordionN">
    #       <div class="card mb-3">
    #           <div class="card-header bg-green" id="headingN">
    #               ...<button class="...btn-accordeon-mde">HEADING</button>...
    #           </div>
    #           <div id="..." class="collapse" data-parent="#accordionN">
    #               <div class="card-body ..."><div class="content-blog">BODY</div>
    #               <video ...><source src="/videos/.../N_xx_sd.mp4" type="video/mp4"></video>
    #               (optional PDF row)
    #           </div>
    #       </div>
    #   </div>
    for acc_m in re.finditer(
        r'<div[^>]*class="[^"]*accordion[^"]*"[^>]*id="accordion(\d+)"[^>]*>(.*?)(?=<div[^>]*class="[^"]*accordion[^"]*"[^>]*id="accordion\d+"|<footer)',
        html, re.DOTALL,
    ):
        idx = int(acc_m.group(1))
        block = acc_m.group(2)

        head_m = re.search(
            r'<button[^>]*class="[^"]*btn-accordeon-mde[^"]*"[^>]*>\s*(.*?)\s*</button>',
            block, re.DOTALL,
        )
        heading = re.sub(r"\s+", " ", head_m.group(1)).strip() if head_m else f"Section {idx}"

        body_m = re.search(
            r'<div class="content-blog">(.*?)</div>\s*(?=<video|<div class="row|</div>\s*</div>\s*</div>)',
            block, re.DOTALL,
        )
        body_html = body_m.group(1) if body_m else ""

        videos = sorted({
            absolutize(m.group(1))
            for m in re.finditer(r'<source[^>]+src="([^"]+)"', block)
        })
        # iframes (in case any youtube embeds)
        iframes = sorted({
            absolutize(m.group(1))
            for m in re.finditer(r'<iframe[^>]+src="([^"]+)"', block)
        })
        videos = sorted(set(videos + iframes))

        images = sorted({
            absolutize(m.group(1))
            for m in re.finditer(r'<img[^>]+src="([^"]+)"', block)
        })
        pdfs = sorted({
            absolutize(m.group(1))
            for m in re.finditer(r'href="([^"]+\.pdf)"', block, re.IGNORECASE)
        })

        sections.append({
            "index": idx,
            "level": 2,
            "heading": heading,
            "anchor": slugify(heading),
            "content_html": sanitize(body_html),
            "content_text": to_text(body_html),
            "videos": videos,
            "images": images,
            "pdfs": pdfs,
            "cross_references": find_cross_refs(block),
        })

    sections.sort(key=lambda s: s["index"])
    rec["sections"] = sections
    rec["raw_text"] = "\n\n".join(s["content_text"] for s in sections if s["content_text"])

    # Aggregate cross-refs
    all_refs, seen = [], set()
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
        print(f"  {s['index']:>2}. {s['heading']:50s} "
              f"({len(s['videos'])} vid, {len(s['images'])} img, {len(s['pdfs'])} pdf)")
    print(f"Saved to {OUT_FILE} ({OUT_FILE.stat().st_size//1024} KB)")


if __name__ == "__main__":
    main()
