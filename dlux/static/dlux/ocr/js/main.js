(function () {
    const POLL_MS = 4000;
    const timers = new WeakMap();

    function message(panel, text, isError) {
        const box = panel.querySelector('[data-dlux-ocr-message]');
        if (!box || !text) return;
        box.textContent = text;
        box.classList.toggle('text-danger', Boolean(isError));
        box.hidden = false;
    }

    function replace(panel, data, isError) {
        if (!data?.html || !panel.isConnected) return panel;
        const holder = document.createElement('div');
        holder.innerHTML = data.html.trim();
        const next = holder.firstElementChild;
        if (!next) return panel;
        panel.replaceWith(next);
        message(next, data.message, isError);
        watch(next);
        return next;
    }

    async function request(panel, method) {
        const options = { method, headers: { 'X-Requested-With': 'XMLHttpRequest' }, credentials: 'same-origin' };
        if (method === 'POST') options.headers['X-CSRFToken'] = panel.querySelector('input[name="csrfmiddlewaretoken"]')?.value || '';
        const response = await fetch(panel.dataset.ocrUrl, options);
        let data = null;
        try { data = await response.json(); } catch (_) { /* Non-JSON error page. */ }
        return { ok: response.ok, data };
    }

    function watch(panel) {
        clearTimeout(timers.get(panel));
        if (!panel.hasAttribute('data-ocr-active')) return;
        timers.set(panel, setTimeout(async () => {
            if (!panel.isConnected) return;
            try {
                const { ok, data } = await request(panel, 'GET');
                if (ok) replace(panel, data, false);
                else watch(panel);
            } catch (_) { watch(panel); }
        }, POLL_MS));
    }

    document.addEventListener('click', async (event) => {
        const button = event.target.closest('[data-dlux-ocr-run]');
        const panel = button?.closest('[data-dlux-ocr]');
        if (!panel) return;
        button.disabled = true;
        try {
            const { ok, data } = await request(panel, 'POST');
            const next = replace(panel, data, !ok);
            if (!ok && next === panel) {
                message(panel, data?.message || data?.error || panel.dataset.ocrError, true);
                button.disabled = false;
            }
        } catch (error) {
            message(panel, panel.dataset.ocrError, true);
            button.disabled = false;
        }
    });

    function initialize(root) {
        root.querySelectorAll('[data-dlux-ocr]').forEach(watch);
    }
    document.addEventListener('dlux:modal-content-loaded', (event) => initialize(event.target));
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => initialize(document));
    else initialize(document);
})();
