/* ============================================
   Datatouille — App Logic
   ============================================ */

const BASE_IMG = 'https://www.hamstouille.fr';
let allRecipes = [];
let filteredRecipes = [];
let activeCategory = 'all';
let activeDietaryFilters = new Set();
let searchQuery = '';

// ── Data Loading ──────────────────────────────

async function loadRecipes() {
  const resp = await fetch('recipes.json');
  if (!resp.ok) throw new Error('Failed to load recipes');
  return resp.json();
}

// ── Rendering ─────────────────────────────────

function getCategories(recipes) {
  const cats = new Map();
  for (const r of recipes) {
    if (r.category && !cats.has(r.category)) {
      cats.set(r.category, r.category_id);
    }
  }
  return [...cats.entries()].sort((a, b) => a[0].localeCompare(b[0], 'fr'));
}

function getDietaryFilters(recipes) {
  const filters = new Map();
  for (const r of recipes) {
    if (!r.filters) continue;
    for (let i = 0; i < r.filter_ids.length; i++) {
      const id = r.filter_ids[i];
      const name = r.filters[i];
      if (name && !filters.has(id)) {
        filters.set(id, name);
      }
    }
  }
  return [...filters.entries()].sort((a, b) => a[1].localeCompare(b[1], 'fr'));
}

function renderCategoryChips(categories) {
  const container = document.getElementById('categoryChips');
  const allChip = container.querySelector('[data-category="all"]');

  for (const [name] of categories) {
    const btn = document.createElement('button');
    btn.className = 'chip';
    btn.dataset.category = name;
    btn.textContent = name;
    btn.setAttribute('role', 'option');
    btn.setAttribute('aria-selected', 'false');
    container.appendChild(btn);
  }

  container.addEventListener('click', (e) => {
    const chip = e.target.closest('.chip');
    if (!chip) return;
    activeCategory = chip.dataset.category;
    container.querySelectorAll('.chip').forEach(c => {
      c.classList.toggle('active', c.dataset.category === activeCategory);
      c.setAttribute('aria-selected', c.dataset.category === activeCategory);
    });
    applyFilters();
  });
}

function renderDietaryFilters(filters) {
  const grid = document.getElementById('dietaryGrid');

  for (const [id, name] of filters) {
    const btn = document.createElement('button');
    btn.className = 'dietary-chip';
    btn.dataset.filterId = id;
    btn.textContent = name;
    btn.type = 'button';
    grid.appendChild(btn);
  }

  grid.addEventListener('click', (e) => {
    const chip = e.target.closest('.dietary-chip');
    if (!chip) return;
    const id = chip.dataset.filterId;
    if (activeDietaryFilters.has(id)) {
      activeDietaryFilters.delete(id);
      chip.classList.remove('active');
    } else {
      activeDietaryFilters.add(id);
      chip.classList.add('active');
    }
    updateDietaryCount();
    applyFilters();
  });
}

function updateDietaryCount() {
  const badge = document.getElementById('dietaryCount');
  const count = activeDietaryFilters.size;
  badge.textContent = count;
  badge.hidden = count === 0;
}

function imageUrl(recipe) {
  if (recipe.image) {
    return recipe.image.startsWith('http')
      ? recipe.image
      : BASE_IMG + recipe.image;
  }
  if (recipe.thumbnail) {
    return recipe.thumbnail.startsWith('http')
      ? recipe.thumbnail
      : BASE_IMG + recipe.thumbnail;
  }
  return null;
}

