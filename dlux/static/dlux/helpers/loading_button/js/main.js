/**
 * Dlux Loading Button
 * -------------------------------------------------------------------------
 * One reusable spinner-in-button primitive for the whole DjangoLux ecosystem,
 * replacing the bespoke disable/spinner/restore code copy-pasted across login,
 * scan, dynamic-modal, updater, 2FA, etc.
 *
 * Three ways to use it (all build on the same low-level handle):
 *
 *  1. Promise API (for your own JS) — spinner for the lifetime of an async fn:
 *       DluxLoadingButton.run(btn, async (handle) => {
 *           const r = await fetch(...); handle.update('Saving…'); ...
 *       });
 *     or the low-level form when you control completion yourself:
 *       const handle = DluxLoadingButton.start(btn, { label: 'Saving…' });
 *       handle.update(msg, progress); handle.done(); handle.error(msg);
 *
 *  2. Submit spinner (declarative) — add `data-dlux-loading` to a submit button
 *     and it shows the spinner while its form submits (cooperates with
 *     prevent_double_submit; the page navigates, so no restore is needed).
 *
 *  3. Task-polling (declarative) — a button that kicks off a server task and
 *     polls until it finishes:
 *       <button data-dlux-loading
 *               data-dlux-loading-start="/things/42/rebuild/"
 *               data-dlux-loading-poll="/things/42/rebuild/status/"
 *               data-dlux-loading-interval="1500"
 *               data-dlux-loading-label="Rebuilding…">Rebuild</button>
 *     POSTs `start` (CSRF-aware), then polls `poll` reading the JSON contract
 *     `{ status, progress, message, redirect, error }`. Terminal success
 *     statuses (complete/completed/done/success/finished/ok) finish the button
 *     (or follow `redirect`); failure statuses (error/failed/cancelled) put it
 *     in the error state. If `start` is omitted, the poll URL is hit directly.
 *
 *  4. Custom event (declarative) — `data-dlux-loading-event="my:event"` makes
 *     the button go busy on click and dispatch your event with the handle in
 *     `detail.handle`; your listener does the async work and calls
 *     `handle.done()` / `handle.error()`.
 *
 * Every transition also dispatches a bubbling DOM event on the button:
 *   dlux:loading:start, dlux:loading:poll, dlux:loading:done, dlux:loading:error
 */
