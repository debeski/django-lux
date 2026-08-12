(function () {
    function initializePicker(picker) {
        if (!picker || picker.dataset.assetPickerReady === 'true') return;
        picker.dataset.assetPickerReady = 'true';

        const valueInput = picker.querySelector('[data-asset-picker-value]');
        const clearInput = picker.querySelector('[data-asset-picker-clear-value]');
        const uploadInput = picker.querySelector('[data-asset-picker-upload]');
        const library = picker.querySelector('[data-asset-picker-library]');
        const toggle = picker.querySelector('[data-archive-file-library]');
        const clearButton = picker.querySelector('[data-archive-file-clear]');

        function syncCard(name, url, icon) {
            picker.dataset.initialName = name || '';
            picker.dataset.initialUrl = url || '';
            picker.dataset.initialIcon = icon || 'bi bi-file-earmark-image-fill';
            if (uploadInput) uploadInput.dispatchEvent(new Event('change', { bubbles: true }));
        }

        function closeLibrary() {
            if (!library || library.hidden) return;
            library.hidden = true;
            picker.classList.remove('is-library-open');
            if (toggle) toggle.setAttribute('aria-expanded', 'false');
        }

        function openLibrary() {
            if (!library) return;
            library.hidden = false;
            picker.classList.add('is-library-open');
            if (toggle) toggle.setAttribute('aria-expanded', 'true');
            const search = library.querySelector('[data-asset-picker-search]');
            if (search) search.focus();
        }

        if (toggle && library) {
            toggle.addEventListener('click', function (event) {
                event.preventDefault();
                event.stopPropagation();
                if (library.hidden) openLibrary();
                else closeLibrary();
            });
            document.addEventListener('click', function (event) {
                if (!picker.contains(event.target)) closeLibrary();
            });
            picker.addEventListener('keydown', function (event) {
                if (event.key === 'Escape') {
                    closeLibrary();
                    if (toggle) toggle.focus();
                }
            });
        }

        picker.querySelectorAll('[data-asset-picker-option]').forEach(function (option) {
            option.addEventListener('click', function () {
                picker.querySelectorAll('[data-asset-picker-option]').forEach(function (item) {
                    item.classList.remove('is-selected');
                });
                option.classList.add('is-selected');
                valueInput.value = option.dataset.assetId || '';
                clearInput.checked = false;
                if (uploadInput) uploadInput.value = '';
                syncCard(
                    option.dataset.assetName,
                    option.dataset.assetUrl,
                    picker.dataset.assetKind === 'font' ? 'bi bi-file-earmark-font-fill' : 'bi bi-file-earmark-image-fill'
                );
                closeLibrary();
                valueInput.dispatchEvent(new Event('change', { bubbles: true }));
            });
        });

        const search = picker.querySelector('[data-asset-picker-search]');
        if (search) {
            search.addEventListener('input', function () {
                const query = search.value.trim().toLowerCase();
                picker.querySelectorAll('[data-asset-picker-option]').forEach(function (option) {
                    option.hidden = query && !(option.dataset.assetName || '').toLowerCase().includes(query);
                });
            });
        }

        if (uploadInput) {
            uploadInput.addEventListener('change', function () {
                const file = uploadInput.files && uploadInput.files[0];
                if (!file) return;
                picker.dataset.assetFallbackId = valueInput.value || '';
                picker.dataset.assetFallbackName = picker.dataset.initialName || '';
                picker.dataset.assetFallbackUrl = picker.dataset.initialUrl || '';
                picker.dataset.assetFallbackIcon = picker.dataset.initialIcon || '';
                valueInput.value = '';
                clearInput.checked = false;
                picker.querySelectorAll('[data-asset-picker-option]').forEach(function (item) {
                    item.classList.remove('is-selected');
                });
            });
        }

        if (clearButton) {
            clearButton.addEventListener('pointerdown', function () {
                picker.dataset.assetClearingUpload = uploadInput && uploadInput.files && uploadInput.files.length ? 'true' : 'false';
            });
            clearButton.addEventListener('click', function () {
                if (picker.dataset.assetClearingUpload === 'true') {
                    valueInput.value = picker.dataset.assetFallbackId || '';
                    clearInput.checked = false;
                    syncCard(
                        picker.dataset.assetFallbackName,
                        picker.dataset.assetFallbackUrl,
                        picker.dataset.assetFallbackIcon
                    );
                    return;
                }
                valueInput.value = '';
                clearInput.checked = true;
                picker.dataset.initialName = '';
                picker.dataset.initialUrl = '';
                picker.querySelectorAll('[data-asset-picker-option]').forEach(function (item) {
                    item.classList.remove('is-selected');
                });
                if (uploadInput) uploadInput.dispatchEvent(new Event('change', { bubbles: true }));
                valueInput.dispatchEvent(new Event('change', { bubbles: true }));
            });
        }
    }

    function initializeAll(root) {
        (root || document).querySelectorAll('[data-asset-picker]').forEach(initializePicker);
    }

    document.addEventListener('DOMContentLoaded', function () { initializeAll(document); });
    new MutationObserver(function (mutations) {
        mutations.forEach(function (mutation) {
            mutation.addedNodes.forEach(function (node) {
                if (node.nodeType !== 1) return;
                if (node.matches?.('[data-asset-picker]')) initializePicker(node);
                initializeAll(node);
            });
        });
    }).observe(document.documentElement, { childList: true, subtree: true });
}());
