"""
Build a single self-contained HTML file for iPad offline use.
Inlines CSS, JS, and all data sources (recipes, blog, menus, méthode,
tire-allaitement) into one file.
"""
import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(ROOT, 'app')
DATA = os.path.join(ROOT, 'data')
OUT = os.path.join(APP, 'standalone.html')

DATA_FILES = {
    'RECIPES': 'recipes.json',
    'BLOG': 'blog.json',
    'MENUS': 'menus.json',
    'METHOD': 'diversification.json',
    'TIRE': 'tire_allaitement.json',
}

# Read components
with open(os.path.join(APP, 'index.html')) as f:
    html = f.read()
with open(os.path.join(APP, 'style.css')) as f:
    css = f.read()
with open(os.path.join(APP, 'app.js')) as f:
    js = f.read()

# Read all data files (prefer the freshly scraped ones in data/, fall back to app/)
data_blobs = {}
for var, fname in DATA_FILES.items():
    candidates = [os.path.join(DATA, fname), os.path.join(APP, fname)]
    path = next((p for p in candidates if os.path.exists(p)), None)
    if not path:
        raise SystemExit(f"Missing data file: {fname}")
    with open(path) as f:
        data_blobs[var] = f.read()

# Patch JS: replace the loadAll() body with embedded constants
# Find the loadAll function and substitute the fetch block
js_patched = js.replace(
    """async function loadAll() {
  const [recipes, blog, menus, method, tire] = await Promise.all([
    loadJson('recipes.json'),
    loadJson('blog.json'),
    loadJson('menus.json'),
    loadJson('diversification.json'),
    loadJson('tire_allaitement.json'),
  ]);
  return { recipes, blog, menus, method, tire };
}""",
    """async function loadAll() {
  return {
    recipes: window.__RECIPES__,
    blog: window.__BLOG__,
    menus: window.__MENUS__,
    method: window.__METHOD__,
    tire: window.__TIRE__,
  };
}"""
)

# Remove SW registration (file:// won't allow SW)
js_patched = js_patched.replace(
    """if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('sw.js').catch((err) => console.warn('SW registration failed:', err));
}""",
    "// SW not used in standalone mode"
)

# Strip external chrome we don't need
html = html.replace('  <link rel="stylesheet" href="style.css">\n', '')
html = html.replace('  <link rel="manifest" href="manifest.json">\n', '')
html = html.replace('  <script type="module" src="app.js"></script>\n', '')

# Inline CSS before </head>
html = html.replace('</head>', f'  <style>\n{css}\n  </style>\n</head>')

# Inline data + JS before </body>
data_block = "\n".join(
    f"window.__{var}__ = {blob};" for var, blob in data_blobs.items()
)
html = html.replace('</body>', f"""  <script>
{data_block}
  </script>
  <script type="module">
{js_patched}
  </script>
</body>""")

with open(OUT, 'w') as f:
    f.write(html)

size_kb = os.path.getsize(OUT) / 1024
print(f"Built {OUT}")
print(f"Size: {size_kb:.0f} KB ({size_kb/1024:.1f} MB)")
print(f"Embedded:")
for var, blob in data_blobs.items():
    items = json.loads(blob)
    n = len(items) if isinstance(items, list) else 1
    print(f"  {var}: {n} item(s), {len(blob)//1024} KB")
