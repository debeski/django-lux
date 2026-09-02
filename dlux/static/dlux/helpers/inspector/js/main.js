(function (root) {
    'use strict';

    const DEFAULT_STRINGS = {
        clearSelection: 'Clear selection',
        empty: 'Select an item to edit it.',
    };

    const FIELD_TYPES = ['text', 'url', 'number', 'email', 'textarea', 'select', 'toggle', 'localized-text', 'custom'];

    function isObject(value) {
        return value && typeof value === 'object' && !Array.isArray(value);
    }

    function asArray(value) {
        if (Array.isArray(value)) return value;
        if (value === undefined || value === null) return [];
        return [value];
    }

    function asText(value) {
        return value === undefined || value === null ? '' : String(value);
    }

    const POPOVER_GAP = 8;

    // The band the element can actually be seen in: the viewport, narrowed by every
    // scrolling or clipping ancestor. Measuring against the viewport alone is what
    // put the panel outside a scrollable modal body — there was room on screen, but
    // none inside the box that does the clipping.
    function visibleBounds(element) {
        const doc = element.ownerDocument;
        const view = doc && doc.defaultView;
        let top = 0;
        let bottom = (view && view.innerHeight)
            || (doc && doc.documentElement && doc.documentElement.clientHeight)
            || 0;
        if (!view || typeof view.getComputedStyle !== 'function') return { top, bottom };
        let node = element.parentElement;
        while (node && node !== doc.body) {
            const overflowY = view.getComputedStyle(node).overflowY;
            if (overflowY === 'auto' || overflowY === 'scroll' || overflowY === 'hidden') {
                const rect = node.getBoundingClientRect();
                top = Math.max(top, rect.top);
                bottom = Math.min(bottom, rect.bottom);
            }
            node = node.parentElement;
        }
        return { top, bottom };
    }

    function isAnchorClipped(anchorRect, bounds) {
        return anchorRect.bottom <= bounds.top || anchorRect.top >= bounds.bottom;
    }

    function mergeOptions(options) {
        const merged = Object.assign({
            actionsPlacement: 'host',
            adapter: {},
            className: '',
            defaultCommitOn: 'change',
            dismissIgnoreSelector: '',
            dismissOnOutsideClick: false,
            includeClearAction: true,
            presentation: 'inline',
            showEmpty: false,
            strings: {},
        }, options || {});
        merged.strings = Object.assign({}, DEFAULT_STRINGS, merged.strings || {});
        return merged;
    }

    function resolveElement(target) {
        if (!target) return null;
        if (typeof target === 'string') return document.querySelector(target);
        return target;
    }

    function callMaybe(fn, context, fallback) {
        if (typeof fn !== 'function') return fallback;
        const result = fn(context);
        return result === undefined ? fallback : result;
    }

    function boolValue(value) {
        return value === true || value === 'true' || value === '1' || value === 1;
    }

    function addIcon(button, icon) {
        const classes = asText(icon).split(/\s+/).filter(Boolean);
        if (!classes.length) return;
        const node = document.createElement('i');
        node.setAttribute('aria-hidden', 'true');
        classes.forEach((name) => {
            if (/^[A-Za-z0-9_-]+$/.test(name)) node.classList.add(name);
        });
        if (!node.classList.length) return;
        if (!node.classList.contains('bi') && classes.some((name) => name.indexOf('bi-') === 0)) {
            node.classList.add('bi');
        }
        button.appendChild(node);
    }

    function makeFieldShell(field) {
        const wrapper = document.createElement('div');
        wrapper.className = [
            'dlux-inspector-shell__field',
            field.fullWidth ? 'dlux-inspector-shell__field--full' : '',
            field.className || '',
        ].filter(Boolean).join(' ');
        wrapper.dataset.inspectorField = field.id || '';
        return wrapper;
    }

    function makeLabel(field, targetId, fallback) {
        const label = document.createElement('label');
        label.className = 'form-label small fw-semibold mb-1';
        if (targetId) label.setAttribute('for', targetId);
        label.textContent = asText(field.label || fallback || field.id);
        return label;
    }

    function applyControlState(control, field) {
        if (field.disabled) control.disabled = true;
        if (field.readOnly || field.readonly) control.readOnly = true;
        if (field.required) control.required = true;
        if (field.name) control.name = field.name;
        if (field.placeholder) control.placeholder = field.placeholder;
        if (field.autocomplete) control.autocomplete = field.autocomplete;
        if (field.ariaLabel) control.setAttribute('aria-label', field.ariaLabel);
    }

    function renderHelp(wrapper, field) {
        if (!field.helpText && !field.help) return;
        const help = document.createElement('div');
        help.className = 'form-text';
        help.textContent = asText(field.helpText || field.help);
        wrapper.appendChild(help);
    }

    function commitForEvent(shell, field, eventName, context) {
        const commitOn = field.commitOn === undefined ? shell.options.defaultCommitOn : field.commitOn;
        if (commitOn === eventName || (eventName === 'change' && commitOn === true)) {
            shell.commit(Object.assign({}, context, { reason: eventName }));
        }
    }

    function handleResult(shell, result, context) {
        if (!isObject(result)) return;
        if (result.clearSelection) shell.clearSelection(context);
        if (result.commit) shell.commit(Object.assign({}, context, { reason: result.reason || context.reason }));
        if (result.render) shell.render();
    }

    function bindControl(shell, control, field, valueGetter, extraContext) {
        const eventContext = (event, eventName) => Object.assign({
            event,
            field,
            fieldId: field.id,
            selection: shell.selection,
            value: valueGetter(),
            reason: eventName,
            shell: shell.api,
        }, extraContext || {});

        if (field.onInput || field.commitOn === 'input') {
            control.addEventListener('input', (event) => {
                const context = eventContext(event, 'input');
                const result = callMaybe(field.onInput, context, null);
                handleResult(shell, result, context);
                if (!isObject(result) || !result.commit) commitForEvent(shell, field, 'input', context);
            });
        }

        control.addEventListener('change', (event) => {
            const context = eventContext(event, 'change');
            const result = callMaybe(field.onChange, context, null);
            handleResult(shell, result, context);
            if (!isObject(result) || !result.commit) commitForEvent(shell, field, 'change', context);
        });
    }

    function renderTextField(shell, field) {
        const wrapper = makeFieldShell(field);
        const id = shell.nextId(field.id || 'text');
        wrapper.appendChild(makeLabel(field, id));
        const input = document.createElement('input');
        input.type = field.inputType || field.type || 'text';
        input.id = id;
        input.className = field.controlClassName || 'form-control glass-input';
        input.value = asText(field.value);
        applyControlState(input, field);
        bindControl(shell, input, field, () => input.value);
        wrapper.appendChild(input);
        renderHelp(wrapper, field);
        return wrapper;
    }

    function renderTextareaField(shell, field) {
        const wrapper = makeFieldShell(Object.assign({ fullWidth: true }, field));
        const id = shell.nextId(field.id || 'textarea');
        wrapper.appendChild(makeLabel(field, id));
        const textarea = document.createElement('textarea');
        textarea.id = id;
        textarea.className = field.controlClassName || 'form-control glass-input';
        textarea.value = asText(field.value);
        if (field.rows) textarea.rows = field.rows;
        applyControlState(textarea, field);
        bindControl(shell, textarea, field, () => textarea.value);
        wrapper.appendChild(textarea);
        renderHelp(wrapper, field);
        return wrapper;
    }

    function renderSelectField(shell, field) {
        const wrapper = makeFieldShell(field);
        const id = shell.nextId(field.id || 'select');
        wrapper.appendChild(makeLabel(field, id));
        const select = document.createElement('select');
        select.id = id;
        select.className = field.controlClassName || 'form-select glass-input';
        applyControlState(select, field);
        asArray(field.options).forEach((option) => {
            const item = isObject(option) ? option : { value: option, label: option };
            const node = document.createElement('option');
            node.value = asText(item.value);
            node.textContent = asText(item.label);
            node.disabled = Boolean(item.disabled);
            if (asText(item.value) === asText(field.value)) node.selected = true;
            select.appendChild(node);
        });
        bindControl(shell, select, field, () => select.value);
        wrapper.appendChild(select);
        renderHelp(wrapper, field);
        return wrapper;
    }

    function renderToggleField(shell, field) {
        const wrapper = makeFieldShell(field);
        const id = shell.nextId(field.id || 'toggle');
        const row = document.createElement('div');
        row.className = 'form-check form-switch dlux-inspector-shell__toggle';
        const input = document.createElement('input');
        input.type = 'checkbox';
        input.className = 'form-check-input';
        input.id = id;
        input.checked = boolValue(field.value);
        applyControlState(input, field);
        bindControl(shell, input, field, () => input.checked);
        const label = document.createElement('label');
        label.className = 'form-check-label fw-semibold';
        label.setAttribute('for', id);
        label.textContent = asText(field.label || field.id);
        row.appendChild(input);
        row.appendChild(label);
        wrapper.appendChild(row);
        renderHelp(wrapper, field);
        return wrapper;
    }

    function languageCode(language) {
        if (Array.isArray(language)) return language[0];
        if (isObject(language)) return language.code || language.value || language.id || language.key;
        return language;
    }

    function languageLabel(language) {
        if (Array.isArray(language)) return language[1] && (language[1].label || language[1].name) || language[0];
        if (isObject(language)) return language.label || language.name || language.code || language.value;
        return language;
    }

    function renderLocalizedTextField(shell, field) {
        const wrapper = makeFieldShell(Object.assign({ fullWidth: true }, field));
        if (field.label) wrapper.appendChild(makeLabel(field, null));
        const grid = document.createElement('div');
        grid.className = 'dlux-inspector-shell__localized-grid';
        const values = field.values || {};
        asArray(field.languages).forEach((language) => {
            const code = asText(languageCode(language));
            if (!code) return;
            const item = makeFieldShell({ id: `${field.id || 'localized'}-${code}` });
            const id = shell.nextId(`${field.id || 'localized'}-${code}`);
            item.appendChild(makeLabel({ label: languageLabel(language), id: code }, id));
            const control = document.createElement('input');
            control.type = field.inputType || 'text';
            control.id = id;
            control.className = field.controlClassName || 'form-control glass-input';
            control.value = asText(values[code]);
            applyControlState(control, field);
            bindControl(shell, control, field, () => control.value, { language: code });
            item.appendChild(control);
            grid.appendChild(item);
        });
        wrapper.appendChild(grid);
        renderHelp(wrapper, field);
        return wrapper;
    }

    function renderCustomField(shell, field) {
        const wrapper = makeFieldShell(field);
        const context = {
            field,
            fieldId: field.id,
            selection: shell.selection,
            shell: shell.api,
            wrapper,
        };
        const rendered = callMaybe(field.render, context, null);
        const NodeClass = root.Node || null;
        if (NodeClass && rendered instanceof NodeClass) {
            wrapper.appendChild(rendered);
        } else if (NodeClass && isObject(rendered) && rendered.node instanceof NodeClass) {
            wrapper.appendChild(rendered.node);
            if (typeof rendered.cleanup === 'function') shell.cleanups.push(rendered.cleanup);
        }
        renderHelp(wrapper, field);
        return wrapper;
    }

    function renderField(shell, field) {
        const type = field.type || 'text';
        if (type === 'textarea') return renderTextareaField(shell, field);
        if (type === 'select') return renderSelectField(shell, field);
        if (type === 'toggle') return renderToggleField(shell, field);
        if (type === 'localized-text') return renderLocalizedTextField(shell, field);
        if (type === 'custom') return renderCustomField(shell, field);
        return renderTextField(shell, field);
    }

    function normalizeAction(action) {
        if (!action || action.hidden) return null;
        return Object.assign({
            icon: '',
            label: action.id || '',
            variant: 'outline-secondary',
        }, action);
    }

    // A switch in the action row. Some hosts have no builder-level toolbar to put a
    // per-entry on/off control in, so it rides with the actions it belongs beside.
    function renderToggleAction(shell, action) {
        const wrap = document.createElement('div');
        wrap.className = [
            'form-check form-switch dlux-inspector-shell__action-toggle',
            action.alignEnd ? 'dlux-inspector-shell__action--end' : '',
            action.className || '',
        ].filter(Boolean).join(' ');
        wrap.dataset.inspectorAction = action.id || '';
        const id = shell.nextId(action.id || 'toggle-action');
        const input = document.createElement('input');
        input.type = 'checkbox';
        input.role = 'switch';
        input.className = 'form-check-input';
        input.id = id;
        input.checked = boolValue(action.checked);
        input.disabled = Boolean(action.disabled);
        const label = document.createElement('label');
        label.className = 'form-check-label fw-semibold';
        label.setAttribute('for', id);
        label.textContent = asText(action.label);
        if (action.title) wrap.title = action.title;
        input.addEventListener('change', (event) => {
            const context = {
                action,
                actionId: action.id,
                event,
                reason: 'action',
                selection: shell.selection,
                shell: shell.api,
                value: input.checked,
            };
            shell.dispatch('action', context);
            handleResult(shell, callMaybe(action.onChange || action.onClick || action.run, context, null), context);
        });
        wrap.appendChild(input);
        wrap.appendChild(label);
        return wrap;
    }

    function renderAction(shell, action) {
        if (action.type === 'toggle') return renderToggleAction(shell, action);
        const button = document.createElement('button');
        button.type = 'button';
        button.className = [
            'btn',
            action.size ? `btn-${action.size}` : 'btn-sm',
            action.variant && action.variant.indexOf('btn-') === 0 ? action.variant : `btn-${action.variant || 'outline-secondary'}`,
            action.alignEnd ? 'dlux-inspector-shell__action--end' : '',
            action.className || '',
        ].filter(Boolean).join(' ');
        button.dataset.inspectorAction = action.id || '';
        button.disabled = Boolean(action.disabled);
        if (action.title) button.title = action.title;
        if (action.ariaLabel || action.label) button.setAttribute('aria-label', action.ariaLabel || action.label);
        addIcon(button, action.icon);
        if (!action.iconOnly) {
            const label = document.createElement('span');
            label.textContent = asText(action.label);
            button.appendChild(label);
        }
        button.addEventListener('click', (event) => {
            const context = {
                action,
                actionId: action.id,
                event,
                reason: 'action',
                selection: shell.selection,
                shell: shell.api,
            };
            shell.dispatch('action', context);
            handleResult(shell, callMaybe(action.onClick || action.run, context, null), context);
        });
        return button;
    }

    function createInspectorShell(target, options) {
        const container = resolveElement(target);
        if (!container) throw new Error('DluxInspectorShell requires a container element.');

        const shell = {
            cleanups: [],
            container,
            idCounter: 0,
            options: mergeOptions(options),
            selection: null,
            api: null,
        };

        container.classList.add('dlux-inspector-shell');
        container.classList.toggle('dlux-inspector-shell--popover', shell.options.presentation === 'popover');
        if (shell.options.className) container.classList.add(shell.options.className);
        container.dataset.dluxInspectorShell = '';
        container.innerHTML = '';

        const empty = document.createElement('div');
        empty.className = 'dlux-inspector-shell__empty text-muted small';
        empty.textContent = shell.options.strings.empty;

        const panel = document.createElement('div');
        panel.className = 'dlux-inspector-shell__panel';
        const header = document.createElement('div');
        header.className = 'dlux-inspector-shell__header';
        const title = document.createElement('div');
        title.className = 'dlux-inspector-shell__title';
        const subtitle = document.createElement('div');
        subtitle.className = 'dlux-inspector-shell__subtitle text-muted small';
        const badge = document.createElement('span');
        badge.className = 'badge text-bg-light dlux-inspector-shell__badge';
        header.appendChild(title);
        header.appendChild(subtitle);
        header.appendChild(badge);
        const actions = document.createElement('div');
        actions.className = 'dlux-inspector-shell__actions';
        const fields = document.createElement('div');
        fields.className = 'dlux-inspector-shell__fields';
        panel.appendChild(header);
        panel.appendChild(fields);
        container.appendChild(empty);
        container.appendChild(panel);

        // `panel` placement is for hosts with no builder-level toolbar: the actions
        // belong to the entry being inspected, so they travel with its panel.
        function applyActionsPlacement() {
            if (shell.options.actionsPlacement === 'panel') {
                panel.insertBefore(actions, fields);
            } else {
                container.insertBefore(actions, panel);
            }
        }
        applyActionsPlacement();

        shell.elements = { actions, badge, empty, fields, header, panel, subtitle, title };

        shell.nextId = function (suffix) {
            shell.idCounter += 1;
            return `dlux-inspector-${suffix || 'field'}-${shell.idCounter}`;
        };

        shell.dispatch = function (name, detail) {
            container.dispatchEvent(new CustomEvent(`dlux:inspector:${name}`, {
                bubbles: true,
                detail,
            }));
        };

        shell.commit = function (context) {
            const adapter = shell.options.adapter || {};
            shell.dispatch('change', context);
            callMaybe(adapter.commit, Object.assign({}, context, { selection: shell.selection, shell: shell.api }), null);
        };

        shell.clearSelection = function (context) {
            const adapter = shell.options.adapter || {};
            callMaybe(adapter.clearSelection || adapter.onClearSelection, Object.assign({}, context || {}, {
                selection: shell.selection,
                shell: shell.api,
            }), null);
            shell.selection = null;
            shell.render(null);
            shell.dispatch('clear', { shell: shell.api });
        };

        // A popover is anchored to the row it edits, never laid over it. Anchoring
        // to the shell host instead pinned the panel to the top of the builder,
        // where it permanently covered the first entries in the list below.
        shell.positionPanel = function () {
            if (shell.options.presentation !== 'popover') return;
            panel.style.top = '';
            delete panel.dataset.inspectorPlacement;
            if (!shell.selection || panel.hidden) return;

            const adapter = shell.options.adapter || {};
            const anchor = callMaybe(adapter.getAnchor, {
                selection: shell.selection,
                shell: shell.api,
            }, null);
            if (!anchor || typeof anchor.getBoundingClientRect !== 'function') return;

            const anchorRect = anchor.getBoundingClientRect();
            const containerRect = container.getBoundingClientRect();
            // Scrolled out of the box that clips it, the anchor is no longer on
            // screen and a panel still pinned to it would hover over unrelated rows.
            // Keep the panel laid out (so it can come back) but out of sight.
            const anchorBounds = visibleBounds(anchor);
            panel.classList.toggle('is-anchor-offscreen', isAnchorClipped(anchorRect, anchorBounds));

            // The panel's own bounds, not the anchor's: the panel hangs off the shell
            // host, so what may clip it is that element's ancestry (the modal body),
            // not the pane the anchor happens to scroll inside.
            const bounds = visibleBounds(panel);
            // Not `scrollHeight`: an out-of-flow layer inflates a scroll container's
            // overflow without being part of its box, so that read the panel as
            // several times its real size even with everything closed. Measure the
            // panel's own box, then take in any layer actually open over it.
            // The panel's own box, and only that. A field may open a layer over it —
            // an icon picker's dropdown — and that layer is a popover in its own
            // right: it floats outside the panel and is not confined by it, so it is
            // neither measured into the panel's placement nor clipped to it. Never
            // `scrollHeight`, which an out-of-flow layer inflates without being part
            // of the box.
            const naturalHeight = panel.offsetHeight;
            const spaceBelow = bounds.bottom - anchorRect.bottom - POPOVER_GAP;
            const spaceAbove = anchorRect.top - bounds.top - POPOVER_GAP;

            // Below by default; above when there is no room below and there is room
            // above. The panel is never given a height cap: a capped panel scrolls,
            // and a scrolling panel clips the layers its fields open over it. When
            // neither side fits it takes the roomier one and is nudged inside the
            // visible band instead — visible and whole, rather than trimmed.
            const above = naturalHeight > spaceBelow
                && (naturalHeight <= spaceAbove || spaceAbove > spaceBelow);

            const height = naturalHeight;
            let top = above
                ? anchorRect.top - height - POPOVER_GAP
                : anchorRect.bottom + POPOVER_GAP;
            top = Math.max(bounds.top, Math.min(top, bounds.bottom - height));

            panel.style.top = `${Math.round(top - containerRect.top)}px`;
            panel.dataset.inspectorPlacement = above ? 'above' : 'below';
        };

        function handleOutsideClick(event) {
            if (!shell.options.dismissOnOutsideClick || !shell.selection) return;
            const target = event.target;
            if (!target || container.contains(target)) return;
            // Capture phase, so the host's own selection handler has not run yet and
            // the clicked node is still attached: a click that moves the selection
            // must re-anchor the popover, not dismiss it.
            const ignore = shell.options.dismissIgnoreSelector;
            if (ignore && typeof target.closest === 'function' && target.closest(ignore)) return;
            shell.clearSelection({ reason: 'outside-click' });
        }

        // Repositioning reads layout (getBoundingClientRect) and computed styles for
        // every clipping ancestor. Doing that synchronously on a capture-phase scroll
        // listener runs it for every scroll in the document and makes the page drag,
        // so coalesce to one measurement per frame and do nothing at all while there
        // is no open panel to move.
        let reflowQueued = false;
        function handleReflow(event) {
            if (reflowQueued || !shell.selection || panel.hidden) return;
            // A scroll inside the panel cannot move the anchor, so repositioning for
            // it only fights whatever the reader is scrolling — an icon picker's list,
            // for one.
            const target = event && event.target;
            if (target && typeof target.nodeType === 'number' && panel.contains(target)) return;
            reflowQueued = true;
            const run = () => {
                reflowQueued = false;
                shell.positionPanel();
            };
            if (typeof root.requestAnimationFrame === 'function') root.requestAnimationFrame(run);
            else run();
        }

        const ownerDocument = container.ownerDocument || (root.document || null);
        if (ownerDocument && typeof ownerDocument.addEventListener === 'function') {
            ownerDocument.addEventListener('click', handleOutsideClick, true);
        }
        if (root && typeof root.addEventListener === 'function') {
            root.addEventListener('resize', handleReflow);
            // Capture: the anchor usually lives inside a pane that scrolls, and a
            // scroll event on that pane does not bubble to the window.
            root.addEventListener('scroll', handleReflow, true);
        }

        shell.destroy = function () {
            shell.cleanups.splice(0).forEach((cleanup) => cleanup());
            if (ownerDocument && typeof ownerDocument.removeEventListener === 'function') {
                ownerDocument.removeEventListener('click', handleOutsideClick, true);
            }
            if (root && typeof root.removeEventListener === 'function') {
                root.removeEventListener('resize', handleReflow);
                root.removeEventListener('scroll', handleReflow, true);
            }
            container.innerHTML = '';
            container.classList.remove('dlux-inspector-shell');
            delete container.dataset.dluxInspectorShell;
        };

        shell.setOptions = function (nextOptions) {
            shell.options = mergeOptions(Object.assign({}, shell.options, nextOptions || {}));
            container.classList.toggle('dlux-inspector-shell--popover', shell.options.presentation === 'popover');
            applyActionsPlacement();
            shell.render(shell.selection);
        };

        shell.render = function (nextSelection) {
            const adapter = shell.options.adapter || {};
            shell.cleanups.splice(0).forEach((cleanup) => cleanup());
            shell.idCounter = 0;

            const selection = arguments.length
                ? nextSelection
                : callMaybe(adapter.getSelection, { shell: shell.api, selection: shell.selection }, shell.selection);
            shell.selection = selection || null;
            const context = { selection: shell.selection, shell: shell.api };
            const adapterActions = asArray(callMaybe(adapter.getActions, context, []))
                .map(normalizeAction)
                .filter(Boolean);

            if (!shell.selection) {
                actions.innerHTML = '';
                adapterActions.forEach((action) => actions.appendChild(renderAction(shell, action)));
                fields.innerHTML = '';
                header.hidden = true;
                actions.hidden = adapterActions.length === 0;
                fields.hidden = true;
                // The panel holds a selection's header and fields and nothing else,
                // so with no selection it must go away entirely. Tying it to the
                // action count left an empty bordered card sitting under an
                // always-available action such as Nav Bar's Add Group.
                panel.hidden = true;
                empty.hidden = !shell.options.showEmpty || adapterActions.length > 0;
                container.hidden = !shell.options.showEmpty && adapterActions.length === 0;
                return shell.api;
            }

            container.hidden = false;
            empty.hidden = true;
            panel.hidden = false;

            const resolvedTitle = callMaybe(adapter.getTitle, context, '');
            const resolvedSubtitle = callMaybe(adapter.getSubtitle, context, '');
            const resolvedBadge = callMaybe(adapter.getBadge, context, '');
            title.textContent = asText(resolvedTitle);
            subtitle.textContent = asText(resolvedSubtitle);
            badge.textContent = asText(resolvedBadge);
            header.hidden = !resolvedTitle && !resolvedSubtitle && !resolvedBadge;
            subtitle.hidden = !resolvedSubtitle;
            badge.hidden = !resolvedBadge;

            if (shell.options.includeClearAction) {
                adapterActions.push(normalizeAction({
                    id: 'clear-selection',
                    label: shell.options.strings.clearSelection,
                    icon: 'bi bi-x-lg',
                    alignEnd: true,
                    onClick: () => ({ clearSelection: true }),
                }));
            }
            actions.innerHTML = '';
            adapterActions.forEach((action) => actions.appendChild(renderAction(shell, action)));
            actions.hidden = adapterActions.length === 0;

            const fieldSpecs = asArray(callMaybe(adapter.getFields, context, []))
                .filter((field) => isObject(field) && FIELD_TYPES.indexOf(field.type || 'text') !== -1 && !field.hidden);
            fields.innerHTML = '';
            fieldSpecs.forEach((field) => fields.appendChild(renderField(shell, field)));
            fields.hidden = fieldSpecs.length === 0;
            // With the actions inside it, a panel that carries only actions — a strip
            // with nothing to rename, say — still has something to show.
            const panelCarriesActions = shell.options.actionsPlacement === 'panel' && !actions.hidden;
            panel.hidden = header.hidden && fields.hidden && !panelCarriesActions;
            shell.positionPanel();
            shell.dispatch('render', context);
            return shell.api;
        };

        shell.api = {
            clear: shell.clearSelection,
            destroy: shell.destroy,
            elements: shell.elements,
            reposition: shell.positionPanel,
            render: shell.render,
            setOptions: shell.setOptions,
        };

        shell.render();
        return shell.api;
    }

    root.DluxInspectorShell = {
        create: createInspectorShell,
        createInspectorShell,
        fieldTypes: FIELD_TYPES.slice(),
        normalizeAction,
    };
})(typeof window !== 'undefined' ? window : globalThis);