(function () {
    'use strict';

    var SUCCESS_STATES = ['complete', 'completed', 'done', 'success', 'finished', 'ok', 'ready'];
    var FAILURE_STATES = ['error', 'failed', 'failure', 'cancelled', 'canceled', 'aborted'];

    function strings() {
        try {
            var el = document.getElementById('dlux-strings-data');
            return (el && JSON.parse(el.textContent)) || {};
        } catch (e) {
            return {};
        }
    }

    function str(key, fallback) {
        var value = strings()[key];
        return (typeof value === 'string' && value) ? value : fallback;
    }

    function data(el, name) {
        // name is the camelCase dataset key, e.g. 'loadingLabel'
        var value = el.dataset[name];
        return (value === undefined || value === '') ? null : value;
    }

    function toInt(value, fallback) {
        var n = parseInt(value, 10);
        return isNaN(n) ? fallback : n;
    }

    function dispatch(button, name, detail) {
        button.dispatchEvent(new CustomEvent(name, { bubbles: true, cancelable: false, detail: detail || {} }));
    }

    function getCookie(name) {
        if (!document.cookie) return null;
        var parts = document.cookie.split(';');
        for (var i = 0; i < parts.length; i++) {
            var c = parts[i].trim();
            if (c.indexOf(name + '=') === 0) {
                return decodeURIComponent(c.substring(name.length + 1));
            }
        }
        return null;
    }

    function csrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        if (meta && meta.content) return meta.content;
        var input = document.querySelector('[name=csrfmiddlewaretoken]');
        if (input && input.value) return input.value;
        return getCookie('csrftoken');
    }

    function spinnerHTML() {
        return '<span class="spinner-border spinner-border-sm dlux-btn__spinner" role="status" aria-hidden="true"></span>';
    }

    function escapeHTML(text) {
        var div = document.createElement('div');
        div.textContent = text == null ? '' : String(text);
        return div.innerHTML;
    }

    function makeSpinnerEl(extraClasses) {
        var s = document.createElement('span');
        s.className = 'spinner-border spinner-border-sm dlux-btn__spinner' + (extraClasses ? ' ' + extraClasses : '');
        s.setAttribute('role', 'status');
        s.setAttribute('aria-hidden', 'true');
        return s;
    }

    // Render the busy state.
    //  - content-replace (a label is provided / streaming polling): swap the
    //    whole content for `spinner + label`. Used when the text changes.
    //  - in-place (no label, e.g. a submit button): PRESERVE the button's
    //    existing layout — turn its leading icon into the spinner (keeping that
    //    icon's position and margin classes) and leave the text untouched, or
    //    just prepend a small spinner if there is no icon. This keeps dlux's
    //    icon-beside-text button design intact while loading.
    function applyBusy(button, opts) {
        if (opts.label != null) {
            var html = spinnerHTML();
            html += '<span class="dlux-btn__label">' + escapeHTML(opts.label) + '</span>';
            button.innerHTML = html;
            return;
        }
        var icon = button.querySelector('i, svg');
        if (icon) {
            var kept = (icon.getAttribute('class') || '').split(/\s+/).filter(function (c) {
                return c && c !== 'bi' && c.indexOf('bi-') !== 0;
            });
            icon.parentNode.replaceChild(makeSpinnerEl(kept.join(' ')), icon);
        } else {
            button.insertBefore(makeSpinnerEl('me-1'), button.firstChild);
        }
    }

    // -- Low-level handle --------------------------------------------------

    function start(button, opts) {
        opts = opts || {};
        if (button.__dluxLoading) return button.__dluxLoading.handle;

        var state = {
            originalHTML: button.innerHTML,
            originalText: (button.textContent || '').trim(),
            originalDisabled: !!button.disabled,
            startedAt: Date.now(),
            minMs: toInt(opts.min != null ? opts.min : data(button, 'loadingMin'), 0),
            finished: false,
        };
        button.__dluxLoading = state;

        if ('disabled' in button) button.disabled = true;
        button.setAttribute('aria-disabled', 'true');
        button.setAttribute('aria-busy', 'true');
        button.classList.add('dlux-btn--loading');

        // An explicit label (opts.label or data-dlux-loading-label) means
        // content-replace; without one we preserve the button's layout in place.
        var explicitLabel = opts.label != null ? opts.label : data(button, 'loadingLabel');
        state.inPlace = (explicitLabel == null);
        applyBusy(button, { label: explicitLabel });
        if (state.inPlace && !state.originalText && !button.getAttribute('aria-label')) {
            // Icon-only / empty control with no existing name: give assistive
            // tech something to read while busy (removed again on restore).
            button.setAttribute('aria-label', str('loading', 'Loading…'));
            state.setAriaLabel = true;
        }

        dispatch(button, 'dlux:loading:start', {});

        function restore() {
            if (!button.__dluxLoading) return;
            button.innerHTML = state.originalHTML;
            if ('disabled' in button) button.disabled = state.originalDisabled;
            button.removeAttribute('aria-busy');
            button.removeAttribute('aria-disabled');
            if (state.setAriaLabel) button.removeAttribute('aria-label');
            button.classList.remove('dlux-btn--loading');
            delete button.__dluxLoading;
        }

        function afterMin(fn) {
            var elapsed = Date.now() - state.startedAt;
            if (elapsed >= state.minMs) { fn(); return; }
            window.setTimeout(fn, state.minMs - elapsed);
        }

        var handle = {
            button: button,

            update: function (message, progress) {
                if (state.finished) return handle;
                // Only re-render text in content-replace mode; in-place (layout-
                // preserving) buttons keep their own markup.
                if (message != null && !state.inPlace) applyBusy(button, { label: message });
                if (progress != null) button.setAttribute('aria-valuenow', String(progress));
                dispatch(button, 'dlux:loading:poll', { message: message, progress: progress });
                return handle;
            },

            done: function (payload) {
                if (state.finished) return handle;
                state.finished = true;
                payload = payload || {};
                var redirect = payload.redirect || data(button, 'loadingRedirect');
                afterMin(function () {
                    var doneLabel = payload.label != null ? payload.label : data(button, 'loadingDoneLabel');
                    var doneIcon = data(button, 'loadingDoneIcon');
                    if (redirect) {
                        // Keep the spinner up; the navigation replaces the page.
                        window.location.href = redirect;
                        return;
                    }
                    if (doneLabel || doneIcon) {
                        var html = doneIcon ? '<i class="' + doneIcon + '"></i>' : '';
                        if (doneLabel) html += '<span class="dlux-btn__label">' + escapeHTML(doneLabel) + '</span>';
                        button.innerHTML = html;
                        button.classList.remove('dlux-btn--loading');
                        button.classList.add('dlux-btn--done');
                        window.setTimeout(restore, toInt(data(button, 'loadingDoneMs'), 1200));
                    } else {
                        restore();
                    }
                    dispatch(button, 'dlux:loading:done', payload);
                });
                return handle;
            },

            error: function (message) {
                if (state.finished) return handle;
                state.finished = true;
                afterMin(function () {
                    restore();
                    button.classList.add('dlux-btn--error');
                    window.setTimeout(function () { button.classList.remove('dlux-btn--error'); }, 1500);
                    if (message) button.title = message;
                    dispatch(button, 'dlux:loading:error', { message: message });
                });
                return handle;
            },

            // Immediate, no min-duration, no done/error event — just put the
            // control back (e.g. caller is taking over rendering).
            stop: restore,
        };

        state.handle = handle;
        return handle;
    }

    function run(button, fn, opts) {
        var handle = start(button, opts);
        Promise.resolve()
            .then(function () { return fn(handle); })
            .then(function (result) {
                if (button.__dluxLoading) handle.done(result && typeof result === 'object' ? result : {});
            })
            .catch(function (err) {
                if (button.__dluxLoading) handle.error(err && err.message ? err.message : str('loading_failed', null));
            });
        return handle;
    }

    // -- Declarative task-polling -----------------------------------------

    function sleep(ms) {
        return new Promise(function (resolve) { window.setTimeout(resolve, ms); });
    }

    async function runPoll(button) {
        var startUrl = data(button, 'loadingStart');
        var pollUrl = data(button, 'loadingPoll');
        var interval = toInt(data(button, 'loadingInterval'), 1500);
        var timeoutMs = toInt(data(button, 'loadingTimeout'), 5 * 60 * 1000);
        // Polling streams status text, so use content-replace mode with a
        // starting label (explicit data-dlux-loading-label, else the button's
        // own text) that update() then swaps for live status messages.
        var handle = start(button, {
            label: data(button, 'loadingLabel') || (button.textContent || '').trim() || str('loading', 'Loading…'),
        });

        try {
            if (startUrl) {
                var startRes = await fetch(startUrl, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': csrfToken() || '', 'X-Requested-With': 'XMLHttpRequest' },
                    credentials: 'same-origin',
                });
                if (!startRes.ok) throw new Error('HTTP ' + startRes.status);
                var startData = await startRes.json().catch(function () { return {}; });
                if (startData && startData.poll) pollUrl = startData.poll;
                if (startData && startData.redirect && isTerminalSuccess(startData.status)) {
                    handle.done(startData); return;
                }
            }
            if (!pollUrl) { handle.done({}); return; }

            var deadline = Date.now() + timeoutMs;
            while (true) {
                if (Date.now() > deadline) throw new Error(str('loading_timeout', 'Timed out'));
                await sleep(interval);
                var res = await fetch(pollUrl, {
                    headers: { 'X-Requested-With': 'XMLHttpRequest' },
                    credentials: 'same-origin',
                });
                if (!res.ok) throw new Error('HTTP ' + res.status);
                var d = await res.json();
                var status = String(d.status || '').toLowerCase();
                handle.update(d.message != null ? d.message : null, d.progress);
                if (isTerminalSuccess(status)) { handle.done(d); return; }
                if (FAILURE_STATES.indexOf(status) !== -1) { handle.error(d.error || d.message); return; }
            }
        } catch (err) {
            handle.error(err && err.message ? err.message : str('loading_failed', null));
        }
    }

    function isTerminalSuccess(status) {
        return SUCCESS_STATES.indexOf(String(status || '').toLowerCase()) !== -1;
    }

    // -- Delegated declarative wiring -------------------------------------

    function init() {
        if (window.__dluxLoadingButtonInit) return;
        window.__dluxLoadingButtonInit = true;

        // Polling + custom-event buttons trigger on click.
        document.addEventListener('click', function (e) {
            var pollBtn = e.target.closest('[data-dlux-loading][data-dlux-loading-poll], [data-dlux-loading][data-dlux-loading-start]');
            if (pollBtn) {
                e.preventDefault();
                if (pollBtn.__dluxLoading) return;
                runPoll(pollBtn);
                return;
            }
            var eventBtn = e.target.closest('[data-dlux-loading][data-dlux-loading-event]');
            if (eventBtn) {
                if (eventBtn.__dluxLoading) { e.preventDefault(); return; }
                var handle = start(eventBtn, {});
                dispatch(eventBtn, eventBtn.dataset.dluxLoadingEvent, { handle: handle });
            }
        });

        // Submit buttons (no poll/event) show the spinner while the form posts.
        // Defer the busy state to a macrotask so the submitter's name/value is
        // still serialized (mirrors prevent_double_submit's deferral).
        document.addEventListener('submit', function (e) {
            var form = e.target;
            if (!form || form.nodeName !== 'FORM') return;
            // Don't spin when the browser will block submission for HTML5
            // validation — the page isn't going anywhere.
            if (typeof form.checkValidity === 'function' && !form.checkValidity()) return;
            var btn = e.submitter || form.querySelector('button[type="submit"][data-dlux-loading], input[type="submit"][data-dlux-loading]');
            if (!btn || !btn.hasAttribute || !btn.hasAttribute('data-dlux-loading')) return;
            if (btn.hasAttribute('data-dlux-loading-poll') || btn.hasAttribute('data-dlux-loading-event')) return;
            if (btn.__dluxLoading) return;
            window.setTimeout(function () { start(btn, { keepText: true }); }, 0);
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    window.DluxLoadingButton = {
        start: start,
        run: run,
        poll: runPoll,
        isBusy: function (button) { return !!(button && button.__dluxLoading); },
    };
})();
