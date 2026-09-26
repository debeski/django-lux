/* System Settings previews.
 *
 * Every preview is a real page rendered by the server with the unsaved form:
 * the form is POSTed to the draft endpoint (nothing is saved), which answers
 * with a token, and a frame loads an ordinary page carrying that token. The
 * server swaps the stored settings for the draft for that one request only, so
 * what the frame shows is exactly what a save would produce — the project's own
 * pages, its branding and the draft's default language included. See
 * dlux/system/preview.py and docs/system-configuration.md.
 *
 * Three surfaces:
 * - Behind the Options modal, on the steps whose subject is page chrome, a
 *   frame of the current page follows the form as it changes. The Preview
 *   button lifts the modal off it (glass mode); click, Escape or Q returns.
 * - Sections whose subject is not on screen (tables, forms, modals, login,
 *   home, profile) carry an eye that opens the popup with that real page.
 * - The first-run wizard has no page behind it, so its Preview opens the popup.
 */
(function (root) {
    'use strict';

    const { getNamedFieldValue } = root.DluxSetupDom;

    // Mirrors TITLEBAR_ACTIONS_ORDER in dlux/system/constants.py. Keep this
    // complete: normalization also feeds the titlebar order builder.
    const TITLEBAR_ACTIONS_DEFAULT_ORDER = [
        'search',
        'theme',
        'language',
        'notifications',
        'home',
        'profile',
        'help',
        'users',
        'activity',
        'reports',
        'settings',
        'auth',
    ];
    const TITLEBAR_ACTIONS_KNOWN = new Set(TITLEBAR_ACTIONS_DEFAULT_ORDER);
    const SYSTEM_SETTINGS_STEPS = [
        'branding',
        'languages',
        'email',
        'security',
        'appearance',
        'titlebar',
        'sidebar',
        'navbar',
        'ribbon',
        'layout',
        'homepage',
        'login_page',
        'profile',
        'search',
        'notifications',
        'logging',
        'backups',
        'extras',
    ];
    // Steps whose subject is the chrome of the page behind the Options modal.
    const GLASS_STEPS = new Set(['branding', 'languages', 'appearance', 'titlebar', 'sidebar', 'navbar', 'layout']);
    // What the step's Preview button opens when there is no page to lift the modal off.
    const STEP_TARGETS = {
        branding: 'sample_components',
        languages: 'sample_components',
        appearance: 'sample_components',
        titlebar: 'sample_table',
        sidebar: 'sample_table',
        navbar: 'sample_table',
        ribbon: 'sample_table',
        layout: 'sample_table',
        homepage: 'home',
        login_page: 'login',
        profile: 'profile',
    };
    const REFRESH_DELAY_MS = 450;
    const APP_PREVIEW_REGISTRY = new Map();

    function t(key, fallback) {
        const strings = root.DLUX_STRINGS || {};
        return strings[key] || fallback;
    }

    function parseJson(text, fallback) {
        try {
            return JSON.parse(text || '');
        } catch (error) {
            return fallback;
        }
    }

    function readBooleanField(form, selector, fallback) {
        const field = form.querySelector(selector);
        return field ? Boolean(field.checked) : Boolean(fallback);
    }

    function readTrimmedValue(form, selector, fallback) {
        const field = form.querySelector(selector);
        return field ? String(field.value || fallback || '').trim() : fallback || '';
    }

    function normalizeTitlebarActionsOrder(value) {
        let rawValue = value;
        if (typeof rawValue === 'string') rawValue = parseJson(rawValue, []);
        if (!Array.isArray(rawValue)) rawValue = [];
        const seen = new Set();
        const normalized = [];
        rawValue.forEach((item) => {
            const key = String(item || '').trim();
            if (TITLEBAR_ACTIONS_KNOWN.has(key) && !seen.has(key)) {
                normalized.push(key);
                seen.add(key);
            }
        });
        TITLEBAR_ACTIONS_DEFAULT_ORDER.forEach((key) => {
            if (!seen.has(key)) normalized.push(key);
        });
        return normalized;
    }

    function readTitlebarActionsOrder(form) {
        return normalizeTitlebarActionsOrder(getNamedFieldValue(form, 'titlebar_actions_order'));
    }

    // ── Drafts ────────────────────────────────────────────────────────────

    function draftEndpoint() {
        return (root.DLUX_URLS && root.DLUX_URLS.settingsPreviewDraft) || '';
    }

    function modalOf(form) {
        return form ? form.closest('#universalDynamicModal') : null;
    }

    function formMode(form) {
        return modalOf(form) ? 'options' : 'setup';
    }

    function csrfToken(form) {
        const field = form.querySelector('input[name="csrfmiddlewaretoken"]')
            || document.querySelector('input[name="csrfmiddlewaretoken"]');
        return field ? field.value : '';
    }

    const pendingDrafts = new WeakMap();

    // An Options step editor posts one step, and its save names it with ?step=N
    // so the other steps keep their stored values; the draft is validated the same way.
    function draftStepQuery(form) {
        if (!modalOf(form) || !isSettingsForm(form)) return '';
        const index = SYSTEM_SETTINGS_STEPS.indexOf(currentPreviewStep(form));
        return index >= 0 ? `?step=${index}` : '';
    }

    // POST the unsaved form; resolves to the endpoint's JSON (ok + token, or errors).
    async function requestDraft(form, extra) {
        const endpoint = draftEndpoint() && draftEndpoint() + draftStepQuery(form);
        if (!endpoint) throw new Error(t('preview_unavailable', 'Preview is not available for this step.'));
        const previous = pendingDrafts.get(form);
        if (previous) previous.abort();
        const controller = new AbortController();
        pendingDrafts.set(form, controller);
        const body = new FormData(form);
        Array.from(body.keys()).forEach((key) => {
            if (body.get(key) instanceof File) body.delete(key);
        });
        Object.entries(extra || {}).forEach(([key, value]) => body.set(key, value));
        const response = await fetch(endpoint, {
            method: 'POST',
            body,
            credentials: 'same-origin',
            headers: { 'X-CSRFToken': csrfToken(form), 'X-Requested-With': 'XMLHttpRequest' },
            signal: controller.signal,
        });
        const payload = await response.json().catch(() => ({ ok: false, errors: { __all__: [response.statusText] } }));
        if (pendingDrafts.get(form) === controller) pendingDrafts.delete(form);
        return payload;
    }

    function systemDraft(form) {
        return requestDraft(form, { _dlux_preview_kind: 'system', _dlux_preview_mode: formMode(form) });
    }

    function previewUrl(draft, path, { audience = '', lang = '' } = {}) {
        const url = new URL(path || '/', root.location.origin);
        url.searchParams.set(draft.param, draft.token);
        if (audience) url.searchParams.set(draft.as_param, audience);
        if (lang) url.searchParams.set(draft.lang_param, lang);
        return url.pathname + url.search;
    }

    function currentPagePath() {
        return root.location.pathname + root.location.search;
    }

    // ── Step awareness ───────────────────────────────────────────────────

    function currentPreviewStep(form) {
        const steps = Array.from(form.querySelectorAll('.wizard-step'));
        const activeIndex = steps.findIndex((step) => !step.classList.contains('d-none') && step.style.display !== 'none');
        if (activeIndex >= 0) return SYSTEM_SETTINGS_STEPS[activeIndex] || '';
        const initialIndex = Number(form.dataset.dluxWizardInitialStep);
        return Number.isInteger(initialIndex) ? SYSTEM_SETTINGS_STEPS[initialIndex] || '' : '';
    }

    function isSettingsForm(form) {
        return Boolean(form && form.classList.contains('dlux-system-setup-form'));
    }

    function usesLiveBackdrop(form) {
        return Boolean(modalOf(form)) && GLASS_STEPS.has(currentPreviewStep(form));
    }

    // ── Live backdrop behind the Options modal ────────────────────────────

    const backdrop = { root: null, frames: [], form: null, timer: 0, generation: 0 };

    function ensureBackdrop() {
        if (backdrop.root && backdrop.root.isConnected) return backdrop.root;
        const container = document.createElement('div');
        container.className = 'dlux-preview-backdrop';
        container.hidden = true;
        container.setAttribute('aria-hidden', 'true');
        // Inert: a page loading in the frame must never take focus (or Escape and
        // Q) away from the modal that owns the keyboard.
        container.inert = true;
        backdrop.frames = [0, 1].map(() => {
            const frame = document.createElement('iframe');
            frame.setAttribute('tabindex', '-1');
            frame.inert = true;
            frame.setAttribute('title', t('preview_frame_title', 'Settings preview'));
            frame.dataset.dluxPreviewStale = '';
            container.appendChild(frame);
            return frame;
        });
        backdrop.root = container;
        placeBackdrop();
        return container;
    }

    // The frame shares z-index 1050 with the sticky titlebar and Bootstrap's
    // modal backdrop, so document order decides: after the titlebar (the draft
    // page covers the real one) and before the backdrop (the modal's darkening
    // still lies over it). Bootstrap re-creates the backdrop on every show.
    // Moving an iframe in the DOM reloads it, so the container is placed once,
    // when it is created, and only moved again if it ever ends up after the
    // darkening (a backdrop Bootstrap re-creates is appended after it anyway).
    function placeBackdrop() {
        const container = backdrop.root;
        if (!container) return;
        const modalBackdrop = document.querySelector('.modal-backdrop');
        if (!modalBackdrop || !modalBackdrop.parentNode) {
            if (!container.isConnected) document.body.appendChild(container);
            return;
        }
        const before = container.isConnected
            && Boolean(container.compareDocumentPosition(modalBackdrop) & Node.DOCUMENT_POSITION_FOLLOWING);
        if (!before) modalBackdrop.before(container);
    }

    // The modal belongs to the real page, which a preview never patches — with
    // one exception: fonts are chosen inside the modal, so it shows the draft's
    // default font for the page's language. The face comes from the draft page
    // (which loads the draft's allowed fonts) through the FontFace API, and the
    // family is set through the CSSOM: no markup, nothing CSP has to allow.
    const loadedFaces = new Set();

    function draftFontFamily(form) {
        const field = form.querySelector('[name="default_fonts"]');
        const fonts = parseJson(field ? field.value : '', {});
        const slug = fonts && typeof fonts === 'object' ? fonts[document.documentElement.lang] : '';
        const families = parseJson(document.getElementById('dlux-font-families')?.textContent, {});
        return slug && families[slug] ? families[slug] : '';
    }

    function adoptFontFaces(frameDocument, family) {
        const wanted = family.toLowerCase();
        Array.from(frameDocument.styleSheets || []).forEach((sheet) => {
            let rules = [];
            try { rules = Array.from(sheet.cssRules || []); } catch (error) { return; }
            rules.filter((rule) => rule.type === 5).forEach((rule) => {
                const name = rule.style.getPropertyValue('font-family').replace(/["']/g, '').trim();
                if (name.toLowerCase() !== wanted) return;
                const weight = rule.style.getPropertyValue('font-weight') || 'normal';
                const style = rule.style.getPropertyValue('font-style') || 'normal';
                const key = `${name}|${weight}|${style}`;
                if (loadedFaces.has(key)) return;
                loadedFaces.add(key);
                const face = new FontFace(name, rule.style.getPropertyValue('src'), { weight, style, display: 'swap' });
                document.fonts.add(face);
                face.load().catch(() => loadedFaces.delete(key));
            });
        });
    }

    function syncModalFont(form, frame) {
        const modal = modalOf(form);
        if (!modal) return;
        const family = draftFontFamily(form);
        if (!family) {
            modal.style.removeProperty('font-family');
            return;
        }
        if (frame && frame.contentDocument) adoptFontFaces(frame.contentDocument, family);
        modal.style.setProperty('font-family', `'${family}', var(--dlux-font-fallback, sans-serif)`);
    }

    function clearModalFont() {
        document.querySelectorAll('#universalDynamicModal').forEach((modal) => modal.style.removeProperty('font-family'));
    }

    function hideBackdrop() {
        root.clearTimeout(backdrop.timer);
        backdrop.generation += 1;
        if (backdrop.root) backdrop.root.hidden = true;
        backdrop.form = null;
    }

    // Load the draft into the hidden frame and swap it in once it has loaded,
    // so a change never flashes an empty page.
    // The draft page is only worth showing once the form differs from how it
    // opened: until then it is the real page, and loading a copy of it only
    // looks like the page reloading. Changing a value back returns to the real page.
    const baselines = new WeakMap();

    function serializeForm(form) {
        return JSON.stringify(Array.from(new FormData(form).entries())
            .filter(([, value]) => !(value instanceof File))
            .map(([key, value]) => [key, String(value)]));
    }

    function rememberBaseline(form) {
        baselines.set(form, serializeForm(form));
    }

    function isPristine(form) {
        return baselines.has(form) && baselines.get(form) === serializeForm(form);
    }

    // Open the copy where the reader is: the same scroll offset as the real page.
    function matchScroll(frame) {
        try {
            const doc = frame.contentDocument;
            const realMain = document.getElementById('mainContent');
            const frameMain = doc && doc.getElementById('mainContent');
            if (realMain && frameMain) frameMain.scrollTop = realMain.scrollTop;
            frame.contentWindow.scrollTo(root.scrollX, root.scrollY);
        } catch (error) {
            // A frame that is not same-origin cannot be read; there is none here.
        }
    }

    async function refreshBackdrop(form) {
        if (!usesLiveBackdrop(form) || isPristine(form)) {
            hideBackdrop();
            if (isPristine(form)) clearModalFont();
            return;
        }
        const generation = ++backdrop.generation;
        let draft;
        try {
            draft = await systemDraft(form);
        } catch (error) {
            return;
        }
        if (generation !== backdrop.generation || !draft || !draft.ok) return;
        ensureBackdrop();
        const front = backdrop.frames.find((frame) => frame.dataset.dluxPreviewStale === undefined);
        const back = backdrop.frames.find((frame) => frame !== front) || backdrop.frames[0];
        back.onload = () => {
            if (generation !== backdrop.generation) return;
            matchScroll(back);
            delete back.dataset.dluxPreviewStale;
            if (front && front !== back) front.dataset.dluxPreviewStale = '';
            backdrop.root.hidden = false;
            syncModalFont(form, back);
        };
        back.dataset.dluxPreviewStale = '';
        back.src = previewUrl(draft, currentPagePath());
        backdrop.form = form;
    }

    function scheduleRefresh(form) {
        if (!isSettingsForm(form) || !modalOf(form)) return;
        root.clearTimeout(backdrop.timer);
        backdrop.timer = root.setTimeout(() => refreshBackdrop(form), REFRESH_DELAY_MS);
    }

    // ── Glass mode ───────────────────────────────────────────────────────

    let glassPreviewState = null;

    function exitGlassPreview() {
        if (!glassPreviewState) return;
        const { modal, button, shield, clickHandler, keyHandler, hideHandler } = glassPreviewState;
        shield.remove();
        modal.classList.remove('dlux-system-preview-glass');
        delete modal.dataset.dluxPreviewHint;
        const content = modal.querySelector('.modal-content');
        if (content) delete content.dataset.dluxPreviewHint;
        document.body.classList.remove('dlux-system-preview-active');
        modal.removeEventListener('click', clickHandler, true);
        document.removeEventListener('keydown', keyHandler, true);
        modal.removeEventListener('hide.bs.modal', hideHandler);
        glassPreviewState = null;
        if (button?.isConnected) button.focus({ preventScroll: true });
    }

    function enterGlassPreview(form, button) {
        const modal = modalOf(form);
        if (!modal) return;
        exitGlassPreview();
        root.clearTimeout(backdrop.timer);
        refreshBackdrop(form);
        const hint = t('preview_close_hint', 'Click anywhere, press Escape, or press Q to return.');
        modal.dataset.dluxPreviewHint = hint;
        const content = modal.querySelector('.modal-content');
        if (content) content.dataset.dluxPreviewHint = hint;
        modal.classList.add('dlux-system-preview-glass');
        document.body.classList.add('dlux-system-preview-active');
        // The draft frame lets clicks through; outside the modal they would reach
        // the real page. The shield takes them instead, and a click only returns.
        const shield = document.createElement('div');
        shield.className = 'dlux-preview-glass-shield';
        document.body.appendChild(shield);

        const clickHandler = (event) => {
            event.preventDefault();
            event.stopImmediatePropagation();
            exitGlassPreview();
        };
        const keyHandler = (event) => {
            if (event.key !== 'Escape' && String(event.key || '').toLowerCase() !== 'q') return;
            event.preventDefault();
            event.stopImmediatePropagation();
            exitGlassPreview();
        };
        const hideHandler = () => exitGlassPreview();
        glassPreviewState = { modal, button, shield, clickHandler, keyHandler, hideHandler };
        shield.addEventListener('click', clickHandler, true);
        // Keys and hiding count at once; only the modal's click waits a tick, so
        // the click that opened glass mode is not also the one that closes it.
        document.addEventListener('keydown', keyHandler, true);
        modal.addEventListener('hide.bs.modal', hideHandler);
        root.setTimeout(() => {
            if (!glassPreviewState || glassPreviewState.modal !== modal) return;
            modal.addEventListener('click', clickHandler, true);
        }, 0);
    }

    // ── Popup ────────────────────────────────────────────────────────────

    const TARGET_TITLES = {
        sample_table: ['preview_target_table', 'Tables and list pages'],
        sample_form: ['preview_target_form', 'Forms'],
        sample_modal: ['preview_target_modal', 'Modals'],
        sample_components: ['preview_target_components', 'Cards, buttons and typography'],
        home: ['preview_target_home', 'Home page'],
        home_user: ['preview_target_home', 'Home page'],
        home_public: ['preview_target_home_public', 'Public page'],
        login: ['preview_target_login', 'Login page'],
        profile: ['preview_target_profile', 'Profile page'],
        app: ['btn_preview', 'Preview'],
    };

    let popupState = null;

    function closePopup() {
        if (!popupState) return;
        const { element, keyHandler, opener } = popupState;
        document.removeEventListener('keydown', keyHandler, true);
        element.remove();
        popupState = null;
        if (opener?.isConnected) opener.focus({ preventScroll: true });
    }

    function renderErrors(status, errors) {
        status.hidden = false;
        status.replaceChildren();
        const box = document.createElement('div');
        box.className = 'dlux-preview-popup__errors';
        const heading = document.createElement('p');
        heading.className = 'fw-semibold';
        heading.textContent = t('preview_invalid_draft', 'Fix these settings before previewing:');
        box.appendChild(heading);
        const list = document.createElement('ul');
        Object.entries(errors || {}).forEach(([field, messages]) => {
            (Array.isArray(messages) ? messages : [messages]).forEach((message) => {
                const item = document.createElement('li');
                item.textContent = field === '__all__' ? String(message) : `${field}: ${message}`;
                list.appendChild(item);
            });
        });
        box.appendChild(list);
        status.appendChild(box);
    }

    function option(value, label) {
        const element = document.createElement('option');
        element.value = value;
        element.textContent = label;
        return element;
    }

    function spinner() {
        const element = document.createElement('div');
        element.className = 'spinner-border text-primary';
        element.setAttribute('aria-hidden', 'true');
        return element;
    }

    // Open the popup on `target` (a key of the draft's `targets`, or `home`
    // for the signed-in/visitor pair). `makeDraft` produces the draft to show.
    async function openPopup(target, makeDraft, opener) {
        closePopup();
        const [titleKey, titleFallback] = TARGET_TITLES[target] || TARGET_TITLES.app;
        const element = document.createElement('div');
        element.className = 'dlux-preview-popup';
        element.setAttribute('role', 'dialog');
        element.setAttribute('aria-modal', 'true');
        element.dataset.previewTarget = target;
        element.innerHTML = `
            <div class="dlux-preview-popup__dialog">
                <div class="dlux-preview-popup__bar">
                    <h2 class="dlux-preview-popup__title"></h2>
                    <select class="form-select form-select-sm" data-preview-audience hidden></select>
                    <select class="form-select form-select-sm" data-preview-language hidden></select>
                    <div class="btn-group btn-group-sm" role="group">
                        <button type="button" class="btn btn-outline-secondary active" data-viewport="desktop"><i class="bi bi-display" aria-hidden="true"></i></button>
                        <button type="button" class="btn btn-outline-secondary" data-viewport="tablet"><i class="bi bi-tablet" aria-hidden="true"></i></button>
                        <button type="button" class="btn btn-outline-secondary" data-viewport="mobile"><i class="bi bi-phone" aria-hidden="true"></i></button>
                    </div>
                    <button type="button" class="btn-close" data-preview-close></button>
                </div>
                <div class="dlux-preview-popup__stage" data-viewport="desktop">
                    <iframe></iframe>
                    <div class="dlux-preview-popup__status" role="status"></div>
                </div>
            </div>`;
        const title = element.querySelector('.dlux-preview-popup__title');
        title.textContent = t(titleKey, titleFallback);
        element.setAttribute('aria-label', title.textContent);
        element.querySelector('[data-preview-close]').setAttribute('aria-label', t('btn_close', 'Close'));
        [['desktop', 'preview_viewport_desktop', 'Desktop'], ['tablet', 'preview_viewport_tablet', 'Tablet'],
            ['mobile', 'preview_viewport_mobile', 'Mobile']].forEach(([key, stringKey, fallback]) => {
            const button = element.querySelector(`[data-viewport="${key}"]`);
            button.setAttribute('aria-label', t(stringKey, fallback));
            button.title = t(stringKey, fallback);
        });
        const frame = element.querySelector('iframe');
        frame.title = t('preview_frame_title', 'Settings preview');
        const stage = element.querySelector('.dlux-preview-popup__stage');
        const status = element.querySelector('.dlux-preview-popup__status');
        status.appendChild(spinner());
        const audienceSelect = element.querySelector('[data-preview-audience]');
        const languageSelect = element.querySelector('[data-preview-language]');
        document.body.appendChild(element);

        const keyHandler = (event) => {
            if (event.key !== 'Escape') return;
            event.preventDefault();
            event.stopImmediatePropagation();
            closePopup();
        };
        document.addEventListener('keydown', keyHandler, true);
        element.addEventListener('click', (event) => {
            if (event.target === element || event.target.closest('[data-preview-close]')) {
                closePopup();
                return;
            }
            const viewport = event.target.closest('[data-viewport]');
            if (viewport) {
                stage.dataset.viewport = viewport.dataset.viewport;
                element.querySelectorAll('[data-viewport]').forEach((button) => {
                    button.classList.toggle('active', button === viewport);
                });
            }
        });
        popupState = { element, keyHandler, opener };

        let draft;
        try {
            draft = await makeDraft();
        } catch (error) {
            renderErrors(status, { __all__: [error.message || String(error)] });
            return;
        }
        if (!popupState || popupState.element !== element) return;
        if (!draft || !draft.ok) {
            renderErrors(status, draft && draft.errors);
            return;
        }

        const targets = draft.targets || {};
        const audiences = target === 'home'
            ? [['home_user', t('preview_audience_user', 'Signed in')],
                ['home_public', t('preview_audience_visitor', 'Visitors')]].filter(([key]) => targets[key])
            : [];
        if (audiences.length > 1) {
            audiences.forEach(([key, label]) => audienceSelect.appendChild(option(key, label)));
            audienceSelect.setAttribute('aria-label', t('preview_audience_label', 'Seen by'));
            audienceSelect.hidden = false;
        }
        (draft.languages || []).forEach((language) => {
            languageSelect.appendChild(option(language.code, language.name));
        });
        languageSelect.value = draft.language;
        languageSelect.setAttribute('aria-label', t('preview_language_label', 'Language'));
        languageSelect.hidden = (draft.languages || []).length < 2;

        const load = () => {
            const key = target === 'home' ? (audienceSelect.value || 'home_user') : target;
            const spec = targets[key];
            if (!spec) {
                renderErrors(status, { __all__: [t('preview_unavailable', 'Preview is not available for this step.')] });
                return;
            }
            status.hidden = false;
            status.replaceChildren(spinner());
            frame.onload = () => { status.hidden = true; };
            frame.src = previewUrl(draft, spec.path, {
                audience: spec.audience,
                lang: languageSelect.value && languageSelect.value !== draft.language ? languageSelect.value : '',
            });
        };
        audienceSelect.addEventListener('change', load);
        languageSelect.addEventListener('change', load);
        load();
    }

    // ── Buttons ──────────────────────────────────────────────────────────

    function previewButtonsFor(form) {
        const buttons = Array.from(form.querySelectorAll('[data-dlux-system-settings-preview]'));
        if (form.id) {
            const escapedId = root.CSS && typeof root.CSS.escape === 'function'
                ? root.CSS.escape(form.id)
                : form.id.replace(/["\\]/g, '\\$&');
            document.querySelectorAll(`[data-dlux-system-settings-preview][form="${escapedId}"]`).forEach((button) => {
                if (!buttons.includes(button)) buttons.push(button);
            });
        }
        return buttons;
    }

    function resolvePreviewMode(form) {
        const step = currentPreviewStep(form);
        if (usesLiveBackdrop(form)) return { mode: 'glass', step, target: '' };
        const target = STEP_TARGETS[step] || '';
        return { mode: target ? 'popup' : '', step, target };
    }

    function syncPreviewButtons(form) {
        const { mode, step } = resolvePreviewMode(form);
        previewButtonsFor(form).forEach((button) => {
            const unavailable = button.dataset.previewUnavailableLabel || t('preview_unavailable', 'Preview is not available for this step.');
            button.disabled = !mode;
            button.dataset.previewMode = mode;
            button.dataset.previewStep = step;
            button.setAttribute('aria-disabled', mode ? 'false' : 'true');
            if (mode) button.removeAttribute('title');
            else button.setAttribute('title', unavailable);
        });
    }

    function initPreviewControls(form) {
        previewButtonsFor(form).forEach((button) => {
            if (button.dataset.dluxSystemPreviewBound === 'true') return;
            button.dataset.dluxSystemPreviewBound = 'true';
            button.addEventListener('click', () => {
                const { mode, target } = resolvePreviewMode(form);
                if (mode === 'glass') enterGlassPreview(form, button);
                else if (mode === 'popup') openPopup(target, () => systemDraft(form), button);
            });
        });
        form.querySelectorAll('[data-dlux-preview-target]').forEach((eye) => {
            if (eye.dataset.dluxSystemPreviewBound === 'true') return;
            eye.dataset.dluxSystemPreviewBound = 'true';
            eye.addEventListener('click', (event) => {
                event.preventDefault();
                openPopup(eye.dataset.dluxPreviewTarget, () => systemDraft(form), eye);
            });
        });
        if (form.dataset.dluxPreviewStepBound !== 'true') {
            form.dataset.dluxPreviewStepBound = 'true';
            form.addEventListener('dlux:wizard-step-change', () => {
                syncPreviewButtons(form);
                scheduleRefresh(form);
            });
        }
        syncPreviewButtons(form);
    }

    // Kept for callers that announce a change after rewriting a hidden builder
    // field; the backdrop re-renders from the form instead of patching the page.
    function applySystemSettingsPreview(form) {
        if (isSettingsForm(form)) scheduleRefresh(form);
    }

    function applyThemePreview() {
        const form = backdrop.form || document.querySelector('#universalDynamicModal form.dlux-system-setup-form');
        if (form) scheduleRefresh(form);
    }

    function initSystemSettingsPreview(scope) {
        initAppPreviewControls(scope);
        scope.querySelectorAll('form.dlux-system-setup-form').forEach((form) => {
            if (form.dataset.systemSettingsPreviewBound !== 'true') {
                form.dataset.systemSettingsPreviewBound = 'true';
                form.addEventListener('input', () => scheduleRefresh(form));
                form.addEventListener('change', () => scheduleRefresh(form));
                const modal = modalOf(form);
                if (modal && modal.dataset.dluxPreviewBackdropBound !== 'true') {
                    modal.dataset.dluxPreviewBackdropBound = 'true';
                    modal.addEventListener('hidden.bs.modal', () => {
                        hideBackdrop();
                        clearModalFont();
                    });
                }
            }
            initPreviewControls(form);
            // Initialisers may still write hidden fields this tick; the baseline
            // is the form as the reader first sees it.
            root.setTimeout(() => { if (!baselines.has(form)) rememberBaseline(form); }, 0);
        });
    }

    // ── App-owned settings ───────────────────────────────────────────────

    function appPreviewForms(scope, registration) {
        const selector = `form[data-dlux-app-settings-namespace="${registration.namespace}"]`;
        const forms = Array.from(scope.querySelectorAll(selector));
        if (scope.matches && scope.matches(selector)) forms.unshift(scope);
        return forms;
    }

    function appPreviewButtonsFor(form) {
        const buttons = Array.from(form.querySelectorAll('[data-dlux-app-settings-preview]'));
        if (form.id) {
            document.querySelectorAll(`[data-dlux-app-settings-preview][form="${form.id}"]`).forEach((button) => {
                if (!buttons.includes(button)) buttons.push(button);
            });
        }
        return buttons;
    }

    function initAppPreviewForm(form, registration) {
        appPreviewButtonsFor(form).forEach((button) => {
            button.hidden = false;
            button.disabled = false;
            button.setAttribute('aria-disabled', 'false');
            button.removeAttribute('title');
            if (button.dataset.dluxAppPreviewBound === registration.namespace) return;
            button.dataset.dluxAppPreviewBound = registration.namespace;
            button.addEventListener('click', () => {
                const current = APP_PREVIEW_REGISTRY.get(registration.namespace);
                if (!current) return;
                openPopup('app', async () => {
                    const draft = await requestDraft(form, {
                        _dlux_preview_kind: 'app',
                        _dlux_preview_namespace: current.namespace,
                    });
                    if (draft && draft.ok) {
                        const path = typeof current.path === 'function' ? current.path(form) : current.path;
                        draft.targets = { ...(draft.targets || {}), app: { path: path || '/', audience: current.audience } };
                    }
                    return draft;
                }, button);
            });
        });
    }

    function initAppPreviewControls(scope) {
        const target = scope || document;
        APP_PREVIEW_REGISTRY.forEach((registration) => {
            appPreviewForms(target, registration).forEach((form) => initAppPreviewForm(form, registration));
        });
    }

    // Register a preview for an app's own settings. `options.path` is the page
    // to render with the unsaved app form applied (a string, or a function of
    // the form); `options.audience` may be `anonymous` for a public page.
    function registerAppPreview(namespace, options) {
        if (!namespace || typeof namespace !== 'string') throw new TypeError('Preview namespace is required.');
        const settings = options || {};
        if (typeof settings.path !== 'string' && typeof settings.path !== 'function') {
            throw new TypeError('An app preview needs a path to render.');
        }
        APP_PREVIEW_REGISTRY.set(namespace, {
            namespace,
            path: settings.path,
            audience: settings.audience === 'anonymous' ? 'anonymous' : '',
        });
        initAppPreviewControls(document);
        return () => unregisterAppPreview(namespace);
    }

    function unregisterAppPreview(namespace) {
        APP_PREVIEW_REGISTRY.delete(namespace);
        document.querySelectorAll('[data-dlux-app-settings-preview]').forEach((button) => {
            if (button.dataset.dluxAppPreviewBound !== namespace) return;
            button.hidden = true;
            button.disabled = true;
            button.setAttribute('aria-disabled', 'true');
        });
    }

    const previewApi = {
        TITLEBAR_ACTIONS_DEFAULT_ORDER,
        applySystemSettingsPreview,
        applyThemePreview,
        closePreview: closePopup,
        initAppPreviewControls,
        initSystemSettingsPreview,
        normalizeTitlebarActionsOrder,
        openPreview: (form, target) => openPopup(target, () => systemDraft(form)),
        readBooleanField,
        readTitlebarActionsOrder,
        readTrimmedValue,
        registerAppPreview,
        requestDraft,
        unregisterAppPreview,
    };
    root.DluxSetupPreview = Object.assign(root.DluxSetupPreview || {}, previewApi);
    root.DluxSetup = Object.assign(root.DluxSetup || {}, previewApi, {
        applyImmediateSystemSettingsPreview: applySystemSettingsPreview,
        initImmediateSystemSettingsPreview: initSystemSettingsPreview,
    });
})(typeof window !== 'undefined' ? window : globalThis);
