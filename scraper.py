"""
Hamstouille recipe scraper.

Scrapes recipes from hamstouille.fr, extracts structured data,
and saves to data/recipes.json with a progress tracker in data/progress.json.

Usage:
    python3 scraper.py                  # Scrape next batch (default 10)
    python3 scraper.py --limit 20       # Scrape next 20
    python3 scraper.py --all            # Scrape all remaining
    python3 scraper.py --status         # Show progress
"""
import requests
import re
import json
import os
import time
import argparse
from html.parser import HTMLParser
from pathlib import Path

BASE_URL = "https://www.hamstouille.fr"
DATA_DIR = Path(__file__).parent / "data"
RECIPES_FILE = DATA_DIR / "recipes.json"
PROGRESS_FILE = DATA_DIR / "progress.json"
LISTING_CACHE = DATA_DIR / "recipe_index.json"

COOKIE = {"PHPSESSID": "13j45hfk2pdesd5gvh730aapar"}

CATEGORIES = {
    "1": "Petits déjeuners et goûters",
    "2": "Entrées",
    "3": "Plats complets",
    "4": "Pâtes, semoule, riz et pdt",
    "5": "Légumes",
    "6": "Bases patisserie boulangerie",
    "7": "Sauces et tartinades salées",
    "8": "Desserts",
    "9": "Occasions spéciales",
    "10": "Sauces et tartinades sucrées",
    "11": "Lait-laitages",
    "12": "Légumineuses",
    "13": "Viandes, poissons, oeufs",
    "14": "Fruits",
    "15": "Tout en 1 pour les sorties",
    "16": "Healthy Snack",
    "17": "One Pot",
    "18": "Faciles et rapides !",
    "19": "Vapeur",
}

FILTERS = {
    "1": "Sans fruits à coques/arachides",
    "2": "Sans gluten",
    "3": "Sans blé",
    "4": "Sans lait animal",
    "7": "Sans oeuf",
    "8": "Sans produits de la mer",
    "9": "Sans sésame",
    "10": "Sans légumineuses",
    "11": "Sans banane",
    "12": "Recette avec protéines",
    "13": "Recette végétarienne",
    "14": "Recette vegan",
    "15": "Recette avec source de calcium",
    "16": "Sans cuisson",
    "17": "Pour les petits mangeurs",
}


