/* ============================================
   Datatouille — App Logic
   ============================================ */

const BASE_IMG = 'https://www.hamstouille.fr';

/* Data — populated at boot */
let allRecipes = [];
let allBlog = [];
let allMenus = [];
let methodDoc = null;
let tireDoc = null;
let recipeById = new Map();

/* View state */
let activeSection = 'recipes';      // 'recipes' | 'menus' | 'blog' | 'method' | 'tire'
let activeCategory = 'all';
let activeBlogCategory = 'all';
let activeDietaryFilters = new Set();
let searchQuery = '';

/* Section config drives header copy and which chrome is visible */
const SECTIONS = {
  recipes: {
    title: 'Les recettes de bébé',
    subtitle: '275 recettes pour accompagner la diversification alimentaire',
    showSearch: true,
    showFilters: true,
    showBlogFilters: false,
    searchPlaceholder: 'Chercher une recette, un ingrédient...',
  },
  menus: {
    title: 'Menus de la semaine',
    subtitle: 'Idées de repas équilibrés jour par jour',
    showSearch: false,
    showFilters: false,
    showBlogFilters: false,
  },
  blog: {
    title: 'Le blog',
    subtitle: '31 articles sur la diversification, le quotidien et la nutrition',
    showSearch: true,
    showFilters: false,
    showBlogFilters: true,
    searchPlaceholder: 'Chercher un article...',
  },
  method: {
    title: 'Ma méthode de diversification',
    subtitle: 'Un guide étape par étape, des purées aux morceaux',
    showSearch: false,
    showFilters: false,
    showBlogFilters: false,
  },
  tire: {
    title: 'Module tire-allaitement',
    subtitle: '15 chapitres vidéo pour gérer le tire-allaitement',
    showSearch: false,
    showFilters: false,
    showBlogFilters: false,
  },
};

// ── Data Loading ──────────────────────────────

async function loadJson(path) {
  const resp = await fetch(path);
  if (!resp.ok) throw new Error(`Failed to load ${path}`);
  return resp.json();
}

async function loadAll() {
  const [recipes, blog, menus, method, tire] = await Promise.all([
    loadJson('recipes.json'),
    loadJson('blog.json'),
    loadJson('menus.json'),
    loadJson('diversification.json'),
    loadJson('tire_allaitement.json'),
  ]);
  return { recipes, blog, menus, method, tire };
}

// ── Recipe rendering (existing logic, lightly refactored) ─────

function getCategories(recipes) {
  const cats = new Map();
  for (const r of recipes) {
    if (r.category && !cats.has(r.category)) cats.set(r.category, r.category_id);
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
      if (name && !filters.has(id)) filters.set(id, name);
    }
  }
  return [...filters.entries()].sort((a, b) => a[1].localeCompare(b[1], 'fr'));
}

function renderCategoryChips(categories) {
  const container = document.getElementById('categoryChips');
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
    renderRecipes();
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
    renderRecipes();
  });
}

function updateDietaryCount() {
  const badge = document.getElementById('dietaryCount');
  const count = activeDietaryFilters.size;
  badge.textContent = count;
  badge.hidden = count === 0;
}

