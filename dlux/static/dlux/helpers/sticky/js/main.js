/*
 * Assisted data entry — sticky forms (`sticky_forms`).
 *
 * A blank add-form is refilled from the last record the user created. It changes
 * a form nobody touched, so it is off by default and every capable form renders
 * the inline assist bar with its switch (the Options page carries the same one).
 * Its sibling feature, fill-from-related, is a separate module:
 * helpers/autofill/js/main.js. Each reads its own key from window.USER_PREFS;
 * neither can turn the other on.
 *
 * Forms that were prefilled server-side mark themselves `data-sticky-server`;
 * the client must not fill those again, and toggling the switch reloads instead.
 */
(function () {
    'use strict';

    const STORAGE_PREFIX = 'dlux_autofill_';
    const PREF_STICKY = 'sticky_forms';
    const SUBMIT_FLAG = 'dlux_last_submit_autofill';

    function pref(key, fallback) {
        const prefs = window.USER_PREFS;
        if (!prefs || !Object.prototype.hasOwnProperty.call(prefs, key)) {
            return fallback;
        }
        return Boolean(prefs[key]);
    }

    function t(key, fallback) {
        const strings = window.DLUX_STRINGS || {};
        return strings[key] || fallback;
    }

    async function fetchModelDetails(app, model, pk) {
        let url = `/sys/api/details/${app}/${model}/${pk}/`;
        if (window.dluxEndpoint) {
            url = window.dluxEndpoint('modelDetails', { app: app, model: model, pk: pk }, url);
        } else if (window.dluxUrl) {
            url = window.dluxUrl(url);
        }
        const response = await fetch(url);
        if (!response.ok) throw new Error(`API Error ${response.status}: ${response.statusText}`);
        return response.json();
    }

    function populateForm(form, data) {
        if (!data) {
            return;
        }
        Object.entries(data).forEach(([key, value]) => {
            if (key.startsWith('_')) {
                return;
            }
            const input = form.querySelector(`[name="${key}"]`);
            if (!input) {
                return;
            }
            if (input.type === 'checkbox') {
                input.checked = Boolean(value);
            } else if (input.type !== 'radio') {
                input.value = value;
            }
        });
    }

    function formCapabilities(form) {
        return {
            related: Boolean(form.querySelector('[data-autofill-source]')),
            sticky: Boolean(form.dataset.modelName && form.dataset.appLabel),
        };
    }

    function expose(api) {
        window.dluxAssistedEntry = Object.assign(window.dluxAssistedEntry || {}, api);
    }

    function stickyEnabled() {
        return pref(PREF_STICKY, false);
    }

    function setPref(key, value) {
        if (window.USER_PREFS) {
            window.USER_PREFS[key] = value;
        }
        if (typeof window.updatePreferences !== 'function') {
            return Promise.resolve();
        }
        return Promise.resolve(window.updatePreferences({ [key]: value }));
    }

    function assistableForms(root) {
        const scope = root && root.querySelectorAll ? root : document;
        return Array.from(scope.querySelectorAll('form')).filter((form) => formCapabilities(form).sticky);
    }

    // ── inline control ──────────────────────────────────────────────────────
    // A thin bar at the top of the form. The switch is the same control the
    // System Settings steps use (build_settings_toggle_field in forms.py) —
    // helpers/toggle/css/main.css and the themes style it by those exact class names, so
    // it must not be hand-rolled from `form-check form-switch`.
    function buildSwitch(prefKey, label, checked) {
        const control = document.createElement('div');
        control.className = 'dlux-settings-toggle-field__control form-switch';
        const input = document.createElement('input');
        input.className = 'form-check-input dlux-settings-toggle-field__input';
        input.type = 'checkbox';
        input.id = `id_dlux_assist_${prefKey}`;
        input.name = `dlux_assist_${prefKey}`;
        input.setAttribute('aria-label', label);
        input.setAttribute('data-dlux-assist-pref', prefKey);
        input.checked = Boolean(checked);
        control.appendChild(input);
        return control;
    }

    function renderControl(form) {
        if (form.querySelector('[data-dlux-assist-bar]') || !formCapabilities(form).sticky) {
            return;
        }
        const bar = document.createElement('div');
        bar.className = 'dlux-assist-bar';
        bar.setAttribute('data-dlux-assist-bar', '');

        const legend = document.createElement('span');
        legend.className = 'dlux-assist-bar__legend';
        legend.innerHTML = '<i class="bi bi-magic" aria-hidden="true"></i>';
        legend.append(` ${t('assist_bar_legend', 'Assisted entry')}`);
        bar.appendChild(legend);

        const label = t('assist_sticky_label', 'Reuse my last entry');
        const labelEl = document.createElement('span');
        labelEl.className = 'dlux-assist-bar__label';
        labelEl.textContent = label;
        labelEl.setAttribute('data-dlux-tooltip',
            t('assist_sticky_desc', 'A new form starts pre-filled with the last record you created.'));
        bar.appendChild(labelEl);
        bar.appendChild(buildSwitch(PREF_STICKY, label, stickyEnabled()));

        form.insertBefore(bar, form.firstChild);
    }

    function setAssistPreference(key, enabled, origin) {
        const saved = setPref(key, enabled);
        document.querySelectorAll(`[data-dlux-assist-pref="${key}"]`).forEach((input) => {
            input.checked = enabled;
        });
        const form = key === PREF_STICKY && origin && origin.closest ? origin.closest('form') : null;
        if (!form) {
            return;
        }
        if (form.dataset.stickyServer !== undefined) {
            // The project prefilled this form server-side, before it rendered;
            // only a reload can apply or undo that — and the reload has to wait
            // for the preference to be stored, or it races its own POST and the
            // page comes back showing the value we just left.
            forgetSticky(form);
            const reload = () => window.location.reload();
            saved.then(reload, reload);
            return;
        }
        if (enabled) {
            applySticky(form);
        } else {
            forgetSticky(form);
        }
    }

    // ── sticky forms ────────────────────────────────────────────────────────
    function initStickyForm(form) {
        if (form.dataset.dluxStickyBound === 'true') {
            return;
        }
        form.dataset.dluxStickyBound = 'true';

        form.addEventListener('submit', function () {
            if (stickyEnabled()) {
                sessionStorage.setItem(SUBMIT_FLAG, 'true');
            } else {
                sessionStorage.removeItem(SUBMIT_FLAG);
            }
        });

        if (stickyEnabled() && form.dataset.stickyServer === undefined) {
            applySticky(form);
        }
    }

    async function applySticky(form) {
        const appLabel = form.dataset.appLabel;
        const modelName = form.dataset.modelName;
        const storageKey = `${STORAGE_PREFIX}${appLabel}_${modelName}`;

        // "Save and add another" hands over via sessionStorage: refill from the
        // record just created rather than whatever was remembered before.
        if (sessionStorage.getItem(SUBMIT_FLAG) === 'true') {
            sessionStorage.removeItem(SUBMIT_FLAG);
            try {
                const lastEntry = await fetchLastEntry(appLabel, modelName);
                if (lastEntry && lastEntry._pk) {
                    localStorage.setItem(storageKey, lastEntry._pk);
                    populateForm(form, lastEntry);
                }
            } catch (err) {
                console.error('Assisted entry: could not read the last entry', err);
            }
            return;
        }

        const targetId = localStorage.getItem(storageKey);
        if (!targetId) {
            return;
        }
        try {
            populateForm(form, await fetchModelDetails(appLabel, modelName, targetId));
        } catch (err) {
            localStorage.removeItem(storageKey);
        }
    }

    function forgetSticky(form) {
        const { appLabel, modelName } = form.dataset;
        if (appLabel && modelName) {
            localStorage.removeItem(`${STORAGE_PREFIX}${appLabel}_${modelName}`);
        }
        sessionStorage.removeItem(SUBMIT_FLAG);
    }

    async function fetchLastEntry(app, model) {
        const path = `/sys/api/last-entry/${app}/${model}/`;
        const url = window.dluxEndpoint
            ? window.dluxEndpoint('lastEntry', { app: app, model: model }, path)
            : (window.dluxUrl ? window.dluxUrl(path) : path);
        const response = await fetch(url);
        if (!response.ok) throw new Error(response.statusText);
        return response.json();
    }

    function scan(root) {
        assistableForms(root).forEach((form) => {
            renderControl(form);
            initStickyForm(form);
        });
    }

    function init() {
        scan(document);

        document.addEventListener('change', (event) => {
            const control = event.target && event.target.closest
                ? event.target.closest('[data-dlux-assist-pref]')
                : null;
            if (!control) {
                return;
            }
            setAssistPreference(control.getAttribute('data-dlux-assist-pref'),
                Boolean(control.checked), control);
        });

        // Dynamic-modal forms are injected after load and dispatch no lifecycle
        // event, so they are picked up the same way the setup wizard does it.
        new MutationObserver((mutations) => {
            for (const mutation of mutations) {
                for (const node of mutation.addedNodes) {
                    if (node.nodeType === 1 && (node.matches?.('form') || node.querySelector?.('form'))) {
                        scan(node);
                        return;
                    }
                }
            }
        }).observe(document.documentElement, { childList: true, subtree: true });
    }

    expose({
        scan: scan,
        capabilities: formCapabilities,
        stickyEnabled: stickyEnabled,
    });

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
