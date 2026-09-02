(function () {
    if (window.__dluxManagedAssetsInitialized) return;
    window.__dluxManagedAssetsInitialized = true;

    function csrfToken() {
        const input = document.querySelector('#universalDynamicModalBody input[name="csrfmiddlewaretoken"]');
        if (input) return input.value;
        const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : '';
    }

    function closeEditor(input, titleButton, title) {
        input.value = title;
        input.hidden = true;
        titleButton.textContent = title;
        titleButton.hidden = false;
        delete input.dataset.saving;
    }

    function saveTitle(input) {
        if (input.dataset.saving === 'true') return;
        const container = input.closest('.dlux-managed-asset-name');
        const titleButton = container && container.querySelector('[data-managed-image-title]');
        if (!titleButton) return;
        const title = input.value.trim();
        if (!title || title === titleButton.textContent.trim()) {
            closeEditor(input, titleButton, title || titleButton.textContent.trim());
            return;
        }

        input.dataset.saving = 'true';
        input.disabled = true;
        const body = new FormData();
        body.append('title', title);
        fetch(titleButton.dataset.renameUrl, {
            method: 'POST',
            body: body,
            headers: {
                'Accept': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': csrfToken(),
            },
        })
            .then(function (response) {
                return response.json().then(function (data) {
                    if (!response.ok || !data.success) throw new Error(data.error || 'Failed to rename image.');
                    return data;
                });
            })
            .then(function (data) {
                closeEditor(input, titleButton, data.title);
            })
            .catch(function (error) {
                delete input.dataset.saving;
                input.disabled = false;
                input.focus();
                window.alert(error.message);
            })
            .finally(function () {
                input.disabled = false;
            });
    }

    function s(key, fallback) {
        const value = (window.DLUX_STRINGS || {})[key];
        return (typeof value === 'string' && value.length) ? value : fallback;
    }

    function prune(button) {
        if (button.dataset.pruning === 'true') return;
        button.dataset.pruning = 'true';
        const post = function (confirmed) {
            const body = new FormData();
            if (confirmed) body.append('confirm', '1');
            return fetch(button.dataset.pruneUrl, {
                method: 'POST',
                body: body,
                headers: {
                    'Accept': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': csrfToken(),
                },
            }).then(function (response) {
                return response.json().then(function (data) {
                    if (!response.ok || !data.success) throw new Error(data.error || s('asset_prune_failed', 'Clean-up failed.'));
                    return data;
                });
            });
        };

        // Ask first, and name what is going: the preview is the whole point of
        // a two-step delete.
        post(false).then(function (preview) {
            if (!preview.count) {
                window.alert(preview.message || s('asset_prune_none', 'No unused files to clean up.'));
                return null;
            }
            const listed = (preview.titles || []).join('\n');
            const question = s('asset_prune_confirm', 'Permanently delete {count} unused file(s)?')
                .replace('{count}', String(preview.count));
            if (!window.confirm(listed ? (question + '\n\n' + listed) : question)) return null;
            return post(true);
        }).then(function (result) {
            if (!result) return;
            if (window.showToast && result.message) window.showToast(result.message);
            // Same refresh the upload path uses, so the grid and counts agree.
            const nav = document.querySelector('[data-dlux-modal-nav] a[aria-current="page"], [data-dlux-modal-nav] a.active');
            if (nav) { nav.click(); } else { window.location.reload(); }
        }).catch(function (error) {
            window.alert(error.message);
        }).finally(function () {
            delete button.dataset.pruning;
        });
    }

    document.addEventListener('click', function (event) {
        const pruneButton = event.target.closest('[data-asset-prune]');
        if (pruneButton) {
            event.preventDefault();
            prune(pruneButton);
            return;
        }

        const uploadButton = event.target.closest('[data-managed-image-upload-trigger]');
        if (uploadButton) {
            event.preventDefault();
            const form = uploadButton.form;
            const input = form && form.querySelector('[data-managed-image-input]');
            if (input) input.click();
            return;
        }

        const titleButton = event.target.closest('[data-managed-image-title]');
        if (!titleButton) return;
        const input = titleButton.parentElement.querySelector('[data-managed-image-title-input]');
        if (!input) return;
        titleButton.hidden = true;
        input.hidden = false;
        input.focus();
        input.select();
    });

    document.addEventListener('change', function (event) {
        const input = event.target.closest('[data-managed-image-input]');
        if (!input || !input.files.length || !input.form) return;
        const submitter = document.querySelector(`[data-managed-image-upload-trigger][form="${input.form.id}"]`)
            || input.form.querySelector('[data-managed-image-upload-trigger]');
        input.form.requestSubmit(submitter || undefined);
    });

    document.addEventListener('keydown', function (event) {
        const input = event.target.closest('[data-managed-image-title-input]');
        if (!input) return;
        if (event.key === 'Escape') {
            event.preventDefault();
            input.dataset.cancel = 'true';
            const titleButton = input.parentElement.querySelector('[data-managed-image-title]');
            closeEditor(input, titleButton, titleButton.textContent.trim());
        } else if (event.key === 'Enter') {
            event.preventDefault();
            saveTitle(input);
        }
    });

    document.addEventListener('focusout', function (event) {
        const input = event.target.closest('[data-managed-image-title-input]');
        if (!input) return;
        if (input.dataset.cancel === 'true') {
            delete input.dataset.cancel;
            return;
        }
        saveTitle(input);
    });
}());
