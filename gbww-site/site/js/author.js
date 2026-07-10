// author.js — author detail: their works + their Syntopicon appearances
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

  // /autores/<name>/autor.html
  const parts = location.pathname.split('/');
  const name = decodeURIComponent(parts[parts.length - 2]);

  fetch(`/api/author/${encodeURIComponent(name)}`).then(r => r.json()).then(({ author, works }) => {
    if (!author) {
      document.getElementById('authorTitle').textContent = name;
      document.getElementById('worksList').innerHTML = `<li>Autor não encontrado.</li>`;
      return;
    }
    document.title = `${author.name} — Autores`;
    document.getElementById('authorTitle').textContent = author.name;
    document.getElementById('authorLede').textContent =
      `${works.length} obra${works.length === 1 ? '' : 's'} no acervo.`;
    document.getElementById('worksCount').textContent =
      `${works.length} obra${works.length === 1 ? '' : 's'}`;

    const worksList = document.getElementById('worksList');
    if (works.length) {
      worksList.innerHTML = works.map(w => `
        <li>
          <span class="ref-work">${w.work_title}</span>
          <span class="ref-pages">volume ${w.volume_id} · ${w.n_refs} remissões</span>
          <a class="ref-link" href="/obras/${w.work_id}/obra.html">abrir obra →</a>
        </li>`).join('');
    } else {
      worksList.innerHTML = '<li>Nenhuma obra catalogada.</li>';
    }

    // Now pull refs grouped by idea + topic
    fetch(`/api/author/${encodeURIComponent(name)}`).then(() => null);  // already fetched
    // Need a separate endpoint to fetch author refs (not just works).
    // We can add this to the API; for now reuse the works endpoint and
    // fetch full text per work.
    const refsList = document.getElementById('refsList');
    refsList.innerHTML = '';
    works.forEach((w, idx) => {
      fetch(`/api/work/${w.work_id}`).then(r => r.json()).then(({ refs }) => {
        if (!refs || !refs.length) return;
        const block = document.createElement('li');
        block.className = 'group-head';
        block.innerHTML = `<span>${w.work_title}</span>
          <span class="ref-meta">${refs.length} remissões no Syntopicon</span>`;
        refsList.appendChild(block);
        refs.forEach(r => {
          const li = document.createElement('li');
          li.id = `ref-${r.id}`;
          li.innerHTML = `
            <span class="ref-work">Idea ${r.idea_number} · ${r.idea_name} · tópico ${r.topic_label}</span>
            <span class="ref-pages">${r.page_start ? 'pp. ' + r.page_start : ''}${r.page_end && r.page_end !== r.page_start ? '–' + r.page_end : ''}</span>
            <a class="ref-link" href="/ideias/${r.idea_number}/${encodeURIComponent(r.topic_label)}/topic.html#ref-${r.id}">ver no tópico →</a>
          `;
          refsList.appendChild(li);
        });
      });
    });
  });
})();