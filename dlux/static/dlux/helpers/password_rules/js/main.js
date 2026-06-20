/**
 * Dlux live password-rules checker.
 * Shows a live requirements checklist under new-password fields on focus, but
 * only when the SystemSettings `enforce_strong_passwords` toggle is on
 * (window.DLUX_CONFIG.enforce_strong_passwords). Rules mirror the server-side
 * dlux.password_validation.DluxStrongPasswordValidator — keep them in sync.
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

    function enabled() {
        try { return !!(window.DLUX_CONFIG && window.DLUX_CONFIG.enforce_strong_passwords); }
        catch (_e) { return false; }
    }

    function t(key, fallback) {
        try {
            var s = window.DLUX_STRINGS || {};
            return (typeof s[key] === 'string' && s[key]) ? s[key] : fallback;
        } catch (_e) { return fallback; }
    }

    var STRENGTH_RULES = [
        { test: function (v) { return v.length >= 12; }, label: function () { return t('password_rule_length', 'At least 12 characters'); } },
        { test: function (v) { return /[A-Z]/.test(v); }, label: function () { return t('password_rule_upper', 'An uppercase letter'); } },
        { test: function (v) { return /[a-z]/.test(v); }, label: function () { return t('password_rule_lower', 'A lowercase letter'); } },
        { test: function (v) { return /[0-9]/.test(v); }, label: function () { return t('password_rule_digit', 'A digit'); } },
        { test: function (v) { return /[^A-Za-z0-9]/.test(v); }, label: function () { return t('password_rule_symbol', 'A symbol'); } }
    ];

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
            : STRENGTH_RULES;

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
        if (!enabled()) { return; }
        try {
            (root || document).querySelectorAll(SELECTOR).forEach(bind);
        } catch (_e) { /* never throw */ }
    }

    document.addEventListener('DOMContentLoaded', function () { scan(document); });

    // Dlux renders forms inside dynamic modals — pick those up too.
    function observe() {
        var observer = new MutationObserver(function (mutations) {
            if (!enabled()) { return; }
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
