// ideas.js — list all 102 ideas
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

  fetch('/api/ideas').then(r => r.json()).then(({ ideas }) => {
    document.getElementById('ideaCount').textContent = `${ideas.length} ideias`;
    const grid = document.getElementById('ideasGrid');
    grid.classList.remove('loading');
    grid.innerHTML = ideas.map(it => `
      <a class="entry" href="../${it.number}/idea.html">
        <span class="entry-lang">Idea ${it.number}</span>
        <h3>${it.name}</h3>
        <div class="entry-meta"><span>${it.n_refs} referências · ${it.n_topics} tópicos</span></div>
      </a>`).join('');
  });
})();