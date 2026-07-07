/**
 * Dlux live password-rules checker.
 * Shows a live requirements checklist under new-password fields on focus. The
 * rule set adapts to the SystemSettings auth config exposed on
 * window.DLUX_CONFIG:
 * - `enforce_strong_passwords` on  -> configured minimum length
 *   (`strong_password_min_length`, default 12) + upper/lower/digit/symbol,
 *   mirroring dlux.password_validation.DluxStrongPasswordValidator (in sync).
 * - off -> Django's stock checkable rules: at least 8 characters and not
 *   entirely numeric (similarity/common-password checks stay server-side).
 *
 * Targets Django's new-password fields (autocomplete="new-password") so login
 * and current-password fields are excluded; downstream forms can opt in with
 * data-dlux-password-rules. A confirm field (name ending in `password2`, e.g.
 * `password2` / `new_password2`) instead shows a single "passwords match" check
 * against its `...password1` sibling. No network, no inline JS (DSRP-1).
 */
(function () {
    'use strict';

    var SELECTOR = 'input[type="password"][autocomplete="new-password"], input[type="password"][data-dlux-password-rules]';

    function strongEnabled() {
        try { return !!(window.DLUX_CONFIG && window.DLUX_CONFIG.enforce_strong_passwords); }
        catch (_e) { return false; }
    }

    function strongMinLength() {
        try {
            var value = parseInt((window.DLUX_CONFIG || {}).strong_password_min_length, 10);
            if (value >= 8 && value <= 64) { return value; }
        } catch (_e) { /* fall through */ }
        return 12;
    }

    function t(key, fallback) {
        try {
            var s = window.DLUX_STRINGS || {};
            return (typeof s[key] === 'string' && s[key]) ? s[key] : fallback;
        } catch (_e) { return fallback; }
    }

    function minLengthLabel(count) {
        return t('password_rule_min_length', 'At least {count} characters').replace('{count}', String(count));
    }

    function buildRules() {
        if (strongEnabled()) {
            var minLength = strongMinLength();
            return [
                { test: function (v) { return v.length >= minLength; }, label: function () { return minLengthLabel(minLength); } },
                { test: function (v) { return /[A-Z]/.test(v); }, label: function () { return t('password_rule_upper', 'An uppercase letter'); } },
                { test: function (v) { return /[a-z]/.test(v); }, label: function () { return t('password_rule_lower', 'A lowercase letter'); } },
                { test: function (v) { return /[0-9]/.test(v); }, label: function () { return t('password_rule_digit', 'A digit'); } },
                { test: function (v) { return /[^A-Za-z0-9]/.test(v); }, label: function () { return t('password_rule_symbol', 'A symbol'); } }
            ];
        }
        // Normal mode: Django's client-checkable defaults.
        return [
            { test: function (v) { return v.length >= 8; }, label: function () { return minLengthLabel(8); } },
            { test: function (v) { return v.length > 0 && !/^[0-9]+$/.test(v); }, label: function () { return t('password_rule_not_numeric', 'Not entirely numeric'); } }
        ];
    }

    // Resolve the `...password1` sibling for a confirm field named `...password2`.
    function confirmPrimaryFor(input) {
        var name = input.name || '';
        if (!/password2$/i.test(name)) { return null; }
        try {
            var scope = input.form || document;
            return scope.querySelector('input[type="password"][name="' + name.replace(/2$/, '1') + '"]');
        } catch (_e) { return null; }
    }

    function bind(input) {
        if (!input || input.dataset.dluxPwRulesBound === 'true') { return; }
        input.dataset.dluxPwRulesBound = 'true';

        var primary = confirmPrimaryFor(input);
        var rules = primary
            ? [{ test: function (v) { return v.length > 0 && v === primary.value; }, label: function () { return t('password_rule_match', 'Matches the password'); } }]
            : buildRules();

        var box = document.createElement('div');
        box.className = 'dlux-password-rules';
        box.hidden = true;
        box.setAttribute('aria-hidden', 'true');

        var items = rules.map(function (rule) {
            var item = document.createElement('div');
            item.className = 'dlux-password-rules__item';
            var icon = document.createElement('i');
            icon.className = 'bi bi-circle dlux-password-rules__icon';
            icon.setAttribute('aria-hidden', 'true');
            var label = document.createElement('span');
            label.textContent = rule.label();
            item.appendChild(icon);
            item.appendChild(label);
            box.appendChild(item);
            return { item: item, icon: icon, rule: rule };
        });

        var anchor = input.closest('.mb-3, .form-group, .dlux-form-field, .form-floating') || input;
        if (anchor.parentNode) {
            anchor.parentNode.insertBefore(box, anchor.nextSibling);
        }

        function update() {
            var value = input.value || '';
            items.forEach(function (it) {
                var met = it.rule.test(value);
                it.item.classList.toggle('is-met', met);
                it.icon.className = 'bi ' + (met ? 'bi-check-circle-fill' : 'bi-circle') + ' dlux-password-rules__icon';
            });
        }

        input.addEventListener('focus', function () { update(); box.hidden = false; box.setAttribute('aria-hidden', 'false'); });
        input.addEventListener('input', update);
        input.addEventListener('blur', function () { box.hidden = true; box.setAttribute('aria-hidden', 'true'); });
        // Editing the primary while the confirm checklist is visible should re-evaluate the match.
        if (primary) {
            primary.addEventListener('input', function () { if (!box.hidden) { update(); } });
        }
    }

    function scan(root) {
        // Always bind: the card now replaces the static password help bullets in
        // BOTH modes; strongEnabled() only decides which rule set renders.
        try {
            (root || document).querySelectorAll(SELECTOR).forEach(bind);
        } catch (_e) { /* never throw */ }
    }

    document.addEventListener('DOMContentLoaded', function () { scan(document); });

    // Dlux renders forms inside dynamic modals — pick those up too.
    function observe() {
        var observer = new MutationObserver(function (mutations) {
            for (var i = 0; i < mutations.length; i += 1) {
                var nodes = mutations[i].addedNodes;
                for (var j = 0; j < nodes.length; j += 1) {
                    var node = nodes[j];
                    if (node.nodeType !== 1) { continue; }
                    if ((node.matches && node.matches(SELECTOR)) || (node.querySelector && node.querySelector(SELECTOR))) {
                        scan(node);
                    }
                }
            }
        });
        observer.observe(document.body, { childList: true, subtree: true });
    }
    if (document.body) { observe(); } else { document.addEventListener('DOMContentLoaded', observe); }
})();
