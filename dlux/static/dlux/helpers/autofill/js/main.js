/*
 * Assisted data entry — fill from related record (`autofill_from_related`).
 *
 * Choosing a ForeignKey fills the form's matching-named fields from that related
 * record. It reacts only to a deliberate selection, so it is on by default and
 * needs no per-form control (the Options page carries the switch). Its sibling
 * feature, sticky forms, is a separate module: helpers/sticky/js/main.js. Each
 * reads its own key from window.USER_PREFS; neither can turn the other on.
 */
(function () {
    'use strict';

    const PREF_RELATED = 'autofill_from_related';

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

    function relatedEnabled() {
        return pref(PREF_RELATED, true);
    }

    // ── fill from related record ────────────────────────────────────────────
    async function handleRelatedChange(event) {
        const target = event.target;
        const sourceEl = target && target.closest ? target.closest('[data-autofill-source]') : null;
        if (!sourceEl || !relatedEnabled()) {
            return;
        }
        const source = sourceEl.dataset.autofillSource;
        const form = sourceEl.closest('form');
        if (!source || !form) {
            return;
        }
        const [app, model] = source.split('.');
        const parent = sourceEl.parentElement;

        if (parent) {
            parent.classList.add('opacity-50');
        }
        try {
            // Clearing the FK clears what it filled, so a stale related record's
            // values never survive into a different selection.
            const pk = sourceEl.value || 'empty_schema';
            populateForm(form, await fetchModelDetails(app, model, pk));
        } catch (err) {
            console.error('Assisted entry: could not read the related record', err);
        } finally {
            if (parent) {
                parent.classList.remove('opacity-50');
            }
        }
    }

    function init() {
        document.addEventListener('change', handleRelatedChange);
        document.addEventListener('input', handleRelatedChange);
        if (window.jQuery) {
            window.jQuery(document.body).on('select2:select', function (event) {
                handleRelatedChange(event.originalEvent || event);
            });
        }
    }

    expose({
        capabilities: formCapabilities,
        relatedEnabled: relatedEnabled,
    });

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
