(function () {
    'use strict';

    const OPTIONS_ORDER_STORAGE_KEY = 'dlux.options.card-order.v1';

    function onReady(callback) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', callback);
            return;
        }
        callback();
    }

    function getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) {
            return parts.pop().split(';').shift();
        }
        return null;
    }

    function getCsrfToken() {
        return document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
    }

    function setCookie(name, value) {
        const expires = new Date();
        expires.setTime(expires.getTime() + (365 * 24 * 60 * 60 * 1000));
        document.cookie = `${name}=${value};expires=${expires.toUTCString()};path=/`;
    }

    function updateActiveOption(options, attribute, activeValue) {
        options.forEach((option) => {
            option.classList.toggle('is-active', option.getAttribute(attribute) === activeValue);
        });
    }

    function getActiveOptionValue(options, attribute, fallback) {
        return options.find((option) => option.classList.contains('is-active'))?.getAttribute(attribute) || fallback;
    }

    function initAutofill() {
        const toggle = document.getElementById('autofillToggle');
        if (!toggle) {
            return;
        }

        const cookieValue = getCookie('enable_prefill');
        const storedValue = localStorage.getItem('enable_prefill');
        const resolvedValue = cookieValue ?? storedValue ?? 'true';
        toggle.checked = resolvedValue === 'true';

        toggle.addEventListener('change', () => {
            const isEnabled = Boolean(toggle.checked);
            setCookie('enable_prefill', isEnabled);
            localStorage.setItem('enable_prefill', String(isEnabled));

            if (typeof window.showToast === 'function') {
                window.showToast(isEnabled ? toggle.dataset.enabledMessage : toggle.dataset.disabledMessage);
            }
        });
    }

    function initThemePicker() {
        document.querySelectorAll('[data-theme]').forEach((element) => {
            element.addEventListener('click', function () {
                const theme = this.getAttribute('data-theme');
                if (window.setTheme) {
                    window.setTheme(theme);
                }
                if (window.updatePreferences) {
                    window.updatePreferences({ theme });
                }
            });
        });
    }

    function initLandingPageControl() {
        const group = document.querySelector('[data-user-home-url-group]');
        if (!group) {
            return;
        }
        // Entry selector (radio group): selecting an entry saves immediately,
        // like the theme picker — no separate Save button.
        group.addEventListener('change', function (event) {
            const radio = event.target.closest('input[name="user_home_url"]');
            if (!radio || !radio.checked) {
                return;
            }
            const value = (radio.value || '').trim();
            if (window.updatePreferences) {
                window.updatePreferences({ user_home_url: value });
            }
            if (window.showToast) {
                window.showToast(group.dataset.savedMessage || 'Saved');
            }
        });
    }

    function initAccessibilityToggles() {
        document.querySelectorAll('.accessibility-switch').forEach((element) => {
            element.addEventListener('change', function () {
                const mode = this.getAttribute('data-accessibility');
                if (window.setAccessibilityMode) {
                    window.setAccessibilityMode(mode);
                }
            });
        });
    }

    function initLanguagePicker() {
        document.querySelectorAll('[data-lang]').forEach((element) => {
            element.addEventListener('click', function () {
                const lang = this.getAttribute('data-lang');
                if (window.setLanguage) {
                    window.setLanguage(lang);
                }
            });
        });
    }

    function initFontPicker() {
        document.querySelectorAll('[data-font]').forEach((element) => {
            element.addEventListener('click', function () {
                const font = this.getAttribute('data-font');
                // Update local UI
                document.querySelectorAll('[data-font]').forEach((option) => {
                    option.classList.toggle('is-active', option === this);
                });
                
                // Apply immediately
                const familyName = window.DLUX_FONT_FAMILIES && window.DLUX_FONT_FAMILIES[font];
                if (familyName) {
                    document.documentElement.style.setProperty('--dlux-main-font', `'${familyName}', sans-serif`);
                }
                
                // Update preferences on server
                if (window.updatePreferences) {
                    window.updatePreferences({ font });
                }
            });
        });
    }

    function initDensityPickers() {
        const densityPicker = document.querySelector('.dlux-table-density-picker:not([data-setup-table-density-picker]):not(.dlux-sidebar-density-picker)');
        const densityOptions = densityPicker
            ? Array.from(densityPicker.querySelectorAll('.dlux-density-option[data-table-density]'))
            : [];
        const sidebarDensityPicker = document.querySelector('.dlux-sidebar-density-picker');
        const sidebarDensityOptions = sidebarDensityPicker
            ? Array.from(sidebarDensityPicker.querySelectorAll('.dlux-density-option[data-sidebar-density]'))
            : [];

        if (densityOptions.length) {
            const currentDensity = (window.USER_PREFS && window.USER_PREFS.table_density)
                || getActiveOptionValue(densityOptions, 'data-table-density', 'balanced');
            updateActiveOption(densityOptions, 'data-table-density', currentDensity);

            densityOptions.forEach((option) => {
                option.addEventListener('click', function () {
                    const density = this.getAttribute('data-table-density') || 'balanced';
                    updateActiveOption(densityOptions, 'data-table-density', density);
                    if (window.USER_PREFS) {
                        window.USER_PREFS.table_density = density;
                    }
                    if (window.updatePreferences) {
                        window.updatePreferences({ table_density: density });
                    }
                });
            });
        }

        if (sidebarDensityOptions.length) {
            const currentSidebarDensity = (window.USER_PREFS && window.USER_PREFS.sidebar_density)
                || getActiveOptionValue(sidebarDensityOptions, 'data-sidebar-density', 'balanced');
            updateActiveOption(sidebarDensityOptions, 'data-sidebar-density', currentSidebarDensity);

            sidebarDensityOptions.forEach((option) => {
                option.addEventListener('click', function () {
                    const density = this.getAttribute('data-sidebar-density') || 'balanced';
                    updateActiveOption(sidebarDensityOptions, 'data-sidebar-density', density);
                    if (window.USER_PREFS) {
                        window.USER_PREFS.sidebar_density = density;
                    }
                    const sidebar = document.getElementById('sidebar');
                    if (sidebar) {
                        sidebar.setAttribute('data-sidebar-density', density);
                    }
                    if (window.updatePreferences) {
                        window.updatePreferences({ sidebar_density: density });
                    }
                });
            });
        }
    }

    function initBodyAttrPicker(pickerSelector, optionAttr, bodyDataKey, prefKey, fallback) {
        const picker = document.querySelector(pickerSelector);
        const options = picker ? Array.from(picker.querySelectorAll('.dlux-density-option[' + optionAttr + ']')) : [];
        if (!options.length) {
            return;
        }
        const current = (window.USER_PREFS && window.USER_PREFS[prefKey])
            || getActiveOptionValue(options, optionAttr, fallback);
        updateActiveOption(options, optionAttr, current);
        document.body.dataset[bodyDataKey] = current;
        options.forEach((option) => {
            option.addEventListener('click', function () {
                const value = this.getAttribute(optionAttr) || fallback;
                updateActiveOption(options, optionAttr, value);
                document.body.dataset[bodyDataKey] = value;
                if (window.USER_PREFS) {
                    window.USER_PREFS[prefKey] = value;
                }
                if (window.updatePreferences) {
                    window.updatePreferences({ [prefKey]: value });
                }
            });
        });
    }

    function initFormDensityPicker() {
        initBodyAttrPicker('.dlux-form-density-picker', 'data-form-density', 'dluxFormDensity', 'form_density', 'balanced');
    }

    function initModalSizePicker() {
        initBodyAttrPicker('.dlux-modal-size-picker', 'data-modal-size', 'dluxModalSize', 'modal_size', 'standard');
    }

    function initNavbarModePicker() {
        const picker = document.querySelector('[data-navbar-mode-picker]');
        const options = picker ? Array.from(picker.querySelectorAll('[data-navbar-mode]')) : [];
        if (!options.length) {
            return;
        }
        const currentMode = (window.USER_PREFS && window.USER_PREFS.navbar_mode)
            || getActiveOptionValue(options, 'data-navbar-mode', 'hierarchy');
        updateActiveOption(options, 'data-navbar-mode', currentMode);
        options.forEach((option) => {
            option.addEventListener('click', () => {
                const navbarMode = option.getAttribute('data-navbar-mode') === 'history' ? 'history' : 'hierarchy';
                updateActiveOption(options, 'data-navbar-mode', navbarMode);
                if (window.USER_PREFS) {
                    window.USER_PREFS.navbar_mode = navbarMode;
                }
                if (window.setNavbarMode) {
                    window.setNavbarMode(navbarMode);
                }
                if (window.updatePreferences) {
                    window.updatePreferences({ navbar_mode: navbarMode });
                }
            });
        });
    }

    function clearPreferenceStorage(storageKey) {
        const keysToRemove = [];
        for (let index = 0; index < localStorage.length; index += 1) {
            const key = localStorage.key(index);
            if (!key) {
                continue;
            }
            if (
                key.startsWith('sidebar_')
                || key === 'appTheme'
                || key === 'appLanguage'
                || key === 'appFont'
                || key === 'accessibilityMode'
                || key === 'enable_prefill'
                || key === storageKey
            ) {
                keysToRemove.push(key);
            }
        }
        keysToRemove.forEach((key) => localStorage.removeItem(key));
    }

    function initResetDefaults(grid) {
        const panel = document.querySelector('.dlux-options-panel--danger[data-reset-url]');
        const btnInit = document.getElementById('btnResetInit');
        const actions = document.getElementById('resetActions');
        const btnConfirm = document.getElementById('btnResetConfirm');
        const btnCancel = document.getElementById('btnResetCancel');

        if (!panel || !btnInit || !actions || !btnConfirm || !btnCancel) {
            return;
        }

        const storageKey = grid?.dataset.optionsOrderStorageKey || OPTIONS_ORDER_STORAGE_KEY;

        btnInit.addEventListener('click', () => {
            btnInit.hidden = true;
            actions.hidden = false;
        });

        btnCancel.addEventListener('click', () => {
            actions.hidden = true;
            btnInit.hidden = false;
        });

        btnConfirm.addEventListener('click', async function () {
            const originalContent = this.innerHTML;
            this.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>';
            this.disabled = true;
            btnCancel.disabled = true;

            try {
                const response = await fetch(panel.dataset.resetUrl, {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': getCsrfToken(),
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({}),
                });
                const data = await response.json();
                if (!response.ok || !data.success) {
                    throw new Error(data.error || panel.dataset.resetError || 'Unable to reset preferences.');
                }

                clearPreferenceStorage(storageKey);
                alert(panel.dataset.resetSuccess);
                window.location.reload();
            } catch (error) {
                console.error('Reset failed', error);
                alert(panel.dataset.resetError || 'Unable to reset preferences.');
                this.innerHTML = originalContent;
                this.disabled = false;
                btnCancel.disabled = false;
                actions.hidden = true;
                btnInit.hidden = false;
            }
        });
    }

    function initForcePasswordChangeAll() {
        // Reuse the global confirm-password prompt (confirm_password.js) instead of
        // a bespoke modal — same design as every other "confirm with your password".
        const openButton = document.querySelector('[data-force-pass-change-open]');
        if (!openButton) {
            return;
        }
        openButton.addEventListener('click', () => {
            if (typeof window.dluxConfirmPassword !== 'function') {
                return;
            }
            window.dluxConfirmPassword({
                title: openButton.dataset.title,
                description: openButton.dataset.description,
                confirmLabel: openButton.dataset.confirmLabel,
                icon: 'bi-key-fill',
                danger: true,
                requirePassword: true,
                onConfirm: (currentPassword) => {
                    const body = new FormData();
                    body.append('current_password', currentPassword);
                    return fetch(openButton.dataset.url, {
                        method: 'POST',
                        headers: {
                            'X-CSRFToken': getCsrfToken(),
                            'X-Requested-With': 'XMLHttpRequest',
                        },
                        body,
                    })
                        .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
                        .then(({ ok, data }) => {
                            if (!ok || data.status !== 'success') {
                                throw new Error(data.message || 'Unable to apply command.');
                            }
                            if (window.showToast && data.message) {
                                window.showToast(data.message);
                            }
                            return true;
                        });
                },
            });
        });
    }

    function initEmailHealthCheck() {
        // Re-reads configuration + verification state. Unlike the Celery probe this
        // touches no network and sends no mail — proving delivery is the Email
        // step's test-send button, not a status widget.
        const container = document.querySelector('[data-dlux-email-health]');
        if (!container) {
            return;
        }
        const button = container.querySelector('[data-email-recheck]');
        const badge = container.querySelector('[data-email-badge]');
        if (!button || !badge) {
            return;
        }
        const detail = container.querySelector('[data-email-detail]');
        const note = container.querySelector('[data-email-note]');
        const checkUrl = container.getAttribute('data-check-url');
        const errorLabel = container.getAttribute('data-error-label') || 'Check failed';

        async function runCheck() {
            const response = await fetch(checkUrl, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCsrfToken(),
                    'X-Requested-With': 'XMLHttpRequest',
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({}),
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok || !data.state) {
                throw new Error('email check failed');
            }
            badge.className = 'badge ' + (data.badge_class || 'bg-secondary');
            badge.textContent = data.label || '';
            badge.setAttribute('title', data.note || '');
            if (detail && data.detail) {
                detail.textContent = data.detail;
            }
            if (note) {
                note.textContent = data.note || '';
            }
        }

        function paintError() {
            badge.className = 'badge bg-danger';
            badge.textContent = errorLabel;
            badge.setAttribute('title', '');
        }

        button.addEventListener('click', () => {
            if (window.DluxLoadingButton) {
                if (window.DluxLoadingButton.isBusy(button)) {
                    return;
                }
                window.DluxLoadingButton.run(button, () => runCheck().catch((err) => {
                    paintError();
                    throw err;
                }));
                return;
            }
            runCheck().catch(paintError);
        });
    }

    function initCeleryHealthCheck() {
        // On-demand Celery worker check. Nothing pings the broker until the user
        // clicks the recheck arrow; the server persists the result, so the badge
        // keeps its last outcome across visits until the next manual check.
        const container = document.querySelector('[data-dlux-celery-health]');
        if (!container) {
            return;
        }
        const button = container.querySelector('[data-celery-recheck]');
        const badge = container.querySelector('[data-celery-badge]');
        if (!button || !badge) {
            return;
        }
        const detail = container.querySelector('[data-celery-detail]');
        const note = container.querySelector('[data-celery-note]');
        const checkUrl = container.getAttribute('data-check-url');
        const errorLabel = container.getAttribute('data-error-label') || 'Check failed';

        async function runCheck() {
            const response = await fetch(checkUrl, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCsrfToken(),
                    'X-Requested-With': 'XMLHttpRequest',
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({}),
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok || data.status !== 'ok' || !data.service) {
                throw new Error('celery check failed');
            }
            const svc = data.service;
            badge.className = 'badge ' + (svc.badge_class || 'bg-secondary');
            badge.textContent = svc.label || '';
            badge.setAttribute('title', svc.note || '');
            if (detail && svc.detail) {
                detail.textContent = svc.detail;
            }
            if (note) {
                note.textContent = svc.note || '';
            }
        }

        function paintError() {
            badge.className = 'badge bg-danger';
            badge.textContent = errorLabel;
            badge.setAttribute('title', '');
        }

        button.addEventListener('click', () => {
            if (window.DluxLoadingButton) {
                if (window.DluxLoadingButton.isBusy(button)) {
                    return;
                }
                window.DluxLoadingButton.run(button, () => runCheck().catch((err) => {
                    paintError();
                    throw err; // let the button show its error state too
                }));
                return;
            }
            // Fallback if the shared spinner helper is unavailable.
            if (button.disabled) {
                return;
            }
            button.disabled = true;
            runCheck()
                .catch(paintError)
                .finally(() => {
                    button.disabled = false;
                });
        });
    }

    function initAdminCommandLauncher() {
        const launcher = document.querySelector('[data-admin-command-launcher]');
        const toggle = launcher?.querySelector('[data-admin-command-toggle]');
        if (!launcher || !toggle) {
            return;
        }

        function setOpen(isOpen) {
            launcher.classList.toggle('is-open', isOpen);
            toggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
        }

        toggle.addEventListener('click', (event) => {
            event.stopPropagation();
            setOpen(!launcher.classList.contains('is-open'));
        });

        launcher.addEventListener('click', (event) => {
            event.stopPropagation();
        });

        document.addEventListener('click', () => {
            setOpen(false);
        });

        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') {
                setOpen(false);
            }
        });
    }

    function persistCardOrder(grid, storageKey) {
        const order = Array.from(grid.querySelectorAll('.dlux-options-card[data-options-card]'))
            .map((card) => card.dataset.optionsCard)
            .filter(Boolean);
        localStorage.setItem(storageKey, JSON.stringify(order));
    }

    function restoreCardOrder(grid, storageKey) {
        const raw = localStorage.getItem(storageKey);
        if (!raw) {
            return;
        }

        let order;
        try {
            order = JSON.parse(raw);
        } catch (_error) {
            localStorage.removeItem(storageKey);
            return;
        }

        if (!Array.isArray(order) || !order.length) {
            return;
        }

        const cardsByKey = new Map(
            Array.from(grid.querySelectorAll('.dlux-options-card[data-options-card]'))
                .map((card) => [card.dataset.optionsCard, card])
        );

        order.forEach((key) => {
            const card = cardsByKey.get(key);
            if (card) {
                grid.appendChild(card);
                cardsByKey.delete(key);
            }
        });

        cardsByKey.forEach((card) => {
            grid.appendChild(card);
        });
    }

    function initCardOrdering(grid) {
        const cards = Array.from(grid.querySelectorAll('.dlux-options-card[data-options-card]'));
        if (cards.length < 2) {
            return;
        }

        const storageKey = grid.dataset.optionsOrderStorageKey || OPTIONS_ORDER_STORAGE_KEY;
        restoreCardOrder(grid, storageKey);

        let draggedCard = null;

        function clearDropIndicators() {
            grid.querySelectorAll('.is-drag-over-before, .is-drag-over-after').forEach((card) => {
                card.classList.remove('is-drag-over-before', 'is-drag-over-after');
            });
        }

        function shouldInsertBefore(targetCard, event) {
            const rect = targetCard.getBoundingClientRect();
            const direction = window.getComputedStyle(targetCard).direction || document.documentElement.dir || 'ltr';
            const midpoint = rect.left + (rect.width / 2);
            if (direction === 'rtl') {
                return event.clientX > midpoint;
            }
            return event.clientX < midpoint;
        }

        function placeDraggedCard(targetCard, event) {
            if (!draggedCard || !targetCard || draggedCard === targetCard) {
                return;
            }

            const insertBefore = shouldInsertBefore(targetCard, event);
            targetCard.classList.toggle('is-drag-over-before', insertBefore);
            targetCard.classList.toggle('is-drag-over-after', !insertBefore);
        }

        grid.querySelectorAll('[data-options-card-handle]').forEach((handle) => {
            const card = handle.closest('.dlux-options-card[data-options-card]');
            if (!card) {
                return;
            }

            handle.draggable = true;

            handle.addEventListener('dragstart', (event) => {
                draggedCard = card;
                card.classList.add('is-dragging');
                if (event.dataTransfer) {
                    event.dataTransfer.effectAllowed = 'move';
                    event.dataTransfer.setData('text/plain', card.dataset.optionsCard || '');
                    try {
                        event.dataTransfer.setDragImage(card, 48, 24);
                    } catch (_error) {
                        // Ignore drag image failures.
                    }
                }
            });

            handle.addEventListener('dragend', () => {
                card.classList.remove('is-dragging');
                clearDropIndicators();
                if (draggedCard) {
                    persistCardOrder(grid, storageKey);
                }
                draggedCard = null;
            });
        });

        grid.querySelectorAll('.dlux-options-card[data-options-card]').forEach((card) => {
            card.addEventListener('dragover', (event) => {
                if (!draggedCard || draggedCard === card) {
                    return;
                }
                event.preventDefault();
                clearDropIndicators();
                placeDraggedCard(card, event);
            });

            card.addEventListener('dragleave', (event) => {
                if (!card.contains(event.relatedTarget)) {
                    card.classList.remove('is-drag-over-before', 'is-drag-over-after');
                }
            });

            card.addEventListener('drop', (event) => {
                if (!draggedCard || draggedCard === card) {
                    return;
                }
                event.preventDefault();

                const insertBefore = shouldInsertBefore(card, event);
                if (insertBefore) {
                    grid.insertBefore(draggedCard, card);
                } else {
                    grid.insertBefore(draggedCard, card.nextSibling);
                }

                clearDropIndicators();
                persistCardOrder(grid, storageKey);
            });
        });

        grid.addEventListener('dragover', (event) => {
            if (draggedCard) {
                event.preventDefault();
            }
        });

        grid.addEventListener('drop', (event) => {
            if (!draggedCard || event.target !== grid) {
                return;
            }
            event.preventDefault();
            grid.appendChild(draggedCard);
            clearDropIndicators();
            persistCardOrder(grid, storageKey);
        });
    }

    // Tabbed Options layout: turn each visible card (admin panel first, then the
    // user-preference cards) into a tab pane, driven by a generated tab strip.
    // Labels/icons are read from each card's own heading so no server changes are
    // needed. Reordering is disabled in this mode.
    function initOptionsTabs(grid) {
      try {
        const cards = Array.from(grid.querySelectorAll(':scope > .dlux-options-card'))
            .filter((card) => window.getComputedStyle(card).display !== 'none');
        // With fewer than two panes, tabs add nothing — leave the cards visible
        // (the fail-safe CSS only hides panes once we add the ready class below).
        if (cards.length < 2) {
            return;
        }

        const nav = document.createElement('div');
        nav.className = 'dlux-options-tabs no-print';
        nav.setAttribute('role', 'tablist');

        const tabs = [];
        cards.forEach((card, index) => {
            const heading = card.querySelector('h4');
            const iconEl = heading ? heading.querySelector('i.bi') : null;
            const label = heading ? heading.textContent.trim() : ('Tab ' + (index + 1));

            const tab = document.createElement('button');
            tab.type = 'button';
            tab.className = 'dlux-options-tab';
            tab.setAttribute('role', 'tab');
            tab.id = 'dlux-options-tab-' + index;
            if (iconEl) {
                const icon = document.createElement('i');
                icon.className = iconEl.className;
                tab.appendChild(icon);
            }
            const text = document.createElement('span');
            text.className = 'dlux-options-tab__label';
            text.textContent = label;
            tab.appendChild(text);

            tab.addEventListener('click', () => activate(index));
            tab.addEventListener('keydown', (e) => {
                if (e.key === 'ArrowRight' || e.key === 'ArrowDown') { e.preventDefault(); activate((index + 1) % cards.length); }
                else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') { e.preventDefault(); activate((index - 1 + cards.length) % cards.length); }
            });
            nav.appendChild(tab);
            tabs.push(tab);
        });

        function activate(index) {
            cards.forEach((card, i) => {
                const on = i === index;
                card.classList.toggle('dlux-options-card--tab-active', on);
                tabs[i].classList.toggle('is-active', on);
                tabs[i].setAttribute('aria-selected', on ? 'true' : 'false');
                tabs[i].setAttribute('tabindex', on ? '0' : '-1');
            });
            try { sessionStorage.setItem('dlux.options.active-tab', String(index)); } catch (_e) { /* ignore */ }
        }

        grid.parentNode.insertBefore(nav, grid);
        let start = 0;
        try {
            const saved = parseInt(sessionStorage.getItem('dlux.options.active-tab'), 10);
            if (!isNaN(saved) && saved >= 0 && saved < cards.length) { start = saved; }
        } catch (_e) { /* ignore */ }
        activate(start);
        // Only now — with the tab strip built and one pane active — do we let the
        // CSS hide the inactive panes. If anything above threw, this line is never
        // reached and every card stays visible (a plain stacked list), so the page
        // is never blank and the style can always be changed back.
        grid.classList.add('dlux-options-tabs-ready');
      } catch (_e) {
        grid.classList.remove('dlux-options-tabs-ready');
      }
    }

    onReady(() => {
        const grid = document.getElementById('dluxOptionsGrid');
        if (!grid) {
            return;
        }

        // Card reordering only applies to the default card grid; tabs/compact
        // are single-flow layouts where drag-reorder makes no sense.
        const optionsStyle = grid.getAttribute('data-options-style') || 'cards';
        if (optionsStyle === 'tabs') {
            initOptionsTabs(grid);
        } else if (optionsStyle === 'cards') {
            initCardOrdering(grid);
        }
        initAutofill();
        initThemePicker();
        initAccessibilityToggles();
        initLandingPageControl();
        initLanguagePicker();
        initFontPicker();
        initDensityPickers();
        initFormDensityPicker();
        initModalSizePicker();
        initNavbarModePicker();
        initResetDefaults(grid);
        initAdminCommandLauncher();
        initForcePasswordChangeAll();
        initEmailHealthCheck();
        initCeleryHealthCheck();
        focusHashCard();

        // Lifecycle hook: app-contributed Options cards attach their behaviour
        // here instead of patching options.js. `detail.cardIds` lists every
        // rendered card (built-in + app) so a project can find its own by id.
        try {
            // Auto-persist any data-dlux-app-pref controls inside app cards.
            if (typeof window.bindAppPrefControls === 'function') {
                window.bindAppPrefControls(grid);
            }
            const cardIds = Array.from(grid.querySelectorAll('.dlux-options-card[data-options-card]'))
                .map((el) => el.getAttribute('data-options-card'));
            document.dispatchEvent(new CustomEvent('dlux:options-ready', {
                detail: { grid: grid, cardIds: cardIds }
            }));
        } catch (e) {
            /* never let the lifecycle event break options init */
        }
    });

    // Global search deep-links to a specific options card via
    // #dlux-option-<slug> → scroll it into view and briefly highlight it.
    function focusHashCard() {
        const match = /^#dlux-option-(.+)$/.exec(window.location.hash || '');
        if (!match) { return; }
        const card = document.querySelector('[data-options-card="' + CSS.escape(match[1]) + '"]');
        if (!card) { return; }
        window.setTimeout(function () {
            card.scrollIntoView({ behavior: 'smooth', block: 'center' });
            card.classList.add('dlux-options-card--flash');
            window.setTimeout(function () { card.classList.remove('dlux-options-card--flash'); }, 2000);
        }, 120);
    }
})();
