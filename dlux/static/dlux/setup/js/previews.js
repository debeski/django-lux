/* Setup wizard: live previews of the surrounding chrome.
 *
 * Editing a setting updates the real footer, titlebar and body flags
 * immediately, without a save — which is also why breaking one is silent: the
 * preview simply stops responding and the operator configures blind.
 *
 * `applySidebarPreview` deliberately stayed in main.js. The wizard renders no
 * sidebar (`#sidebar` and `.sidebar` are both absent from the page), so its 112
 * lines have nothing to act on and cannot be verified across a move.
 *
 * Depends on setup/js/dom.js.
 */
(function (root) {
    'use strict';

    const {
        getNamedFieldValue
    } = root.DluxSetupDom;

    function applyBrandingFilePreviews(form) {
        const logoInput = form.querySelector('#id_logo');
        const faviconInput = form.querySelector('#id_favicon');

        if (logoInput && logoInput.files && logoInput.files[0]) {
            const reader = new FileReader();
            reader.onload = () => {
                document.querySelectorAll('.titlebar__logo, .dlux-setup-page-logo').forEach((image) => {
                    image.setAttribute('src', reader.result);
                });
            };
            reader.readAsDataURL(logoInput.files[0]);
        }

        if (faviconInput && faviconInput.files && faviconInput.files[0]) {
            const reader = new FileReader();
            reader.onload = () => {
                document.querySelectorAll('link[rel="icon"]').forEach((favicon) => {
                    favicon.setAttribute('href', reader.result);
                });
            };
            reader.readAsDataURL(faviconInput.files[0]);
        }
    }

    function applyFooterPreview(form) {
        // Best-effort: the footer element only exists in the DOM when enabled, so
        // we can hide a shown footer and update its text/link live; enabling a
        // currently-absent footer only takes effect after save.
        if (!form.querySelector('[name="footer_enabled"]')) {
            return;
        }
        const enabled = readBooleanField(form, '#id_footer_enabled', true);
        const footer = document.querySelector('footer.dlux-footer');
        if (footer) {
            footer.style.display = enabled ? '' : 'none';
            const textEl = footer.querySelector('.dlux-footer__text');
            const text = getNamedFieldValue(form, 'footer_text');
            if (textEl && text) {
                textEl.textContent = text;
            }
        }
    }

    function applyLayoutBodyPreview(form) {
        // Live-preview only the GLOBAL layout settings on the <body> behind the
        // modal: sticky headers, column resizing, and zebra striping (admin-only,
        // no per-user override). `default_form_density` and `default_modal_size` are the admin
        // DEFAULTS for those per-user preferences — previewing them here would
        // overwrite the editing admin's OWN resolved `data-dlux-form-density` /
        // `data-dlux-modal-size` (which reflect their personal Options choice),
        // making every modal snap to the global default. So they are NOT previewed.
        if (form.querySelector('[name="sticky_table_headers"]')) {
            document.body.dataset.dluxStickyHeader = readBooleanField(form, '#id_sticky_table_headers', true) ? 'on' : 'off';
        }
        if (form.querySelector('[name="resizable_table_columns"]')) {
            document.body.dataset.dluxTableResize = readBooleanField(form, '#id_resizable_table_columns', true) ? 'on' : 'off';
        }
        if (form.querySelector('[name="zebra_striping"]')) {
            document.body.dataset.dluxZebra = readBooleanField(form, '#id_zebra_striping', true) ? 'on' : 'off';
        }
        if (form.querySelector('[name="table_accent_edges"]')) {
            document.body.dataset.dluxTableAccent = readBooleanField(form, '#id_table_accent_edges', false) ? 'on' : 'off';
        }
    }

    function applyNotificationPreview(form) {
        const notificationsEnabled = readBooleanField(form, '#id_notifications_enabled', true);
        const flashEnabled = notificationsEnabled && readBooleanField(form, '#id_notification_flash_enabled', true);
        const flashPosition = getNamedFieldValue(form, 'notification_flash_position') || 'top_center';
        const flashSize = getNamedFieldValue(form, 'notification_flash_size') || 'balanced';
        const flashTextSize = getNamedFieldValue(form, 'notification_flash_text_size') || 'md';
        const flashTimeout = readTrimmedValue(form, '#id_notification_flash_timeout_ms', '3200') || '3200';
        const flashMaxVisible = readTrimmedValue(form, '#id_notification_flash_max_visible', '3') || '3';
        document.querySelectorAll('.dlux-flash-container, .dlux-page-alert-container').forEach((container) => {
            container.dataset.dluxFlashPosition = flashPosition;
            container.dataset.dluxFlashSize = flashSize;
            container.dataset.dluxFlashTextSize = flashTextSize;
            container.dataset.dluxFlashTimeout = flashTimeout;
            container.dataset.dluxFlashMaxVisible = flashMaxVisible;
            setPreviewVisibility(container, flashEnabled);
        });

        const drawerEnabled = notificationsEnabled && readBooleanField(form, '#id_notification_drawer_enabled', true);
        const badgeEnabled = notificationsEnabled && readBooleanField(form, '#id_notification_badge_enabled', true);
        const notificationRoots = Array.from(document.querySelectorAll('[data-dlux-notifications]'));
        notificationRoots.forEach((notifications) => {
            notifications.dataset.dluxNotificationsEnabled = drawerEnabled ? 'true' : 'false';
            notifications.dataset.badgeEnabled = badgeEnabled ? 'true' : 'false';
            setPreviewVisibility(notifications, drawerEnabled);
            notifications.querySelectorAll('[data-dlux-notifications-badge]').forEach((badge) => {
                const hasCount = String(badge.textContent || '').trim().length > 0;
                badge.classList.toggle('d-none', !badgeEnabled || !hasCount);
            });
        });
    }

    function applyTableDensityPreview(form) {
        const density = getNamedFieldValue(form, 'default_table_density') || 'balanced';
        if (typeof window.applyDluxTableDensityPreview === 'function') {
            window.applyDluxTableDensityPreview(density);
        }
    }

    function readBooleanField(form, selector, fallback) {
        const field = form.querySelector(selector);
        if (!field) {
            return Boolean(fallback);
        }
        return Boolean(field.checked);
    }

    function readTrimmedValue(form, selector, fallback) {
        const field = form.querySelector(selector);
        if (!field) {
            return fallback || '';
        }
        return String(field.value || fallback || '').trim();
    }

    function setPreviewVisibility(element, isVisible) {
        if (!element) {
            return;
        }
        element.classList.toggle('d-none', !isVisible);
        element.style.display = isVisible ? '' : 'none';
    }

    root.DluxSetup = Object.assign(root.DluxSetup || {}, {
        applyBrandingFilePreviews,
        applyFooterPreview,
        applyLayoutBodyPreview,
        applyNotificationPreview,
        applyTableDensityPreview,
        readBooleanField,
        readTrimmedValue,
        setPreviewVisibility
    });
})(typeof window !== 'undefined' ? window : globalThis);