function createRecipeCard(recipe, index) {
  const imgUrl = imageUrl(recipe);
  const isVegan = recipe.filters?.includes('Recette vegan');
  const isVegetarian = !isVegan && recipe.filters?.includes('Recette végétarienne');

  const card = document.createElement('article');
  card.className = 'recipe-card';
  card.style.animationDelay = `${Math.min(index * 30, 300)}ms`;
  card.setAttribute('tabindex', '0');
  card.setAttribute('role', 'link');
  card.setAttribute('aria-label', recipe.title);

  const badges = [];
  if (recipe.freezable) badges.push('<span class="badge badge-freeze">Congélation</span>');
  if (isVegan) badges.push('<span class="badge badge-vegan">Vegan</span>');
  else if (isVegetarian) badges.push('<span class="badge badge-vegetarian">Végétarien</span>');

  const allergenTags = (recipe.allergens || [])
    .slice(0, 3)
    .map(a => `<span class="card-tag card-tag-allergen">${escapeHtml(a)}</span>`)
    .join('');

  card.innerHTML = `
    <div class="card-image-wrapper">
      ${imgUrl
        ? `<img class="card-image" src="${escapeHtml(imgUrl)}" alt="${escapeHtml(recipe.title)}" loading="lazy" onerror="this.parentElement.innerHTML='<div class=card-image-placeholder><svg width=40 height=40 viewBox=&quot;0 0 24 24&quot; fill=none stroke=currentColor stroke-width=1.5><path d=&quot;M6 13.87A4 4 0 0 1 7.41 6a5.11 5.11 0 0 1 1.05-1.54 5 5 0 0 1 7.08 0A5.11 5.11 0 0 1 16.59 6 4 4 0 0 1 18 13.87V21H6Z&quot;/><line x1=6 y1=17 x2=18 y2=17/></svg></div>'">`
        : `<div class="card-image-placeholder">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M6 13.87A4 4 0 0 1 7.41 6a5.11 5.11 0 0 1 1.05-1.54 5 5 0 0 1 7.08 0A5.11 5.11 0 0 1 16.59 6 4 4 0 0 1 18 13.87V21H6Z"/><line x1="6" y1="17" x2="18" y2="17"/></svg>
           </div>`
      }
      ${badges.length ? `<div class="card-badges">${badges.join('')}</div>` : ''}
    </div>
    <div class="card-body">
      <div class="card-category">${escapeHtml(recipe.category || '')}</div>
      <h2 class="card-title">${escapeHtml(recipe.title)}</h2>
      ${allergenTags ? `<div class="card-tags">${allergenTags}</div>` : ''}
    </div>
  `;

  card.addEventListener('click', () => openRecipe(recipe));
  card.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      openRecipe(recipe);
    }
  });

  return card;
}

function renderGrid(recipes) {
  const grid = document.getElementById('recipeGrid');
  const noResults = document.getElementById('noResults');

  grid.innerHTML = '';

  if (recipes.length === 0) {
    noResults.hidden = false;
    grid.style.display = 'none';
  } else {
    noResults.hidden = true;
    grid.style.display = '';
    const fragment = document.createDocumentFragment();
    recipes.forEach((r, i) => fragment.appendChild(createRecipeCard(r, i)));
    grid.appendChild(fragment);
  }

  document.getElementById('resultsCount').textContent =
    `${recipes.length} recette${recipes.length !== 1 ? 's' : ''}`;
}

// ── Recipe Detail ─────────────────────────────

