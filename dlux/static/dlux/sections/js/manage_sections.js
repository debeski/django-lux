document.addEventListener('DOMContentLoaded', function () {
    const sectionDataEl = document.getElementById('sectionData');
    const sectionData = sectionDataEl ? JSON.parse(sectionDataEl.textContent) : {};
    const panel = document.querySelector('[data-dlux-section-form-panel]');
    const form = document.querySelector('[data-dlux-section-form]');
    const addTriggers = document.querySelectorAll('[data-dlux-section-add]');

    const snapshotForm = function (targetForm) {
        if (!targetForm) {
            return '';
        }
        return Array.from(targetForm.elements)
            .filter(function (element) {
                return element.name && !element.disabled;
            })
            .map(function (element) {
                if (element.type === 'checkbox' || element.type === 'radio') {
                    return [element.name, element.value, element.checked ? '1' : '0'].join('=');
                }
                if (element.tagName === 'SELECT' && element.multiple) {
                    const selected = Array.from(element.selectedOptions).map(function (option) {
                        return option.value;
                    });
                    return [element.name, selected.join(',')].join('=');
                }
                return [element.name, element.value].join('=');
            })
            .join('&');
    };

    let initialSnapshot = snapshotForm(form);

    const formIsDirty = function () {
        return form && snapshotForm(form) !== initialSnapshot;
    };

    window.dluxConfirmSectionFormNavigation = function () {
        return !formIsDirty() || window.confirm(sectionData.unsavedMessage || 'Discard unsaved section changes?');
    };

    const focusFirstField = function () {
        if (!panel) {
            return;
        }
        const target = panel.querySelector('input:not([type="hidden"]):not([disabled]), select:not([disabled]), textarea:not([disabled]), button:not([disabled])');
        if (target) {
            target.focus({ preventScroll: true });
        }
    };

    const showPanel = function (href) {
        if (!panel) {
            return;
        }
        if (window.bootstrap && window.bootstrap.Collapse) {
            const collapse = window.bootstrap.Collapse.getOrCreateInstance(panel, { toggle: false });
            panel.addEventListener('shown.bs.collapse', focusFirstField, { once: true });
            collapse.show();
        } else {
            panel.classList.add('show');
            panel.style.display = 'block';
            focusFirstField();
        }
        addTriggers.forEach(function (trigger) {
            trigger.setAttribute('aria-expanded', 'true');
        });
        if (href && window.history && window.history.pushState) {
            window.history.pushState({}, '', href);
        }
    };

    if (sectionData.formOpen) {
        window.setTimeout(focusFirstField, 0);
    }

    addTriggers.forEach(function (trigger) {
        trigger.addEventListener('click', function (event) {
            if (!form || form.dataset.dluxSectionFormMode === 'edit') {
                if (!window.dluxConfirmSectionFormNavigation()) {
                    event.preventDefault();
                }
                return;
            }

            if (!window.dluxConfirmSectionFormNavigation()) {
                event.preventDefault();
                return;
            }

            event.preventDefault();
            initialSnapshot = snapshotForm(form);
            showPanel(trigger.href);
        });
    });

    document.querySelectorAll('[data-dlux-section-cancel]').forEach(function (trigger) {
        trigger.addEventListener('click', function (event) {
            if (!window.dluxConfirmSectionFormNavigation()) {
                event.preventDefault();
            }
        });
    });

    [
        ['id_type', 'id_name'],
        ['id_subtype', 'id_subname'],
    ].forEach(function ([sourceId, targetId]) {
        const source = document.getElementById(sourceId);
        const target = document.getElementById(targetId);

        if (!source || !target) {
            return;
        }

        source.addEventListener('change', function () {
            const label = source.options[source.selectedIndex]?.text || '';
            target.value = `${label} `;
            target.focus();
            target.setSelectionRange(target.value.length, target.value.length);
        });
    });

    if (typeof window.initDluxDatepickers === 'function') {
        window.initDluxDatepickers(document);
    }

    if (window.bootstrap && window.bootstrap.Tooltip) {
        document.querySelectorAll('.subsection-help[data-bs-toggle="tooltip"]').forEach(function (element) {
            window.bootstrap.Tooltip.getOrCreateInstance(element, { container: 'body' });
        });
    }
});