function imageUrl(item) {
  const candidate = item.image || item.thumbnail || item.hero_image;
  if (!candidate) return null;
  return candidate.startsWith('http') ? candidate : BASE_IMG + candidate;
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
        : `<div class="card-image-placeholder"><svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M6 13.87A4 4 0 0 1 7.41 6a5.11 5.11 0 0 1 1.05-1.54 5 5 0 0 1 7.08 0A5.11 5.11 0 0 1 16.59 6 4 4 0 0 1 18 13.87V21H6Z"/><line x1="6" y1="17" x2="18" y2="17"/></svg></div>`
      }
      ${badges.length ? `<div class="card-badges">${badges.join('')}</div>` : ''}
    </div>
    <div class="card-body">
      <div class="card-category">${escapeHtml(recipe.category || '')}</div>
      <h2 class="card-title">${escapeHtml(recipe.title)}</h2>
      ${allergenTags ? `<div class="card-tags">${allergenTags}</div>` : ''}
    </div>
  `;

  card.addEventListener('click', () => openRecipeById(recipe.id));
  card.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openRecipeById(recipe.id); }
  });
  return card;
}

function renderRecipes() {
  const q = normalize(searchQuery);
  const filtered = allRecipes.filter(r => {
    if (activeCategory !== 'all' && r.category !== activeCategory) return false;
    if (activeDietaryFilters.size > 0) {
      for (const fid of activeDietaryFilters) {
        if (!r.filter_ids || !r.filter_ids.includes(fid)) return false;
      }
    }
    if (q) {
      const searchable = normalize(
        [r.title, r.category, ...(r.ingredients || []), r.description || ''].join(' ')
      );
      const terms = q.split(/\s+/).filter(Boolean);
      for (const t of terms) if (!searchable.includes(t)) return false;
    }
    return true;
  });

  const grid = document.getElementById('recipeGrid');
  const noResults = document.getElementById('noResults');
  grid.innerHTML = '';
  if (filtered.length === 0) {
    noResults.hidden = false;
    grid.style.display = 'none';
  } else {
    noResults.hidden = true;
    grid.style.display = '';
    const frag = document.createDocumentFragment();
    filtered.forEach((r, i) => frag.appendChild(createRecipeCard(r, i)));
    grid.appendChild(frag);
  }
  document.getElementById('resultsCount').textContent =
    `${filtered.length} recette${filtered.length !== 1 ? 's' : ''}`;
}

// ── Blog rendering ───────────────────────────────────

function renderBlogCategoryChips() {
  const cats = [...new Set(allBlog.map(a => a.category).filter(Boolean))];
  const container = document.getElementById('blogCategoryChips');
  for (const name of cats) {
    const btn = document.createElement('button');
    btn.className = 'chip';
    btn.dataset.blogCategory = name;
    btn.textContent = name;
    btn.type = 'button';
    container.appendChild(btn);
  }
  container.addEventListener('click', (e) => {
    const chip = e.target.closest('.chip');
    if (!chip) return;
    activeBlogCategory = chip.dataset.blogCategory;
    container.querySelectorAll('.chip').forEach(c => {
      c.classList.toggle('active', c.dataset.blogCategory === activeBlogCategory);
    });
    renderBlog();
  });
}

function createBlogCard(article, index) {
  const imgUrl = imageUrl(article);
  const card = document.createElement('article');
  card.className = 'recipe-card';
  card.style.animationDelay = `${Math.min(index * 30, 300)}ms`;
  card.setAttribute('tabindex', '0');
  card.setAttribute('role', 'link');
  card.setAttribute('aria-label', article.title);

  card.innerHTML = `
    <div class="card-image-wrapper">
      ${imgUrl
        ? `<img class="card-image" src="${escapeHtml(imgUrl)}" alt="${escapeHtml(article.title)}" loading="lazy" onerror="this.parentElement.innerHTML='<div class=card-image-placeholder>📖</div>'">`
        : `<div class="card-image-placeholder">📖</div>`
      }
    </div>
    <div class="card-body">
      <div class="card-category">${escapeHtml(article.category || 'Article')}</div>
      <h2 class="card-title">${escapeHtml(article.title)}</h2>
      ${article.intro_text ? `<p class="card-excerpt">${escapeHtml(truncate(article.intro_text, 120))}</p>` : ''}
    </div>
  `;
  card.addEventListener('click', () => openBlog(article.id));
  card.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openBlog(article.id); }
  });
  return card;
}

function renderBlog() {
  const q = normalize(searchQuery);
  const filtered = allBlog.filter(a => {
    if (activeBlogCategory !== 'all' && a.category !== activeBlogCategory) return false;
    if (q) {
      const searchable = normalize([a.title, a.category, a.intro_text, a.content_text].join(' '));
      for (const t of q.split(/\s+/).filter(Boolean)) {
        if (!searchable.includes(t)) return false;
      }
    }
    return true;
  });
  const grid = document.getElementById('blogGrid');
  grid.innerHTML = '';
  const frag = document.createDocumentFragment();
  filtered.forEach((a, i) => frag.appendChild(createBlogCard(a, i)));
  grid.appendChild(frag);
  document.getElementById('resultsCount').textContent =
    `${filtered.length} article${filtered.length !== 1 ? 's' : ''}`;
}

// ── Menus rendering ───────────────────────────────────

function createMenuCard(menu, index) {
  const card = document.createElement('article');
  card.className = 'menu-card';
  card.style.animationDelay = `${Math.min(index * 50, 300)}ms`;
  card.setAttribute('tabindex', '0');
  card.setAttribute('role', 'link');
  card.setAttribute('aria-label', menu.title);

  // Show first 2-3 recipe titles as a teaser, plus a count
  const sampleNames = (menu.recipe_ids || [])
    .slice(0, 3)
    .map(id => recipeById.get(id)?.title)
    .filter(Boolean);

  card.innerHTML = `
    <div class="menu-card-header">
      <span class="menu-card-pill">Semaine</span>
      <h2 class="menu-card-title">${escapeHtml(menu.title || `Menu #${menu.id}`)}</h2>
    </div>
    <div class="menu-card-body">
      <p class="menu-card-meta">${menu.days?.length || 0} jours · ${menu.recipe_ids?.length || 0} recettes</p>
      ${sampleNames.length ? `<ul class="menu-card-samples">${sampleNames.map(n => `<li>${escapeHtml(n)}</li>`).join('')}</ul>` : ''}
    </div>
  `;
  card.addEventListener('click', () => openMenu(menu.id));
  card.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openMenu(menu.id); }
  });
  return card;
}

function renderMenus() {
  const grid = document.getElementById('menuGrid');
  grid.innerHTML = '';
  const frag = document.createDocumentFragment();
  allMenus.forEach((m, i) => frag.appendChild(createMenuCard(m, i)));
  grid.appendChild(frag);
  document.getElementById('resultsCount').textContent =
    `${allMenus.length} menu${allMenus.length !== 1 ? 's' : ''}`;
}

// ── Document views (méthode + tire-allaitement) ──────

function renderDocument(doc, tocEl, bodyEl) {
  // Build TOC
  tocEl.innerHTML = `
    <h3 class="doc-toc-title">Sommaire</h3>
    <nav><ul class="doc-toc-list">
      ${doc.sections.map((s, i) => `
        <li><a href="#sec-${i}">${escapeHtml(s.heading)}</a></li>
      `).join('')}
    </ul></nav>
  `;

  // Build body
  let html = `<h1 class="doc-title">${escapeHtml(doc.title || '')}</h1>`;
  if (doc.intro_html) {
    html += `<div class="doc-intro">${doc.intro_html}</div>`;
  }
  for (let i = 0; i < doc.sections.length; i++) {
    const s = doc.sections[i];
    html += `
      <section class="doc-section" id="sec-${i}">
        <h2 class="doc-section-title">${escapeHtml(s.heading)}</h2>
        ${s.content_html || ''}
        ${(s.videos || []).map(v => `
          <video controls preload="metadata" class="doc-video">
            <source src="${escapeHtml(v)}" type="video/mp4">
          </video>
        `).join('')}
        ${(s.pdfs || []).length ? `
          <div class="doc-attachments">
            ${s.pdfs.map(p => `<a class="doc-pdf-link" href="${escapeHtml(p)}" target="_blank" rel="noopener">📄 PDF</a>`).join('')}
          </div>
        ` : ''}
      </section>
    `;
  }
  bodyEl.innerHTML = html;

  // Smooth scroll inside the doc body
  tocEl.querySelectorAll('a[href^="#sec-"]').forEach(a => {
    a.addEventListener('click', (e) => {
      e.preventDefault();
      const id = a.getAttribute('href').slice(1);
      const target = bodyEl.querySelector(`#${id}`);
      if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });
}

