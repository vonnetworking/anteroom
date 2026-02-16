// Web UI destructive tool approval modal
// Listens for SSE event: destructive_approval_requested

(function () {
    function _ensureModal() {
        let el = document.getElementById('destructive-approval-modal');
        if (el) return el;

        el = document.createElement('div');
        el.id = 'destructive-approval-modal';
        el.className = 'approval-modal hidden';
        el.innerHTML = `
            <div class="approval-backdrop"></div>
            <div class="approval-card" role="dialog" aria-modal="true" aria-labelledby="approval-title">
                <div class="approval-title" id="approval-title">Approve destructive action</div>
                <pre class="approval-message" id="approval-message"></pre>
                <div class="approval-actions">
                    <button id="approval-cancel" class="btn secondary">Cancel</button>
                    <button id="approval-proceed" class="btn danger">Proceed</button>
                </div>
            </div>
        `;
        document.body.appendChild(el);
        return el;
    }

    function _show({ approval_id, message }) {
        const modal = _ensureModal();
        modal.classList.remove('hidden');
        modal.dataset.approvalId = approval_id;
        modal.querySelector('#approval-message').textContent = message || '';

        const cancelBtn = modal.querySelector('#approval-cancel');
        const proceedBtn = modal.querySelector('#approval-proceed');

        const cleanup = () => {
            cancelBtn.onclick = null;
            proceedBtn.onclick = null;
            modal.classList.add('hidden');
            delete modal.dataset.approvalId;
        };

        async function respond(approved) {
            try {
                // Prefer the app's API helper (adds db param + CSRF). Fall back to fetch.
                if (window.App && typeof window.App.api === 'function') {
                    await window.App.api('/api/approvals/respond', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ approval_id, approved })
                    });
                } else {
                    await fetch('/api/approvals/respond', {
                        method: 'POST',
                        credentials: 'same-origin',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ approval_id, approved })
                    });
                }
            } finally {
                cleanup();
            }
        }

        cancelBtn.onclick = () => respond(false);
        proceedBtn.onclick = () => respond(true);

        // Basic escape-to-cancel
        const onKeyDown = (e) => {
            if (e.key === 'Escape') {
                document.removeEventListener('keydown', onKeyDown);
                respond(false);
            }
        };
        document.addEventListener('keydown', onKeyDown);
    }

    window.Approvals = {
        show: _show,
    };
})();