function openRecipe(recipe) {
  const overlay = document.getElementById('overlay');
  const content = document.getElementById('detailContent');

  const imgUrl = imageUrl(recipe);

  const ingredientsList = (recipe.ingredients || [])
    .map(i => `
      <li class="ingredient-item">
        <span class="ingredient-bullet"></span>
        <span>${escapeHtml(i)}</span>
      </li>
    `).join('');

  const stepsList = (recipe.steps || [])
    .map((s, idx) => `
      <li class="step-item">
        <span class="step-number">${idx + 1}</span>
        <span class="step-text">${escapeHtml(s)}</span>
      </li>
    `).join('');

  const allergenTags = (recipe.allergens || [])
    .map(a => `<span class="allergen-tag">${escapeHtml(a)}</span>`)
    .join('');

  const filterTags = (recipe.filters || [])
    .map(f => `<span class="detail-filter-tag">${escapeHtml(f)}</span>`)
    .join('');

  const metaBadges = [];
  if (recipe.freezable) {
    metaBadges.push('<span class="detail-badge badge-freeze">Congélation possible</span>');
  }
  if (recipe.filters?.includes('Recette vegan')) {
    metaBadges.push('<span class="detail-badge badge-vegan">Vegan</span>');
  } else if (recipe.filters?.includes('Recette végétarienne')) {
    metaBadges.push('<span class="detail-badge badge-vegetarian">Végétarien</span>');
  }

  content.innerHTML = `
    <div class="detail-hero">
      ${imgUrl
        ? `<img src="${escapeHtml(imgUrl)}" alt="${escapeHtml(recipe.title)}" onerror="this.parentElement.innerHTML='<div class=detail-hero-placeholder><svg width=64 height=64 viewBox=&quot;0 0 24 24&quot; fill=none stroke=currentColor stroke-width=1.5><path d=&quot;M6 13.87A4 4 0 0 1 7.41 6a5.11 5.11 0 0 1 1.05-1.54 5 5 0 0 1 7.08 0A5.11 5.11 0 0 1 16.59 6 4 4 0 0 1 18 13.87V21H6Z&quot;/><line x1=6 y1=17 x2=18 y2=17/></svg></div>'">`
        : `<div class="detail-hero-placeholder">
            <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M6 13.87A4 4 0 0 1 7.41 6a5.11 5.11 0 0 1 1.05-1.54 5 5 0 0 1 7.08 0A5.11 5.11 0 0 1 16.59 6 4 4 0 0 1 18 13.87V21H6Z"/><line x1="6" y1="17" x2="18" y2="17"/></svg>
           </div>`
      }
    </div>
    <div class="detail-body">
      <div class="detail-category">${escapeHtml(recipe.category || '')}</div>
      <h1 class="detail-title">${escapeHtml(recipe.title)}</h1>

      ${metaBadges.length ? `<div class="detail-meta">${metaBadges.join('')}</div>` : ''}

      ${recipe.description ? `<p class="detail-description">${escapeHtml(recipe.description)}</p>` : ''}

      ${ingredientsList ? `
        <section class="detail-section">
          <h2 class="detail-section-title">Ingrédients</h2>
          <ul class="ingredient-list">${ingredientsList}</ul>
        </section>
      ` : ''}

      ${stepsList ? `
        <section class="detail-section">
          <h2 class="detail-section-title">Préparation</h2>
          <ol class="step-list">${stepsList}</ol>
        </section>
      ` : ''}

      ${allergenTags ? `
        <section class="detail-section">
          <h2 class="detail-section-title">Allergènes</h2>
          <div class="allergen-list">${allergenTags}</div>
        </section>
      ` : ''}

      ${recipe.storage_tip ? `
        <div class="storage-tip">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
          <span>${escapeHtml(recipe.storage_tip)}</span>
        </div>
      ` : ''}

      ${filterTags ? `
        <div class="detail-filters">${filterTags}</div>
      ` : ''}
    </div>
  `;

  overlay.hidden = false;
  document.body.style.overflow = 'hidden';
  history.pushState(null, '', `#recipe/${recipe.id}`);

  // Focus trap
  document.getElementById('detailClose').focus();
}

function closeRecipe() {
  const overlay = document.getElementById('overlay');
  overlay.hidden = true;
  document.body.style.overflow = '';
  if (location.hash.startsWith('#recipe/')) {
    history.pushState(null, '', location.pathname + location.search);
  }
}

// ── Filtering & Search ────────────────────────

function normalize(str) {
  return str
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '');
}