class TextExtractor(HTMLParser):
    """Extract clean text from HTML, preserving allergens marked in red."""

    def __init__(self):
        super().__init__()
        self._skip = False
        self._skip_tags = {"script", "style", "noscript"}
        self._in_red = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in self._skip_tags:
            self._skip = True
        attrs_dict = dict(attrs)
        style = attrs_dict.get("style", "")
        if "color:red" in style or "color: red" in style:
            self._in_red = True
        if tag in ("br", "p", "div", "li", "tr"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._skip_tags:
            self._skip = False
        if tag == "span":
            self._in_red = False

    def handle_data(self, data):
        if self._skip:
            return
        text = data.strip()
        if text:
            if self._in_red:
                self.parts.append(f"[ALLERGEN:{text}]")
            else:
                self.parts.append(text)

    def get_text(self):
        raw = " ".join(self.parts)
        # Normalize whitespace but keep newlines
        lines = raw.split("\n")
        lines = [" ".join(l.split()) for l in lines]
        return "\n".join(l for l in lines if l.strip())


def extract_text(html_fragment):
    """Convert HTML fragment to clean text with allergen markers."""
    ext = TextExtractor()
    ext.feed(html_fragment)
    return ext.get_text()


def discover_recipes():
    """Fetch the listing page and extract all recipe metadata."""
    print("Discovering recipes from listing page...")
    resp = requests.get(f"{BASE_URL}/recettes", cookies=COOKIE, timeout=30)
    resp.raise_for_status()
    html = resp.text

    recipes = []

    # Find each recipe card: <div class="col-md-4 mb-3" id="recetteNN" data-filtres="...">
    for m in re.finditer(
        r'id="recette(\d+)"\s+data-filtres="([^"]*)"', html
    ):
        recipe_id = m.group(1)
        filter_ids = [f for f in m.group(2).split(",") if f]

        # Find the category: look backwards for the nearest data-categorie on a row div
        pos = m.start()
        cat_match = None
        for cm in re.finditer(r'data-categorie="(\d+)"', html[:pos]):
            cat_match = cm
        # The last two matches: h3 (category title) and row div — we want the row's
        category_id = cat_match.group(1) if cat_match else None

        # Find the title from the card
        card_html = html[pos:pos + 2000]
        title_match = re.search(r'title="([^"]+)"', card_html)
        title = title_match.group(1) if title_match else f"Recipe {recipe_id}"

        # Find thumbnail
        img_match = re.search(r'src="(/images/recettes/vignettes/[^"]+)"', card_html)
        thumbnail = f"{BASE_URL}{img_match.group(1)}" if img_match else None

        # Check if freezable (snowflake icon can be anywhere in the card)
        freezable = "fa-snowflake" in card_html

        recipes.append({
            "id": int(recipe_id),
            "title": title,
            "url": f"/recettes/{recipe_id}",
            "category_id": category_id,
            "category": CATEGORIES.get(category_id, category_id),
            "filter_ids": filter_ids,
            "filters": [FILTERS.get(f, f) for f in filter_ids],
            "thumbnail": thumbnail,
            "freezable": freezable,
        })

    recipes.sort(key=lambda r: r["id"])
    print(f"Found {len(recipes)} recipes across {len(set(r['category'] for r in recipes))} categories.")
    return recipes


def parse_recipe_page(html, recipe_meta):
    """Parse a recipe detail page into structured data."""
    recipe = {**recipe_meta}

    # Title (from page, more reliable)
    title_m = re.search(r'<h2 class="text-color-green">([^<]+)</h2>', html)
    if title_m:
        recipe["title"] = title_m.group(1).strip()

    # Full-size image
    img_m = re.search(r'<img class="img-fluid"\s+src="(/images/recettes/[^"]+)"', html)
    if img_m:
        recipe["image"] = f"{BASE_URL}{img_m.group(1)}"

    # Description: content between the image div and the <hr class="separator-green">
    desc_m = re.search(
        r'<div class="col-md-8">(.*?)</div>\s*</div>\s*<hr class="separator-green">',
        html, re.DOTALL
    )
    if desc_m:
        desc_text = extract_text(desc_m.group(1))
        # Remove the freezable tag text
        desc_text = desc_text.replace("Congélation possible", "").strip()
        if desc_text:
            recipe["description"] = desc_text

    # Ingredients: inside card-green-border after "Ingrédients" h4
    ing_m = re.search(
        r'<h4 class="text-color-green">Ingrédients</h4>(.*?)</div>\s*</div>',
        html, re.DOTALL
    )
    if ing_m:
        ing_text = extract_text(ing_m.group(1))

        # Extract allergens before cleaning markers
        allergens = set()
        for a in re.findall(r'\[ALLERGEN:([^\]]+)\]', ing_text):
            allergens.add(a.strip())
        recipe["allergens"] = sorted(allergens)

        # Clean allergen markers
        clean_text = re.sub(r'\[ALLERGEN:([^\]]+)\]', r'\1', ing_text)

        # Split into lines and merge continuations
        # An ingredient line starts with "- " or a dash, or a quantity pattern
        raw_lines = [l.strip() for l in clean_text.split("\n") if l.strip()]
        ingredients = []
        for line in raw_lines:
            if line in ("Ingrédients",):
                continue
            # Detect if this is a new ingredient (starts with dash or quantity)
            is_new = bool(re.match(r'^[-–—•]|^\d', line))
            line = re.sub(r'^[-–—•]\s*', '', line).strip()
            if not line:
                continue
            if is_new or not ingredients:
                ingredients.append(line)
            else:
                # Continuation of previous ingredient
                ingredients[-1] += " " + line
        recipe["ingredients"] = ingredients

    # Preparation: after "Préparation" h4
    prep_m = re.search(
        r'<h4 class="text-color-green">Préparation</h4>(.*?)</div>\s*</div>',
        html, re.DOTALL
    )
    if prep_m:
        prep_text = extract_text(prep_m.group(1))
        clean_text = re.sub(r'\[ALLERGEN:([^\]]+)\]', r'\1', prep_text)

        # Merge lines into steps: a new step starts with "N)" pattern
        raw_lines = [l.strip() for l in clean_text.split("\n") if l.strip()]
        steps = []
        for line in raw_lines:
            if line in ("Préparation",):
                continue
            # Check if line starts a new numbered step
            new_step = re.match(r'^(\d+)\)\s*(.*)', line)
            if new_step:
                steps.append(new_step.group(2))
            elif steps:
                # Continuation of previous step
                steps[-1] += " " + line
            else:
                # No numbered steps yet — treat as a step anyway
                steps.append(line)
        # Clean up extra whitespace
        recipe["steps"] = [" ".join(s.split()) for s in steps if s.strip()]

    # Freezable from detail page (more reliable than listing)
    if "Congélation possible" in html:
        recipe["freezable"] = True

    # Conservation/storage tips: look in the preparation section text
    if prep_m:
        all_text = re.sub(r'\[ALLERGEN:([^\]]+)\]', r'\1', extract_text(prep_m.group(1)))
        for sentence in re.split(r'(?<=[.!])\s+', all_text):
            if re.search(r'conserv|congél|réfrigér|boîte hermétique', sentence, re.IGNORECASE):
                tip = sentence.strip().rstrip(",.")
                if len(tip) > 15:
                    recipe["storage_tip"] = tip
                    break

    return recipe


def load_progress():
    """Load scraping progress."""
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text())
    return {"scraped_ids": [], "failed_ids": [], "last_run": None}


