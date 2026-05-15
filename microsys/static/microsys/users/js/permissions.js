(function() {
    function initPermissionWidget() {
        // Master Checkbox Logic: App Level
        // Using event delegation on document body for dynamic content
    }

    function parsePreviewConfig(previewEl) {
        const raw = previewEl?.dataset?.tierPreviewConfig;
        if (!raw) return null;
        try {
            return JSON.parse(raw);
        } catch (_error) {
            return null;
        }
    }

    function computePreviewState(config, root) {
        const isStaffCheckbox = root.querySelector('input[name="is_staff"]');
        const manageScopesCheckbox = root.querySelector('.permission-checkbox[data-codename="manage_scopes"]');
        const manageStaffCheckbox = root.querySelector('.permission-checkbox[data-codename="manage_staff"]');
        const form = root.closest('form');
        const scopeFieldName = config?.scope_field_name || '';
        const scopeField = scopeFieldName && form ? form.querySelector(`[name="${scopeFieldName}"]`) : null;

        let hasScope = Boolean(config?.fixed_scope_active);
        let scopeLabel = config?.fixed_scope_label || '';
        if (!config?.scope_locked && scopeField && scopeField.tagName === 'SELECT') {
            const selectedOption = scopeField.options[scopeField.selectedIndex];
            if (scopeField.value) {
                hasScope = true;
                scopeLabel = selectedOption ? selectedOption.textContent.trim() : scopeLabel;
            } else if (!config?.fixed_scope_active) {
                hasScope = false;
                scopeLabel = '';
            }
        }

        const isSuperuser = Boolean(config?.forced_superuser);
        const isStaff = isSuperuser || Boolean(isStaffCheckbox?.checked);
        const hasManageScopes = Boolean(manageScopesCheckbox?.checked);
        const hasManageStaff = Boolean(manageStaffCheckbox?.checked);

        let tierKey = 'regular_user';
        if (isSuperuser) {
            tierKey = 'superuser';
        } else if (!isStaff) {
            tierKey = 'regular_user';
        } else if (hasScope) {
            tierKey = 'scoped_staff';
        } else if (hasManageScopes) {
            tierKey = 'global_staff';
        } else {
            tierKey = 'central_staff';
        }

        const warnings = [];
        if (!isStaff && (hasManageScopes || hasManageStaff) && config?.catalog?.warnings?.needs_staff) {
            warnings.push(config.catalog.warnings.needs_staff);
        }
        if (isStaff && hasScope && hasManageScopes && config?.catalog?.warnings?.scoped_manage_scopes_conflict) {
            warnings.push(config.catalog.warnings.scoped_manage_scopes_conflict);
        }

        return {
            tierKey,
            isSuperuser,
            isStaff,
            hasScope,
            scopeLabel,
            hasManageScopes,
            hasManageStaff,
            canDelegateStaff: Boolean(isStaff && hasManageStaff),
            warnings,
        };
    }

    function renderTierPreview(previewEl) {
        const config = parsePreviewConfig(previewEl);
        if (!config?.catalog?.tiers) return;

        const state = computePreviewState(config, previewEl.closest('.grouped-permissions-widget') || previewEl);
        const tier = config.catalog.tiers[state.tierKey];
        if (!tier) return;

        const titleEl = previewEl.querySelector('.ms-staff-tier-preview__title');
        const descriptionEl = previewEl.querySelector('.ms-staff-tier-preview__description');
        const badgesEl = previewEl.querySelector('.ms-staff-tier-preview__badges');
        const capabilitiesEl = previewEl.querySelector('.ms-staff-tier-preview__capabilities');
        const warningsEl = previewEl.querySelector('.ms-staff-tier-preview__warnings');

        if (titleEl) {
            titleEl.textContent = tier.title;
        }
        if (descriptionEl) {
            descriptionEl.textContent = tier.description;
        }
        if (badgesEl) {
            const badges = [
                `<span class="badge ${tier.badge_classes}"><i class="bi ${tier.icon} me-1"></i>${tier.title}</span>`,
            ];
            if (state.canDelegateStaff) {
                badges.push(`<span class="badge bg-light text-primary border">${config.catalog.delegation_badge_label}</span>`);
            }
            if (state.hasScope && state.scopeLabel) {
                badges.push(`<span class="badge bg-light text-secondary border">${state.scopeLabel}</span>`);
            }
            badgesEl.innerHTML = badges.join('');
        }
        if (capabilitiesEl) {
            capabilitiesEl.innerHTML = (tier.capabilities || [])
                .map(item => `<li>${item}</li>`)
                .join('');
        }
        if (warningsEl) {
            warningsEl.innerHTML = (state.warnings || [])
                .map(message => `<div class="ms-staff-tier-preview__warning"><i class="bi bi-exclamation-triangle-fill"></i>${message}</div>`)
                .join('');
        }
    }

    function syncTierPreviews(root) {
        (root || document).querySelectorAll('.ms-staff-tier-preview').forEach(renderTierPreview);
    }

    // Attach to document for event delegation
    document.body.addEventListener('change', function(e) {
        // App Level Master
        if (e.target.matches('.app-master-checkbox')) {
            const isChecked = e.target.checked;
            const card = e.target.closest('.permissions-card');
            card.querySelectorAll('.permission-checkbox, .model-master-checkbox').forEach(cb => {
                if (cb.disabled) return;
                cb.checked = isChecked;
                cb.indeterminate = false;
            });
        }

        // Model Level Master
        if (e.target.matches('.model-master-checkbox')) {
            const isChecked = e.target.checked;
            const modelGroup = e.target.closest('.model-group');
            modelGroup.querySelectorAll('.permission-checkbox').forEach(cb => {
                if (cb.disabled) return;
                cb.checked = isChecked;
            });
            updateAppMasterStatus(e.target.closest('.permissions-card'));
        }

        // Individual Permission Checkbox
        if (e.target.matches('.permission-checkbox')) {
            updateModelMasterStatus(e.target.closest('.model-group'));
            updateAppMasterStatus(e.target.closest('.permissions-card'));
        }

        if (e.target.matches('.permission-checkbox, .model-master-checkbox, .app-master-checkbox, input[name="is_staff"], [name="scope"]')) {
            syncTierPreviews(e.target.closest('form') || document);
        }
    });

    // Delegate Click for toggling
    document.body.addEventListener('click', function(e) {
        const header = e.target.closest('.permissions-card-header');
        if (header) {
            if (e.target.closest('.prevent-toggle')) return;
            
            const targetId = header.getAttribute('data-bs-target');
            const target = document.querySelector(targetId);
            if (target) {
                const isCollapsed = !target.classList.contains('show');
                if (!isCollapsed) {
                    header.classList.add('collapsed');
                    bootstrap.Collapse.getOrCreateInstance(target).hide();
                } else {
                    header.classList.remove('collapsed');
                    bootstrap.Collapse.getOrCreateInstance(target).show();
                }
            }
        }
    });

    function updateModelMasterStatus(modelGroup) {
        if (!modelGroup) return;
        const master = modelGroup.querySelector('.model-master-checkbox');
        if (!master) return;
        const children = Array.from(modelGroup.querySelectorAll('.permission-checkbox')).filter(c => !c.disabled);
        const checkedCount = children.filter(c => c.checked).length;

        master.checked = checkedCount === children.length && children.length > 0;
        master.indeterminate = checkedCount > 0 && checkedCount < children.length;
    }

    function updateAppMasterStatus(card) {
        if (!card) return;
        const master = card.querySelector('.app-master-checkbox');
        if (!master) return;
        const children = Array.from(card.querySelectorAll('.permission-checkbox')).filter(c => !c.checked);
        const allChildren = Array.from(card.querySelectorAll('.permission-checkbox')).filter(c => !c.disabled);
        const checkedCount = allChildren.length - children.length;

        master.checked = checkedCount === allChildren.length && allChildren.length > 0;
        master.indeterminate = checkedCount > 0 && checkedCount < allChildren.length;
    }

    // Export sync functions to window just in case
    window.syncPermissionsStatus = function(container) {
        const root = container || document;
        root.querySelectorAll('.model-group').forEach(group => updateModelMasterStatus(group));
        root.querySelectorAll('.permissions-card').forEach(card => updateAppMasterStatus(card));
        syncTierPreviews(root);
    };

    // Initial sync for whatever is present
    setTimeout(window.syncPermissionsStatus, 100);

})();
