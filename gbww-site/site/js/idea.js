// idea.js — show all topics under one idea (Syntopicon chapter layout)
(() => {
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

  const parts = location.pathname.split('/');
  // /ideias/<n>/idea.html -> parts = ['', 'ideias', '<n>', 'idea.html']
  const ideaN = parseInt(parts[parts.length - 2], 10);

  fetch(`/api/idea/${ideaN}`).then(r => r.json()).then(({ idea, topics }) => {
    document.getElementById('ideaKicker').textContent = `Idea ${idea.number} · Syntopicon volume ${idea.volume_id}`;
    document.getElementById('ideaTitle').textContent = idea.name;
    document.title = `${idea.name} — Idea ${idea.number}`;
    document.getElementById('ideaLede').textContent =
      `Capítulo ${idea.number} do Syntopicon (vol. ${idea.volume_id}). ${topics.length} tópicos catalogados.`;
    document.getElementById('topicCount').textContent = `${topics.length} tópicos`;

    // Group topics by parent_label for visual hierarchy
    const tops = topics.slice().sort((a, b) => {
      const an = parseInt(a.label), bn = parseInt(b.label);
      if (a.parent_label === null && b.parent_label !== null) return -1;
      if (a.parent_label !== null && b.parent_label === null) return 1;
      if (!isNaN(an) && !isNaN(bn) && an !== bn) return an - bn;
      return a.label.localeCompare(b.label);
    });
    const grid = document.getElementById('topicsGrid');
    grid.classList.remove('loading');
    grid.innerHTML = tops.map(t => `
      <a class="entry" href="../${ideaN}/${encodeURIComponent(t.label)}/topic.html">
        <span class="entry-lang">Tópico ${t.label}</span>
        <h3>${t.title || '(sem título)'}</h3>
        <div class="entry-meta"><span>${t.n_refs} referência${t.n_refs === 1 ? '' : 's'}</span></div>
      </a>`).join('');
  });
})();