// ── Detail Overlay (recipe / blog / menu) ────────────

function openRecipeById(id) {
  const recipe = recipeById.get(typeof id === 'string' ? parseInt(id, 10) : id);
  if (!recipe) return;
  openOverlay(buildRecipeDetailHtml(recipe), `recipe/${recipe.id}`);
}

function openBlog(id) {
  const article = allBlog.find(a => a.id === (typeof id === 'string' ? parseInt(id, 10) : id));
  if (!article) return;
  openOverlay(buildBlogDetailHtml(article), `blog/${article.id}`);
}

function openMenu(id) {
  const menu = allMenus.find(m => m.id === (typeof id === 'string' ? parseInt(id, 10) : id));
  if (!menu) return;
  openOverlay(buildMenuDetailHtml(menu), `menu/${menu.id}`);
}

function buildRecipeDetailHtml(recipe) {
  const imgUrl = imageUrl(recipe);
  const ingredientsList = (recipe.ingredients || [])
    .map(i => `<li class="ingredient-item"><span class="ingredient-bullet"></span><span>${escapeHtml(i)}</span></li>`).join('');
  const stepsList = (recipe.steps || [])
    .map((s, idx) => `<li class="step-item"><span class="step-number">${idx + 1}</span><span class="step-text">${escapeHtml(s)}</span></li>`).join('');
  const allergenTags = (recipe.allergens || [])
    .map(a => `<span class="allergen-tag">${escapeHtml(a)}</span>`).join('');
  const filterTags = (recipe.filters || [])
    .map(f => `<span class="detail-filter-tag">${escapeHtml(f)}</span>`).join('');

  const metaBadges = [];
  if (recipe.freezable) metaBadges.push('<span class="detail-badge badge-freeze">Congélation possible</span>');
  if (recipe.filters?.includes('Recette vegan')) metaBadges.push('<span class="detail-badge badge-vegan">Vegan</span>');
  else if (recipe.filters?.includes('Recette végétarienne')) metaBadges.push('<span class="detail-badge badge-vegetarian">Végétarien</span>');

  return `
    <div class="detail-hero">
      ${imgUrl
        ? `<img src="${escapeHtml(imgUrl)}" alt="${escapeHtml(recipe.title)}" onerror="this.parentElement.innerHTML='<div class=detail-hero-placeholder>🍽️</div>'">`
        : `<div class="detail-hero-placeholder">🍽️</div>`
      }
    </div>
    <div class="detail-body">
      <div class="detail-category">${escapeHtml(recipe.category || '')}</div>
      <h1 class="detail-title">${escapeHtml(recipe.title)}</h1>
      ${metaBadges.length ? `<div class="detail-meta">${metaBadges.join('')}</div>` : ''}
      ${recipe.description ? `<p class="detail-description">${escapeHtml(recipe.description)}</p>` : ''}
      ${ingredientsList ? `<section class="detail-section"><h2 class="detail-section-title">Ingrédients</h2><ul class="ingredient-list">${ingredientsList}</ul></section>` : ''}
      ${stepsList ? `<section class="detail-section"><h2 class="detail-section-title">Préparation</h2><ol class="step-list">${stepsList}</ol></section>` : ''}
      ${allergenTags ? `<section class="detail-section"><h2 class="detail-section-title">Allergènes</h2><div class="allergen-list">${allergenTags}</div></section>` : ''}
      ${recipe.storage_tip ? `<div class="storage-tip"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg><span>${escapeHtml(recipe.storage_tip)}</span></div>` : ''}
      ${filterTags ? `<div class="detail-filters">${filterTags}</div>` : ''}
    </div>
  `;
}