function applyFilters() {
  const q = normalize(searchQuery);

  filteredRecipes = allRecipes.filter(r => {
    // Category filter
    if (activeCategory !== 'all' && r.category !== activeCategory) return false;

    // Dietary filters (AND logic: recipe must match ALL selected filters)
    if (activeDietaryFilters.size > 0) {
      for (const fid of activeDietaryFilters) {
        if (!r.filter_ids || !r.filter_ids.includes(fid)) return false;
      }
    }

    // Search
    if (q) {
      const searchable = normalize(
        [r.title, r.category, ...(r.ingredients || []), r.description || ''].join(' ')
      );
      // Support multi-word search: all terms must match
      const terms = q.split(/\s+/).filter(Boolean);
      for (const term of terms) {
        if (!searchable.includes(term)) return false;
      }
    }

    return true;
  });

  renderGrid(filteredRecipes);
}

// ── Search ────────────────────────────────────

function setupSearch() {
  const input = document.getElementById('searchInput');
  const clearBtn = document.getElementById('searchClear');
  let debounceTimer;

  input.addEventListener('input', () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      searchQuery = input.value.trim();
      clearBtn.hidden = !searchQuery;
      applyFilters();
    }, 150);
  });

  clearBtn.addEventListener('click', () => {
    input.value = '';
    searchQuery = '';
    clearBtn.hidden = true;
    applyFilters();
    input.focus();
  });
}

// ── Theme Toggle ──────────────────────────────

function setupTheme() {
  const toggle = document.getElementById('themeToggle');
  const stored = localStorage.getItem('theme');
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;

  if (stored === 'dark' || (!stored && prefersDark)) {
    document.documentElement.setAttribute('data-theme', 'dark');
  }

  toggle.addEventListener('click', () => {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    const next = isDark ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
  });
}

// ── Hash Routing ──────────────────────────────

function handleHash() {
  const hash = location.hash;
  if (hash.startsWith('#recipe/')) {
    const id = parseInt(hash.split('/')[1], 10);
    const recipe = allRecipes.find(r => r.id === id);
    if (recipe) {
      openRecipe(recipe);
      return;
    }
  }
  closeRecipe();
}

// ── Overlay Events ────────────────────────────

function setupOverlay() {
  document.getElementById('detailClose').addEventListener('click', closeRecipe);
  document.getElementById('overlayBackdrop').addEventListener('click', closeRecipe);

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeRecipe();
  });

  document.getElementById('resetFilters').addEventListener('click', () => {
    searchQuery = '';
    activeCategory = 'all';
    activeDietaryFilters.clear();

    document.getElementById('searchInput').value = '';
    document.getElementById('searchClear').hidden = true;

    document.querySelectorAll('.chip').forEach(c => {
      c.classList.toggle('active', c.dataset.category === 'all');
      c.setAttribute('aria-selected', c.dataset.category === 'all');
    });

    document.querySelectorAll('.dietary-chip').forEach(c => c.classList.remove('active'));
    updateDietaryCount();
    applyFilters();
  });
}

// ── Utilities ─────────────────────────────────

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// ── Init ──────────────────────────────────────

async function init() {
  setupTheme();
  setupSearch();
  setupOverlay();

  try {
    allRecipes = await loadRecipes();
    renderCategoryChips(getCategories(allRecipes));
    renderDietaryFilters(getDietaryFilters(allRecipes));
    filteredRecipes = allRecipes;
    renderGrid(allRecipes);
    handleHash();
  } catch (err) {
    console.error('Failed to load recipes:', err);
    document.getElementById('recipeGrid').innerHTML = `
      <p style="text-align:center;color:var(--c-text-muted);grid-column:1/-1;padding:48px 0;">
        Impossible de charger les recettes. Vérifiez que le serveur est lancé.
      </p>
    `;
  }

  window.addEventListener('hashchange', handleHash);
  window.addEventListener('popstate', handleHash);
}

init();

// ── Service Worker Registration ───────────────

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('sw.js').catch((err) => console.warn('SW registration failed:', err));
}
