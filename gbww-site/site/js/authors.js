// authors.js — alphabetical list of authors
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

  fetch('/api/authors').then(r => r.json()).then(({ authors }) => {
    document.getElementById('authorCount').textContent = `${authors.length} autores`;
    const grid = document.getElementById('authorsGrid');
    grid.classList.remove('loading');
    grid.innerHTML = authors.map(a => `
      <a class="entry" href="${encodeURIComponent(a.name)}/autor.html">
        <span class="entry-lang">${a.n_works} obra${a.n_works === 1 ? '' : 's'}</span>
        <h3>${a.name}</h3>
        <div class="entry-meta"><span>${a.n_refs} remissões no Syntopicon</span></div>
      </a>`).join('');
  });
})();