def save_progress(progress):
    """Save scraping progress."""
    progress["last_run"] = time.strftime("%Y-%m-%d %H:%M:%S")
    PROGRESS_FILE.write_text(json.dumps(progress, indent=2, ensure_ascii=False))


def load_recipes():
    """Load already-scraped recipes."""
    if RECIPES_FILE.exists():
        return json.loads(RECIPES_FILE.read_text())
    return []


def save_recipes(recipes):
    """Save recipes to JSON."""
    RECIPES_FILE.write_text(json.dumps(recipes, indent=2, ensure_ascii=False))


def scrape_batch(limit=10, scrape_all=False):
    """Scrape the next batch of recipes."""
    DATA_DIR.mkdir(exist_ok=True)

    # Get or refresh the recipe index
    if LISTING_CACHE.exists():
        index = json.loads(LISTING_CACHE.read_text())
    else:
        index = discover_recipes()
        LISTING_CACHE.write_text(json.dumps(index, indent=2, ensure_ascii=False))

    progress = load_progress()
    recipes = load_recipes()
    scraped_set = set(progress["scraped_ids"])
    failed_set = set(progress["failed_ids"])

    # Find recipes not yet scraped
    remaining = [r for r in index if r["id"] not in scraped_set and r["id"] not in failed_set]
    if not remaining:
        print("All recipes have been scraped!")
        return

    to_scrape = remaining if scrape_all else remaining[:limit]
    print(f"Scraping {len(to_scrape)} recipes ({len(scraped_set)} already done, {len(remaining)} remaining)...\n")

    for i, meta in enumerate(to_scrape, 1):
        rid = meta["id"]
        print(f"  [{i}/{len(to_scrape)}] {meta['title']} (id={rid})...", end=" ", flush=True)

        try:
            resp = requests.get(
                f"{BASE_URL}/recettes/{rid}",
                cookies=COOKIE,
                timeout=15,
            )
            resp.raise_for_status()

            if "/connexion" in resp.url:
                print("SESSION EXPIRED - update PHPSESSID cookie")
                break

            recipe = parse_recipe_page(resp.text, meta)
            recipes.append(recipe)
            progress["scraped_ids"].append(rid)
            print("OK")

            # Be polite - small delay between requests
            time.sleep(0.5)

        except Exception as e:
            print(f"FAILED: {e}")
            progress["failed_ids"].append(rid)

    # Save after each batch
    save_recipes(recipes)
    save_progress(progress)
    print(f"\nDone. {len(recipes)} recipes saved to {RECIPES_FILE}")
    print(f"Progress saved to {PROGRESS_FILE}")


def show_status():
    """Show scraping progress."""
    progress = load_progress()
    recipes = load_recipes()

    if LISTING_CACHE.exists():
        index = json.loads(LISTING_CACHE.read_text())
        total = len(index)
    else:
        total = "unknown (run scraper first)"

    print(f"Total recipes indexed: {total}")
    print(f"Scraped: {len(progress['scraped_ids'])}")
    print(f"Failed:  {len(progress['failed_ids'])}")
    if isinstance(total, int):
        remaining = total - len(progress['scraped_ids']) - len(progress['failed_ids'])
        print(f"Remaining: {remaining}")
    print(f"Last run: {progress.get('last_run', 'never')}")

    if recipes:
        print(f"\nRecipes file: {RECIPES_FILE} ({len(recipes)} recipes)")
        cats = {}
        for r in recipes:
            cats.setdefault(r.get("category", "?"), []).append(r["title"])
        for cat, titles in sorted(cats.items()):
            print(f"  {cat}: {len(titles)} recipes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Hamstouille recipe scraper")
    parser.add_argument("--limit", type=int, default=10, help="Number of recipes to scrape (default: 10)")
    parser.add_argument("--all", action="store_true", help="Scrape all remaining recipes")
    parser.add_argument("--status", action="store_true", help="Show scraping progress")
    args = parser.parse_args()

    if args.status:
        show_status()
    else:
        scrape_batch(limit=args.limit, scrape_all=args.all)
