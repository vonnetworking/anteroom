/* Minimal GitHub integration UI (uses gh via backend). CSP-safe: no inline scripts. */

window.GitHub = (() => {
  function _qs(sel) {
    return document.querySelector(sel);
  }

  function _el(tag, attrs = {}, text = null) {
    const el = document.createElement(tag);
    Object.entries(attrs).forEach(([k, v]) => {
      if (k === 'class') el.className = v;
      else el.setAttribute(k, v);
    });
    if (text != null) el.textContent = text;
    return el;
  }

  function _ensureModal() {
    if (_qs('#gh-modal-overlay')) return;

    const overlay = _el('div', { id: 'gh-modal-overlay', class: 'gh-modal-overlay', style: 'display:none' });
    const modal = _el('div', { class: 'gh-modal' });

    const header = _el('div', { class: 'gh-modal-header' });
    header.appendChild(_el('div', { class: 'gh-modal-title' }, 'GitHub'));
    const close = _el('button', { class: 'gh-btn gh-btn-secondary', id: 'gh-close' }, 'Close');
    header.appendChild(close);

    const body = _el('div', { class: 'gh-modal-body' });

    const authRow = _el('div', { class: 'gh-row' });
    const authBtn = _el('button', { class: 'gh-btn gh-btn-secondary', id: 'gh-auth-status' }, 'Auth status');
    const authOut = _el('pre', { class: 'gh-output', id: 'gh-auth-output' });
    authRow.appendChild(authBtn);
    authRow.appendChild(authOut);

    const form = _el('div', { class: 'gh-form' });
    form.appendChild(_el('label', {}, 'Repo (owner/name)'));
    const repo = _el('input', { id: 'gh-repo', class: 'gh-input', placeholder: 'troylar/anteroom' });
    form.appendChild(repo);

    form.appendChild(_el('label', {}, 'PR number'));
    const pr = _el('input', { id: 'gh-pr', class: 'gh-input', placeholder: '86', inputmode: 'numeric' });
    form.appendChild(pr);

    form.appendChild(_el('label', {}, 'Comment body'));
    const comment = _el('textarea', { id: 'gh-body', class: 'gh-textarea', rows: '8', placeholder: 'Write a PR comment…' });
    form.appendChild(comment);

    const actions = _el('div', { class: 'gh-actions' });
    const post = _el('button', { class: 'gh-btn gh-btn-primary', id: 'gh-post' }, 'Post comment');
    const status = _el('div', { class: 'gh-status', id: 'gh-status' }, '');
    actions.appendChild(post);
    actions.appendChild(status);

    body.appendChild(authRow);
    body.appendChild(form);
    body.appendChild(actions);

    modal.appendChild(header);
    modal.appendChild(body);
    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    close.addEventListener('click', () => hide());
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) hide();
    });

    authBtn.addEventListener('click', async () => {
      authOut.textContent = '';
      try {
        const res = await App.api('/api/github/auth/status');
        authOut.textContent = (res.stdout || res.stderr || '').trim();
      } catch (e) {
        authOut.textContent = String(e);
      }
    });

    post.addEventListener('click', async () => {
      status.textContent = '';
      status.classList.remove('ok', 'err');

      const payload = {
        repo: repo.value.trim(),
        pr_number: parseInt(pr.value.trim(), 10),
        body: comment.value,
      };

      try {
        await App.api('/api/github/pr/comment', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        status.textContent = 'Posted.';
        status.classList.add('ok');
      } catch (e) {
        status.textContent = String(e);
        status.classList.add('err');
      }
    });
  }

  function show(prefill = {}) {
    _ensureModal();
    const overlay = _qs('#gh-modal-overlay');
    overlay.style.display = '';

    const repo = _qs('#gh-repo');
    const pr = _qs('#gh-pr');
    const body = _qs('#gh-body');

    if (prefill.repo) repo.value = prefill.repo;
    if (prefill.pr_number) pr.value = String(prefill.pr_number);
    if (prefill.body) body.value = prefill.body;
  }

  function hide() {
    const overlay = _qs('#gh-modal-overlay');
    if (overlay) overlay.style.display = 'none';
  }

  function init() {
    _ensureModal();
    // Add a Settings button entry
    const settingsBtn = document.getElementById('btn-settings');
    if (!settingsBtn) return;

    // Add a small GitHub button next to settings in sidebar footer.
    if (document.getElementById('btn-github')) return;

    const footer = document.getElementById('sidebar-footer');
    if (!footer) return;

    const btn = _el('button', { class: 'btn-settings', id: 'btn-github', title: 'GitHub' });
    btn.appendChild(_el('span', {}, 'GitHub'));
    btn.addEventListener('click', () => show());
    footer.insertBefore(btn, footer.firstChild);
  }

  return { init, show, hide };
})();
