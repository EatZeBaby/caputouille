"""
Merge scraped bambin data into the app, de-duplicating by title and never
deleting existing (bébé) content.

- recipes / blog : bambin items whose normalised title already exists are
  skipped as duplicates; the rest are added with their id offset by +100000.
- internal /recettes/N and /blog/N links inside bambin HTML are rewritten to
  the final ids (offset for added items, the existing bébé id for de-duped
  ones) so cross-references keep resolving in the app.
- batch-cooking, dans-assiette, quand-ca-ne-marche-pas are brand-new sections
  written to their own JSON files.

Reads app/*.json (currently served) + data/bambin_*.json.
Writes app/recipes.json, app/blog.json, app/batch_cooking.json,
app/dans_assiette.json, app/quand_ca_ne_marche_pas.json.
"""
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).parent
APP = ROOT / "app"
DATA = ROOT / "data"
OFFSET = 100000


def load(p):
    return json.loads(Path(p).read_text())


def save(p, data):
    Path(p).write_text(json.dumps(data, indent=2, ensure_ascii=False))


def norm(title):
    s = unicodedata.normalize("NFD", (title or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s)).strip()


def make_rewriter(recipe_map, blog_map):
    """Return f(html) rewriting bambin /recettes/N and /blog/N to final ids."""
    def repl_recipe(m):
        return f'/recettes/{recipe_map.get(int(m.group(1)), int(m.group(1)) + OFFSET)}'

    def repl_blog(m):
        return f'/blog/{blog_map.get(int(m.group(1)), int(m.group(1)) + OFFSET)}'

    def rewrite(html):
        if not html:
            return html
        html = re.sub(r'(?:https?://bambin\.hamstouille\.fr)?/recettes/(\d+)', repl_recipe, html)
        html = re.sub(r'(?:https?://bambin\.hamstouille\.fr)?/blog/(\d+)', repl_blog, html)
        return html
    return rewrite


def main():
    # Read the pristine bébé base from data/ (never mutated by this script) so
    # the merge is idempotent regardless of the current app/ contents.
    existing_recipes = load(DATA / "recipes.json")
    existing_blog = load(DATA / "blog.json")
    bam_recipes = load(DATA / "bambin_recipes.json")
    bam_blog = load(DATA / "bambin_blog.json")
    bam_batch = load(DATA / "bambin_batch.json")
    bam_assiette = load(DATA / "bambin_assiette.json")
    bam_qcnmp = load(DATA / "bambin_qcnmp.json")

    # ── Build title → existing-id maps for de-dup ──
    recipe_title_to_id = {norm(r["title"]): r["id"] for r in existing_recipes}
    blog_title_to_id = {norm(a["title"]): a["id"] for a in existing_blog}

    # ── Recipes: map every bambin id to its final app id ──
    recipe_map, added_recipes, skipped_recipes = {}, [], 0
    for r in bam_recipes:
        key = norm(r["title"])
        if key in recipe_title_to_id:
            recipe_map[r["id"]] = recipe_title_to_id[key]  # de-dup → existing bébé recipe
            skipped_recipes += 1
        else:
            new_id = r["id"] + OFFSET
            recipe_map[r["id"]] = new_id
            nr = dict(r)
            nr["id"] = new_id
            nr["source"] = "bambin"
            added_recipes.append(nr)

    # ── Blog: map every bambin id to its final app id ──
    blog_map, added_blog, skipped_blog = {}, [], 0
    for a in bam_blog:
        key = norm(a["title"])
        if key in blog_title_to_id:
            blog_map[a["id"]] = blog_title_to_id[key]
            skipped_blog += 1
        else:
            new_id = a["id"] + OFFSET
            blog_map[a["id"]] = new_id
            added_blog.append({**a, "id": new_id, "source": "bambin"})

    rewrite = make_rewriter(recipe_map, blog_map)

    # ── Rewrite links in added bambin blog HTML + cross-refs ──
    def fix_refs(refs):
        out = []
        for ref in refs or []:
            m = recipe_map if ref["type"] == "recipe" else blog_map
            fid = m.get(ref["id"], ref["id"] + OFFSET)
            out.append({**ref, "id": fid, "url": f'/{"recettes" if ref["type"]=="recipe" else "blog"}/{fid}'})
        return out

    for a in added_blog:
        a["intro_html"] = rewrite(a.get("intro_html", ""))
        a["content_html"] = rewrite(a.get("content_html", ""))
        a["cross_references"] = fix_refs(a.get("cross_references"))

    # ── Batch cooking (new section) — rewrite recipe links in content ──
    for b in bam_batch:
        b["content_html"] = rewrite(b.get("content_html", ""))
        b["cross_references"] = fix_refs(b.get("cross_references"))

    # ── Doc sections — rewrite links inside each section ──
    for doc in (bam_assiette, bam_qcnmp):
        for s in doc.get("sections", []):
            s["content_html"] = rewrite(s.get("content_html", ""))
            s["cross_references"] = fix_refs(s.get("cross_references"))
        doc["cross_references"] = fix_refs(doc.get("cross_references"))

    # ── Write merged / new files ──
    merged_recipes = existing_recipes + added_recipes
    merged_blog = existing_blog + added_blog
    save(APP / "recipes.json", merged_recipes)
    save(APP / "blog.json", merged_blog)
    save(APP / "batch_cooking.json", bam_batch)
    save(APP / "dans_assiette.json", bam_assiette)
    save(APP / "quand_ca_ne_marche_pas.json", bam_qcnmp)

    print("── Merge summary ─────────────────────────────")
    print(f"Recipes : {len(existing_recipes)} existing + {len(added_recipes)} added "
          f"({skipped_recipes} bambin dupes skipped) = {len(merged_recipes)}")
    print(f"Blog    : {len(existing_blog)} existing + {len(added_blog)} added "
          f"({skipped_blog} bambin dupes skipped) = {len(merged_blog)}")
    print(f"Batch   : {len(bam_batch)} sessions -> app/batch_cooking.json")
    print(f"Assiette: {len(bam_assiette['sections'])} sections -> app/dans_assiette.json")
    print(f"QCNMP   : {len(bam_qcnmp['sections'])} sections -> app/quand_ca_ne_marche_pas.json")


if __name__ == "__main__":
    main()
