// topic.js — refs under one Syntopicon topic, grouped by author → work
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

  // /ideias/<n>/<label>/topic.html
  const parts = location.pathname.split('/');
  const ideaN = parseInt(parts[parts.length - 3], 10);
  const label = decodeURIComponent(parts[parts.length - 2]);

  // Kick off two fetches in parallel
  Promise.all([
    fetch(`/api/idea/${ideaN}`).then(r => r.json()),
    fetch(`/api/idea/${ideaN}/topic/${encodeURIComponent(label)}`).then(r => r.json()),
  ]).then(([ideaData, refsData]) => {
    const idea = ideaData.idea;
    const topic = ideaData.topics.find(t => t.label === label);
    document.title = `${topic?.title || label} — ${idea.name}`;
    document.getElementById('kicker').innerHTML =
      `Idea ${idea.number} · <a href="../idea.html">${idea.name}</a>`;
    document.getElementById('title').textContent = topic?.title || `(tópico ${label})`;
    document.getElementById('lede').textContent =
      `${refsData.refs.length} remissão${refsData.refs.length === 1 ? '' : 's'} do Syntopicon.`;
    document.getElementById('refCount').textContent = `${refsData.refs.length} referências`;

    // Group by author, then work
    const byAuthor = new Map();
    refsData.refs.forEach(r => {
      if (!byAuthor.has(r.author_name)) byAuthor.set(r.author_name, new Map());
      const works = byAuthor.get(r.author_name);
      if (!works.has(r.work_id)) works.set(r.work_id, { title: r.work_title, refs: [] });
      works.get(r.work_id).refs.push(r);
    });

    const enc = encodeURIComponent;
    const list = document.getElementById('refList');
    let html = '';
    [...byAuthor.entries()].sort((a, b) => a[0].localeCompare(b[0])).forEach(([author, works]) => {
      html += `<li class="group-head"><span>${author}</span></li>`;
      [...works.entries()].sort((a, b) => a[1].title.localeCompare(b[1].title)).forEach(([workId, w]) => {
        w.refs.forEach(r => {
          const pages = r.page_start
            ? `pp. ${r.page_start}${r.page_end && r.page_end !== r.page_start ? '–' + r.page_end : ''}`
            : '';
          html += `<li id="ref-${r.id}">
            <span class="ref-work">${w.title}</span>
            <span class="ref-pages">${pages}</span>
            <a class="ref-link" href="/obras/${r.work_id}/obra.html#ref-${r.id}">abrir obra →</a>
          </li>`;
        });
      });
    });
    list.innerHTML = html;
  });
})();