function buildBlogDetailHtml(article) {
  const img = imageUrl(article);
  return `
    <div class="detail-hero">
      ${img
        ? `<img src="${escapeHtml(img)}" alt="${escapeHtml(article.title)}" onerror="this.parentElement.innerHTML='<div class=detail-hero-placeholder>📖</div>'">`
        : `<div class="detail-hero-placeholder">📖</div>`
      }
    </div>
    <div class="detail-body">
      <div class="detail-category">${escapeHtml(article.category || 'Article')}</div>
      <h1 class="detail-title">${escapeHtml(article.title)}</h1>
      ${article.intro_html ? `<div class="article-intro">${article.intro_html}</div>` : ''}
      <div class="article-body">${article.content_html || ''}</div>
    </div>
  `;
}

function buildMenuDetailHtml(menu) {
  const dayBlocks = (menu.days || []).map(d => `
    <div class="menu-day">
      <h3 class="menu-day-title">${escapeHtml(d.day)}</h3>
      ${d.meals.map(meal => `
        <div class="menu-meal">
          <div class="menu-meal-label">${escapeHtml(meal.meal)}</div>
          <ul class="menu-items">
            ${meal.items.map(it => it.recipe_id
              ? `<li><a class="menu-item-link" href="#recipe/${it.recipe_id}" data-recipe-id="${it.recipe_id}">${escapeHtml(it.text)}</a></li>`
              : `<li class="menu-item-plain">${escapeHtml(it.text)}</li>`
            ).join('')}
          </ul>
        </div>
      `).join('')}
    </div>
  `).join('');

  return `
    <div class="detail-body" style="padding-top: var(--space-2xl);">
      <div class="detail-category">Menu</div>
      <h1 class="detail-title">${escapeHtml(menu.title || `Menu #${menu.id}`)}</h1>
      <p class="detail-description">${menu.recipe_ids?.length || 0} recettes liées · cliquez sur un nom pour ouvrir la recette</p>
      <div class="menu-week">${dayBlocks}</div>
    </div>
  `;
}

function openOverlay(innerHtml, hashRoute) {
  const overlay = document.getElementById('overlay');
  const content = document.getElementById('detailContent');
  content.innerHTML = innerHtml;
  // Reset scroll inside the overlay so each new item starts at the top
  overlay.scrollTop = 0;
  document.querySelector('.recipe-detail').scrollTop = 0;
  overlay.hidden = false;
  document.body.style.overflow = 'hidden';
  if (hashRoute) history.pushState(null, '', `#${hashRoute}`);
  document.getElementById('detailClose').focus();
}

