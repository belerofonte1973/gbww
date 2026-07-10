// works.js — alphabetical list of works
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

  fetch('/api/works').then(r => r.json()).then(({ works }) => {
    document.getElementById('worksCount').textContent = `${works.length} obras`;
    const grid = document.getElementById('worksGrid');
    grid.classList.remove('loading');
    grid.innerHTML = works.map(w => `
      <a class="entry" href="${w.id}/obra.html">
        <span class="entry-lang">Volume ${w.volume_id || '?'}</span>
        <h3>${w.title}</h3>
        <div class="entry-meta"><span>${w.n_refs} remissões no Syntopicon</span></div>
      </a>`).join('');
  });
})();