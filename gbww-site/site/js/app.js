// index.js — homepage: loads ideas, authors, works, search.
(() => {
  // ---------- theme ----------
  const themeBtn = document.getElementById('themeToggle');
  const root = document.documentElement;
  function applyTheme(t) {
    root.setAttribute('data-theme', t);
    themeBtn.textContent = t === 'dark' ? 'Modo claro' : 'Modo escuro';
  }
  applyTheme(localStorage.getItem('gbww-theme') || 'light');
  themeBtn.addEventListener('click', () => {
    const next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    localStorage.setItem('gbww-theme', next);
    applyTheme(next);
  });

  // ---------- helpers ----------
  const enc = (s) => encodeURIComponent(s);
  const entryHTML = (cls, href, kicker, title, meta) => `
    <a class="entry ${cls}" href="${href}">
      <span class="entry-lang">${kicker}</span>
      <h3>${title}</h3>
      ${meta ? `<div class="entry-meta"><span>${meta}</span></div>` : ''}
    </a>`;

  // ---------- ideas ----------
  fetch('/api/ideas').then(r => r.json()).then(({ ideas }) => {
    document.getElementById('ideaCount').textContent = `${ideas.length} ideias`;
    const grid = document.getElementById('ideasGrid');
    grid.classList.remove('loading');
    grid.innerHTML = '';
    ideas.slice(0, 12).forEach(it => {
      grid.insertAdjacentHTML('beforeend', entryHTML(
        'entry-idea',
        `ideias/${it.number}/idea.html`,
        `Idea ${it.number}`,
        it.name,
        `${it.n_refs} referências · ${it.n_topics} tópicos`,
      ));
    });
  });

  // ---------- authors ----------
  fetch('/api/authors').then(r => r.json()).then(({ authors }) => {
    document.getElementById('authorsList').classList.remove('loading');
    const list = document.getElementById('authorsList');
    list.innerHTML = '';
    authors.slice(0, 12).forEach(a => {
      list.insertAdjacentHTML('beforeend', entryHTML(
        'entry-author',
        `autores/${enc(a.name)}/autor.html`,
        `${a.n_works} obra${a.n_works === 1 ? '' : 's'}`,
        a.name,
        `${a.n_refs} remissões no Syntopicon`,
      ));
    });
  });

  // ---------- works ----------
  fetch('/api/works').then(r => r.json()).then(({ works }) => {
    document.getElementById('worksList').classList.remove('loading');
    const list = document.getElementById('worksList');
    list.innerHTML = '';
    works.slice(0, 12).forEach(w => {
      list.insertAdjacentHTML('beforeend', entryHTML(
        'entry-work',
        `obras/${w.id}/obra.html`,
        `Volume ${w.volume_id || '?'}`,
        w.title,
        `${w.n_refs} remissões no Syntopicon`,
      ));
    });
  });

  // ---------- search ----------
  const form = document.getElementById('searchForm');
  const input = document.getElementById('searchInput');
  const results = document.getElementById('results');
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const q = input.value.trim();
    if (!q) return;
    results.hidden = false;
    results.innerHTML = `<div class="loading">Buscando "${q}"…</div>`;
    fetch(`/api/search?q=${enc(q)}&limit=50`).then(r => r.json()).then(({ hits }) => {
      if (!hits.length) {
        results.innerHTML = `<p class="shelf-desc">Sem resultados para "${q}".</p>`;
        return;
      }
      results.innerHTML = `<div class="shelf-head"><h2>Resultados para "${q}"</h2><span class="count">${hits.length} remissões</span></div>` +
        `<ol class="ref-list">${hits.map(h => `
          <li>
            <span class="ref-author">${h.author_name}</span>
            <span class="ref-work">${h.work_title}</span>
            <span class="ref-pages">idea ${h.idea_number} (${h.idea_name}) · tópico ${h.topic_label} · pp. ${h.page_start || '?'}${h.page_end && h.page_end !== h.page_start ? '–' + h.page_end : ''}</span>
            <a class="ref-link" href="/obras/${h.work_id}/obra.html#ref-${h.id}">abrir obra →</a>
          </li>`).join('')}</ol>`;
      results.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });
  document.querySelectorAll('.examples a[data-q]').forEach(a => {
    a.addEventListener('click', (e) => {
      e.preventDefault();
      input.value = a.dataset.q;
      form.dispatchEvent(new Event('submit'));
    });
  });
})();