function closeOverlay() {
  const overlay = document.getElementById('overlay');
  overlay.hidden = true;
  document.body.style.overflow = '';
  if (location.hash.startsWith('#recipe/') ||
      location.hash.startsWith('#blog/') ||
      location.hash.startsWith('#menu/')) {
    history.pushState(null, '', location.pathname + location.search);
  }
}

// ── Section Switching ────────────────────────────────

function switchSection(name) {
  if (!SECTIONS[name]) name = 'recipes';
  activeSection = name;
  const cfg = SECTIONS[name];

  // Update tabs
  document.querySelectorAll('.section-tab').forEach(t => {
    t.classList.toggle('active', t.dataset.section === name);
  });

  // Update hero copy
  document.getElementById('heroTitle').textContent = cfg.title;
  document.getElementById('heroSubtitle').textContent = cfg.subtitle;
  document.getElementById('searchWrapper').hidden = !cfg.showSearch;
  document.getElementById('filters').hidden = !cfg.showFilters;
  document.getElementById('blogFilters').hidden = !cfg.showBlogFilters;
  if (cfg.searchPlaceholder) {
    document.getElementById('searchInput').placeholder = cfg.searchPlaceholder;
  }
  document.getElementById('resultsBar').hidden = (name === 'method' || name === 'tire');

  // Reset search across sections (each section has its own filter state)
  searchQuery = '';
  document.getElementById('searchInput').value = '';
  document.getElementById('searchClear').hidden = true;

  // Show only the selected view
  document.querySelectorAll('.section-view').forEach(v => v.hidden = true);
  document.getElementById(`view-${name}`).hidden = false;

  // Render
  if (name === 'recipes') renderRecipes();
  else if (name === 'blog') renderBlog();
  else if (name === 'menus') renderMenus();
  else if (name === 'method') renderDocument(methodDoc, document.getElementById('methodToc'), document.getElementById('methodBody'));
  else if (name === 'tire') renderDocument(tireDoc, document.getElementById('tireToc'), document.getElementById('tireBody'));

  // Update hash to reflect section (unless an item overlay is open)
  if (!location.hash.startsWith('#recipe/') &&
      !location.hash.startsWith('#blog/') &&
      !location.hash.startsWith('#menu/')) {
    const target = name === 'recipes' ? '' : `#section/${name}`;
    history.replaceState(null, '', location.pathname + location.search + target);
  }
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
      if (activeSection === 'recipes') renderRecipes();
      else if (activeSection === 'blog') renderBlog();
    }, 150);
  });
  clearBtn.addEventListener('click', () => {
    input.value = '';
    searchQuery = '';
    clearBtn.hidden = true;
    if (activeSection === 'recipes') renderRecipes();
    else if (activeSection === 'blog') renderBlog();
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
    if (recipeById.has(id)) { openRecipeById(id); return; }
  } else if (hash.startsWith('#blog/')) {
    const id = parseInt(hash.split('/')[1], 10);
    if (allBlog.find(a => a.id === id)) { openBlog(id); return; }
  } else if (hash.startsWith('#menu/')) {
    const id = parseInt(hash.split('/')[1], 10);
    if (allMenus.find(m => m.id === id)) { openMenu(id); return; }
  } else if (hash.startsWith('#section/')) {
    const sec = hash.split('/')[1];
    if (SECTIONS[sec]) { switchSection(sec); return; }
  }
  closeOverlay();
}

