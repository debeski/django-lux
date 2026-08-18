/* Setup wizard: language catalog, system names and the translation matrix.
 *
 * Adding a language is a fan-out — one action must produce a catalog row, a
 * per-language system-name input, and a column in the translation matrix. Miss
 * one and the language exists but cannot be named or translated, with nothing
 * raised anywhere.
 *
 * The entry points (initLanguageCatalogEditor, initSystemNamesEditor,
 * initTranslationMatrixEditor) stay in main.js — they sit inside its
 * mutually-recursive core. These are the helpers they call.
 *
 * Depends on setup/js/dom.js and setup/js/builder_model.js.
 */
(function (root) {
    'use strict';

    const {
        getNamedFieldValue
    } = root.DluxSetupDom;
    const { normalizeLanguageCode } = root.DluxSetupModel;

    function applyTranslationOverridesToMatrix(form, overrides) {
        if (!form || !overrides || typeof overrides !== 'object') return;
        Object.entries(overrides).forEach(([rawLang, values]) => {
            const lang = normalizeLanguageCode(rawLang);
            if (!lang || !values || typeof values !== 'object') return;
            Object.entries(values).forEach(([key, value]) => {
                const input = Array.from(form.querySelectorAll(`[data-translation-input][data-lang="${lang}"]`)).find((candidate) => {
                    return candidate.dataset.key === String(key);
                });
                if (input) {
                    input.value = value || '';
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                }
            });
        });
        syncTranslationOverrides(form);
    }

    function createLanguageRow(code, name, dir, flag) {
        const row = document.createElement('div');
        row.className = 'dlux-language-row';
        row.dataset.languageRow = 'true';
        row.dataset.languageCode = code;
        const locked = code === 'en' || code === 'ar';
        row.innerHTML = `
            <div class="dlux-language-row__code">${code}</div>
            <input type="text" class="form-control glass-input" data-language-name value="${escapeHtml(name || code)}" aria-label="Display name (${escapeHtml(code)})">
            <select class="form-select glass-input" data-language-dir aria-label="Direction (${escapeHtml(code)})">
                <option value="ltr"${dir !== 'rtl' ? ' selected' : ''}>LTR</option>
                <option value="rtl"${dir === 'rtl' ? ' selected' : ''}>RTL</option>
            </select>
            <input type="text" class="form-control glass-input dlux-language-flag-input" data-language-flag value="${escapeHtml(flag || '')}" aria-label="Flag (${escapeHtml(code)})">
            <label class="dlux-language-default">
                <input type="radio" data-language-default value="${code}">
                <span>Default</span>
            </label>
            <button type="button" class="btn btn-sm btn-outline-danger" data-language-remove${locked ? ' disabled' : ''}>
                <i class="bi bi-trash"></i>
            </button>
        `;
        return row;
    }

    function createSystemNameRow(code, label, value) {
        const row = document.createElement('div');
        row.className = 'dlux-system-name-row';
        row.dataset.systemNameRow = 'true';
        row.dataset.languageCode = code;
        row.innerHTML = `
            <div class="dlux-system-name-row__meta">
                <span class="dlux-system-name-row__code">${escapeHtml(code)}</span>
                <span class="dlux-system-name-row__label">${escapeHtml(label || code)}</span>
            </div>
            <input type="text" class="form-control glass-input" data-system-name-input value="${escapeHtml(value || '')}" placeholder="System name">
        `;
        return row;
    }

    function currentSetupLanguageCode(form) {
        return normalizeLanguageCode(getNamedFieldValue(form, 'default_language') || 'en') || 'en';
    }

    function ensureTranslationLanguageColumn(form, code, label) {
        const matrix = form && form.querySelector('[data-translation-matrix]');
        if (!matrix || !code || matrix.querySelector(`[data-translation-lang-header="${code}"]`)) return;
        const headerRow = matrix.querySelector('thead tr');
        if (headerRow) {
            const header = document.createElement('th');
            header.dataset.translationLangHeader = code;
            header.innerHTML = `${label || code} <span class="text-muted">(${code})</span>`;
            headerRow.appendChild(header);
        }
        matrix.querySelectorAll('[data-translation-row]').forEach((row) => {
            const key = row.getAttribute('data-translation-key') || '';
            const cell = document.createElement('td');
            cell.dataset.translationCell = 'true';
            cell.dataset.source = 'missing';
            cell.innerHTML = `
                <textarea class="form-control form-control-sm glass-input" rows="2" data-translation-input data-lang="${code}" data-key="${key}" data-base-value="" data-override-value="" placeholder=""></textarea>
                <span class="badge dlux-translation-source">missing</span>
            `;
            row.appendChild(cell);
            const input = cell.querySelector('[data-translation-input]');
            input.addEventListener('input', () => syncTranslationOverrides(form));
        });
    }

    function escapeHtml(value) {
        return String(value || '').replace(/[&<>"']/g, (char) => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;'
        })[char]);
    }

    function findSystemNameRow(form, code) {
        return Array.from(form.querySelectorAll('[data-system-name-row]')).find((row) => {
            return normalizeLanguageCode(row.dataset.languageCode) === code;
        });
    }

    function getSetupLanguageCount(form) {
        const renderedCount = form.querySelectorAll('[data-language-row]').length
            || form.querySelectorAll('[data-setup-language-choice]').length;
        if (renderedCount) {
            return renderedCount;
        }
        const preservedCount = Number(form.dataset.dluxLanguageCount);
        return Number.isFinite(preservedCount) && preservedCount >= 0 ? preservedCount : 0;
    }

    function initLanguageFontsEditor(root) {
        root.querySelectorAll('#dluxLanguageFontsEditor').forEach((editor) => {
            if (editor.dataset.bound === 'true') return;
            editor.dataset.bound = 'true';

            const hiddenInput = document.getElementById('id_default_fonts');
            if (!hiddenInput) return;

            function updateHiddenInput() {
                const config = {};
                editor.querySelectorAll('.dlux-lang-font-select').forEach((select) => {
                    config[select.getAttribute('data-lang')] = select.value;
                });
                hiddenInput.value = JSON.stringify(config);
                hiddenInput.dispatchEvent(new Event('change', { bubbles: true }));
            }

            editor.querySelectorAll('.dlux-lang-font-select').forEach((select) => {
                select.addEventListener('change', updateHiddenInput);
            });

            // Sync hidden input to selects if it has value
            if (hiddenInput.value) {
                try {
                    const data = JSON.parse(hiddenInput.value);
                    editor.querySelectorAll('.dlux-lang-font-select').forEach((select) => {
                        const lang = select.getAttribute('data-lang');
                        if (data[lang]) {
                            select.value = data[lang];
                        }
                    });
                } catch (e) {}
            }
        });
    }

    function readSystemNames(form) {
        const systemNames = {};
        if (!form) return systemNames;
        form.querySelectorAll('[data-system-name-row]').forEach((row) => {
            const code = normalizeLanguageCode(row.dataset.languageCode);
            const input = row.querySelector('[data-system-name-input]');
            const value = String(input && input.value ? input.value : '').trim();
            if (code && value) {
                systemNames[code] = value;
            }
        });
        return systemNames;
    }

    function removeTranslationLanguageColumn(form, code) {
        const matrix = form && form.querySelector('[data-translation-matrix]');
        if (!matrix || !code) return;
        matrix.querySelectorAll(`[data-translation-lang-header="${code}"], [data-translation-input][data-lang="${code}"]`).forEach((node) => {
            const cell = node.closest('[data-translation-cell]');
            (cell || node).remove();
        });
    }

    function syncTranslationOverrides(form) {
        const field = form && form.querySelector('[name="translations_override"]');
        if (!field) return;
        const overrides = {};
        form.querySelectorAll('[data-translation-input]').forEach((input) => {
            const lang = normalizeLanguageCode(input.dataset.lang);
            const key = String(input.dataset.key || '').trim();
            if (!lang || !key) return;
            const value = String(input.value || '').trim();
            const baseValue = String(input.dataset.baseValue || '').trim();
            if (value && value !== baseValue) {
                if (!overrides[lang]) overrides[lang] = {};
                overrides[lang][key] = value;
            }
        });
        field.value = JSON.stringify(overrides);
    }

    root.DluxSetup = Object.assign(root.DluxSetup || {}, {
        applyTranslationOverridesToMatrix,
        createLanguageRow,
        createSystemNameRow,
        currentSetupLanguageCode,
        ensureTranslationLanguageColumn,
        escapeHtml,
        findSystemNameRow,
        getSetupLanguageCount,
        initLanguageFontsEditor,
        readSystemNames,
        removeTranslationLanguageColumn,
        syncTranslationOverrides
    });
})(typeof window !== 'undefined' ? window : globalThis);
