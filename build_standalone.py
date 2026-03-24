"""
Build a single self-contained HTML file for iPad offline use.
Inlines CSS, JS, and recipe data into one file.
"""
import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(ROOT, 'app')
OUT = os.path.join(APP, 'standalone.html')

# Read components
with open(os.path.join(APP, 'index.html')) as f:
    html = f.read()
with open(os.path.join(APP, 'style.css')) as f:
    css = f.read()
with open(os.path.join(APP, 'app.js')) as f:
    js = f.read()
with open(os.path.join(APP, 'recipes.json')) as f:
    recipes = f.read()

# Patch JS: replace fetch with embedded data
js = js.replace(
    "const resp = await fetch('recipes.json');\n  if (!resp.ok) throw new Error('Failed to load recipes');\n  return resp.json();",
    "return window.__RECIPES_DATA__;"
)

# Remove SW registration (not needed in standalone)
js = js.replace(
    """if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('sw.js').catch((err) => console.warn('SW registration failed:', err));
}""",
    "// SW not needed in standalone mode"
)

# Build standalone HTML
# Remove external CSS link and SW/manifest references
html = html.replace('  <link rel="stylesheet" href="style.css">\n', '')
html = html.replace('  <link rel="manifest" href="manifest.json">\n', '')
html = html.replace('  <script type="module" src="app.js"></script>\n', '')

# Insert inline CSS before </head>
html = html.replace('</head>', f'  <style>\n{css}\n  </style>\n</head>')

# Insert inline JS + data before </body>
html = html.replace('</body>', f"""  <script>
window.__RECIPES_DATA__ = {recipes};
  </script>
  <script type="module">
{js}
  </script>
</body>""")

with open(OUT, 'w') as f:
    f.write(html)

size_kb = os.path.getsize(OUT) / 1024
print(f"Built {OUT}")
print(f"Size: {size_kb:.0f} KB ({size_kb/1024:.1f} MB)")
print(f"Recipes embedded: {len(json.loads(recipes))}")