// ── Internal-link interceptor ──────────────────────
// Click on /recettes/N or /blog/N inside any rendered HTML opens the overlay
function setupLinkInterceptor() {
  document.body.addEventListener('click', (e) => {
    const a = e.target.closest('a[href]');
    if (!a) return;
    const href = a.getAttribute('href') || '';
    let m = href.match(/(?:hamstouille\.fr)?\/recettes\/(\d+)/);
    if (m) {
      const id = parseInt(m[1], 10);
      if (recipeById.has(id)) { e.preventDefault(); openRecipeById(id); return; }
    }
    m = href.match(/(?:hamstouille\.fr)?\/blog\/(\d+)/);
    if (m) {
      const id = parseInt(m[1], 10);
      if (allBlog.find(x => x.id === id)) { e.preventDefault(); openBlog(id); return; }
    }
    // Section tab clicks
    if (a.classList.contains('section-tab')) {
      e.preventDefault();
      switchSection(a.dataset.section);
    }
  });
}

// ── Section tab clicks ──────────
function setupSectionTabs() {
  document.querySelectorAll('.section-tab').forEach(t => {
    t.addEventListener('click', (e) => {
      e.preventDefault();
      switchSection(t.dataset.section);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  });
}

// ── Overlay Events ────────────────────────────

function setupOverlay() {
  document.getElementById('detailClose').addEventListener('click', closeOverlay);
  document.getElementById('overlayBackdrop').addEventListener('click', closeOverlay);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeOverlay(); });

  document.getElementById('resetFilters').addEventListener('click', () => {
    searchQuery = '';
    activeCategory = 'all';
    activeDietaryFilters.clear();
    document.getElementById('searchInput').value = '';
    document.getElementById('searchClear').hidden = true;
    document.querySelectorAll('#categoryChips .chip').forEach(c => {
      c.classList.toggle('active', c.dataset.category === 'all');
    });
    document.querySelectorAll('.dietary-chip').forEach(c => c.classList.remove('active'));
    updateDietaryCount();
    renderRecipes();
  });
}

// ── Utilities ─────────────────────────────────

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str ?? '';
  return div.innerHTML;
}

function normalize(str) {
  return (str || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
}

function truncate(str, n) {
  str = (str || '').replace(/\s+/g, ' ').trim();
  return str.length <= n ? str : str.slice(0, n - 1) + '…';
}

// ── Init ──────────────────────────────────────

async function init() {
  setupTheme();
  setupSearch();
  setupOverlay();
  setupSectionTabs();
  setupLinkInterceptor();

  try {
    const data = await loadAll();
    allRecipes = data.recipes;
    allBlog = data.blog;
    allMenus = data.menus;
    methodDoc = data.method;
    tireDoc = data.tire;
    recipeById = new Map(allRecipes.map(r => [r.id, r]));

    // Update subtitles with real counts
    SECTIONS.recipes.subtitle = `${allRecipes.length} recettes pour accompagner la diversification alimentaire`;
    SECTIONS.blog.subtitle = `${allBlog.length} articles sur la diversification, le quotidien et la nutrition`;
    SECTIONS.menus.subtitle = `${allMenus.length} semaines de menus équilibrés`;
    SECTIONS.tire.subtitle = `${tireDoc?.sections?.length || 15} chapitres vidéo pour gérer le tire-allaitement`;

    renderCategoryChips(getCategories(allRecipes));
    renderDietaryFilters(getDietaryFilters(allRecipes));
    renderBlogCategoryChips();

    // Honor hash on first load
    if (location.hash.startsWith('#section/')) {
      switchSection(location.hash.split('/')[1]);
    } else {
      switchSection('recipes');
    }
    handleHash();
  } catch (err) {
    console.error('Failed to load data:', err);
    document.getElementById('recipeGrid').innerHTML = `
      <p style="text-align:center;color:var(--c-text-muted);grid-column:1/-1;padding:48px 0;">
        Impossible de charger les données. Vérifiez que le serveur est lancé.
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
