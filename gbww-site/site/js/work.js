// work.js — full text of one work, page by page, with Syntopicon remissões
// rendered as inline highlights.
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

  // The work id is embedded in the URL: /obras/<id>/obra.html
  // (server rewrites /obras/<id>/obra.html to /obras/obra.html so
  // relative paths in the template resolve correctly). js/work.js
  // therefore reads the work id from the *original* URL via the
  // Referer, falling back to location.pathname for direct visits.
  let workId = 0;
  const fromPath = location.pathname.match(/\/obras\/(\d+)\/obra\.html/);
  if (fromPath) {
    workId = parseInt(fromPath[1], 10);
  } else {
    // Direct visit (e.g. /obras/obra.html?id=77) — read from query.
    workId = parseInt(new URLSearchParams(location.search).get("id") || "0", 10);
  }
  console.log('[work.js] workId =', workId);

  if (!workId) {
    document.getElementById('workTitle').textContent = 'Selecione uma obra em /obras/';
    return;
  }

  fetch(`/api/work/${workId}`).then(r => {
    console.log('[work.js] response status:', r.status);
    return r.json();
  }).then((data) => {
    console.log('[work.js] data keys:', Object.keys(data));
    const { work, refs, pages } = data;
    if (work.error) {
      document.getElementById('workTitle').textContent = 'Obra não encontrada';
      return;
    }
    document.title = `${work.title} — Obra`;
    document.getElementById('workKicker').textContent = `Volume ${work.volume_id} · ${work.volume_display || ''}`;
    document.getElementById('workTitle').textContent = work.title;
    document.getElementById('workLede').textContent =
      `${refs.length} remissões do Syntopicon. Texto integral por página e coluna.`;
    document.getElementById('pagesCount').textContent = `${pages.length} páginas`;

    // Map ref pages -> list of refs that mention them
    const refsByPage = new Map();
    refs.forEach(r => {
      if (r.page_start) {
        const ps = r.page_start.match(/^(\d+)([a-d])?$/);
        if (ps) {
          const num = parseInt(ps[1]);
          for (let p = num; p <= num + 0; p++) {
            // Map a-d variants to specific pages where applicable
            const key = r.page_start.replace(/[a-d]$/, '');
            const v = ps[2] || 'a';
            const k = `${key}${v}`;
            if (!refsByPage.has(k)) refsByPage.set(k, []);
            refsByPage.get(k).push(r);
          }
        }
      }
    });

    // TOC
    const tocNav = document.getElementById('tocNav');
    tocNav.innerHTML = pages.slice(0, 100).map(p =>
      `<a href="#page-${p.page_marker}">p. ${p.page_marker}</a>`).join('');
    if (pages.length > 100) {
      tocNav.insertAdjacentHTML('beforeend',
        `<a href="#" style="color:var(--muted)">… ${pages.length - 100} páginas a mais</a>`);
    }

    // Refs nav (sidebar)
    const refsNav = document.getElementById('refsNav');
    if (refs.length) {
      const byIdea = new Map();
      refs.forEach(r => {
        if (!byIdea.has(r.idea_number)) byIdea.set(r.idea_number, []);
        byIdea.get(r.idea_number).push(r);
      });
      let html = '';
      [...byIdea.entries()].sort((a, b) => a[0] - b[0]).forEach(([n, rs]) => {
        const ideaName = rs[0].idea_name;
        html += `<div class="ref-idea">${n}. ${ideaName}</div>`;
        rs.forEach(r => {
          html += `<a href="#ref-${r.id}">${r.topic_label}. ${r.page_start || ''}</a>`;
        });
      });
      refsNav.innerHTML = html;
    } else {
      refsNav.innerHTML = '<span style="color:var(--muted)">Nenhuma remissão.</span>';
    }

    // Pages
    const host = document.getElementById('pagesHost');
    if (!pages.length) {
      host.innerHTML = '<p class="shelf-desc">Texto integral ainda não extraído para esta obra.</p>';
      return;
    }
    host.innerHTML = pages.map(p => {
      const hasRef = refsByPage.has(p.page_marker);
      return `<section class="page-block ${hasRef ? 'has-refs' : ''}" id="page-${p.page_marker}">
        <div class="page-marker">[${p.page_marker}]</div>
        <div class="page-text">${escapeHtml(p.text)}</div>
      </section>`;
    }).join('');

    // If URL has #ref-<id>, scroll there
    if (location.hash) {
      const el = document.querySelector(location.hash);
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });

  function escapeHtml(s) {
    return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }
})();