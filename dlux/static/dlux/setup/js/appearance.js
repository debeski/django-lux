/* Setup wizard: theme and font pickers.
 *
 * Split out of setup/js/main.js. Both are self-contained — neither calls another
 * top-level function nor reads a closure constant — which is why this cluster
 * went first: it proves the module pattern without needing a shared dom.js.
 *
 * The two density pickers that would otherwise belong here stayed behind. Their
 * markup only exists under `picker_mode == 'setup'`, and every include in dlux
 * passes 'options', so they are unreachable and therefore unverifiable across a
 * move. See tests-e2e/wizard_appearance.test.mjs.
 *
 * Namespace pattern matches helpers/icon_picker and setup/js/builder_model.js:
 * loaded before main.js, which destructures it.
 */
(function (root) {
    'use strict';

    function initSetupThemePicker(root) {
        root.querySelectorAll('[data-setup-theme-picker]').forEach((picker) => {
            if (picker.dataset.bound === 'true') return;
            picker.dataset.bound = 'true';

            const inputId = picker.getAttribute('data-theme-input');
            const input = inputId ? document.getElementById(inputId) : null;
            if (!input) return;

            const options = Array.from(picker.querySelectorAll('[data-setup-theme-choice]'));
            const allowToggleContainers = Array.from(picker.querySelectorAll('[data-setup-theme-allow-toggle]'));
            const allowedCheckboxes = Array.from(picker.querySelectorAll('[data-setup-theme-allowed]'));

            function getAllowedThemes() {
                return allowedCheckboxes
                    .filter((checkbox) => checkbox.checked)
                    .map((checkbox) => checkbox.getAttribute('data-setup-theme-allowed'));
            }

            function syncActive() {
                const allowedThemes = getAllowedThemes();
                if (!allowedThemes.length && allowedCheckboxes.length) {
                    allowedCheckboxes[0].checked = true;
                }
                const resolvedAllowedThemes = getAllowedThemes();
                const activeTheme = resolvedAllowedThemes.includes(input.value) ? input.value : (resolvedAllowedThemes[0] || 'light');
                input.value = activeTheme;
                allowedCheckboxes.forEach((checkbox) => {
                    const theme = checkbox.getAttribute('data-setup-theme-allowed');
                    const isLocked = checkbox.checked && resolvedAllowedThemes.length === 1;
                    checkbox.setAttribute('aria-disabled', isLocked ? 'true' : 'false');
                    const container = checkbox.closest('[data-theme-option]');
                    if (!container) {
                        return;
                    }
                    const isAllowed = resolvedAllowedThemes.includes(theme);
                    const isDefault = theme === activeTheme;
                    container.classList.toggle('is-locked', isLocked);
                    container.classList.toggle('opacity-50', !isAllowed);
                    container.classList.toggle('is-default', isDefault);
                    const button = container.matches('[data-setup-theme-choice]')
                        ? container
                        : container.querySelector('[data-setup-theme-choice]');
                    const preview = container.querySelector('.theme-preview[data-theme]');
                    if (button) {
                        button.setAttribute('aria-pressed', isDefault ? 'true' : 'false');
                    }
                    if (preview) {
                        preview.classList.toggle('active', isDefault);
                    }
                });
            }

            function previewTheme(theme) {
                if (!window.setTheme) {
                    return;
                }
                const option = options.find((candidate) => candidate.getAttribute('data-setup-theme-choice') === theme);
                window.setTheme(theme, {
                    preview: true,
                    cssUrl: option ? option.getAttribute('data-setup-theme-preview-url') || '' : '',
                });
            }

            function isThemeAllowControlTarget(target) {
                return Boolean(
                    target &&
                    target.closest &&
                    target.closest('[data-setup-theme-allowed], [data-setup-theme-allowed-control]')
                );
            }

            function isThemeDefaultControlTarget(target) {
                return Boolean(
                    target &&
                    target.closest &&
                    target.closest('[data-setup-theme-choice]')
                );
            }

            function setDefaultThemeFromOption(option) {
                const theme = option.getAttribute('data-setup-theme-choice') || 'light';
                const checkbox = picker.querySelector(`[data-setup-theme-allowed="${theme}"]`);
                if (checkbox && !checkbox.checked) {
                    checkbox.checked = true;
                    checkbox.dispatchEvent(new Event('change', { bubbles: true }));
                }
                input.value = theme;
                input.dispatchEvent(new Event('change', { bubbles: true }));
                syncActive();
                previewTheme(theme);
            }

            function toggleAllowedThemeFromContainer(container) {
                const theme = container.getAttribute('data-setup-theme-allow-toggle') || '';
                if (!theme) return;
                const checkbox = picker.querySelector(`[data-setup-theme-allowed="${theme}"]`);
                if (!checkbox) return;
                if (checkbox.checked && getAllowedThemes().length === 1) {
                    return;
                }
                const previousTheme = input.value;
                checkbox.checked = !checkbox.checked;
                checkbox.dispatchEvent(new Event('change', { bubbles: true }));
                if (previousTheme !== input.value) {
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                    previewTheme(input.value);
                }
            }

            options.forEach((option) => {
                option.addEventListener('click', (event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    setDefaultThemeFromOption(option);
                });
                option.addEventListener('keydown', (event) => {
                    if (!['Enter', ' '].includes(event.key)) {
                        return;
                    }
                    event.preventDefault();
                    event.stopPropagation();
                    option.click();
                });
            });

            allowToggleContainers.forEach((container) => {
                container.addEventListener('click', (event) => {
                    if (isThemeAllowControlTarget(event.target) || isThemeDefaultControlTarget(event.target)) {
                        return;
                    }
                    event.preventDefault();
                    toggleAllowedThemeFromContainer(container);
                });
            });

            allowedCheckboxes.forEach((checkbox) => {
                checkbox.addEventListener('click', (event) => {
                    event.stopPropagation();
                    if (checkbox.checked && getAllowedThemes().length === 1) {
                        event.preventDefault();
                    }
                });
                checkbox.addEventListener('change', () => {
                    const previousTheme = input.value;
                    if (!getAllowedThemes().length) {
                        checkbox.checked = true;
                    }
                    syncActive();
                    if (previousTheme !== input.value) {
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                        previewTheme(input.value);
                    }
                });
            });

            syncActive();
        });
    }

    function initSetupFontPicker(root) {
        root.querySelectorAll('[data-setup-font-picker]').forEach((picker) => {
            if (picker.dataset.bound === 'true') return;
            picker.dataset.bound = 'true';

            const allowedCheckboxes = Array.from(picker.querySelectorAll('[data-setup-font-allowed]'));

            allowedCheckboxes.forEach((checkbox) => {
                checkbox.addEventListener('change', () => {
                    const container = checkbox.closest('[data-font-option]');
                    if (container) {
                        container.classList.toggle('opacity-50', !checkbox.checked);
                    }
                });
                // Initial state
                const container = checkbox.closest('[data-font-option]');
                if (container) {
                    container.classList.toggle('opacity-50', !checkbox.checked);
                }
            });
        });
    }

    root.DluxSetup = Object.assign(root.DluxSetup || {}, {
        initSetupThemePicker,
        initSetupFontPicker
    });
})(typeof window !== 'undefined' ? window : globalThis);
