/* Setup wizard: the log and profile builders.
 *
 * Both present a UI over a config object that is serialised into one hidden
 * field (`log_config`, `profile_config`) — that field is what posts, so the
 * failure mode is silent: the controls move and the payload does not.
 *
 * The sidebar and navbar builders did NOT come with them. Those two sit inside
 * main.js's mutually-recursive core (104 and 96 transitive dependencies each)
 * and cannot be lifted without breaking the cycle.
 *
 * Depends on setup/js/dom.js.
 */
(function (root) {
    'use strict';

    const {
        setBuilderSectionEnabled,
        t
    } = root.DluxSetupDom;

    function initLogBuilder(root) {
        (root.querySelectorAll ? Array.from(root.querySelectorAll('[data-dlux-log-root]')) : []).forEach(function (rootEl) {
            if (rootEl.dataset.dluxLogInit === '1') { return; }
            rootEl.dataset.dluxLogInit = '1';
            var config;
            try { config = JSON.parse(rootEl.getAttribute('data-config') || '{}'); } catch (e) { config = {}; }
            config = (config && typeof config === 'object') ? config : {};
            config.user = config.user || {};
            config.system = config.system || {};
            config.audit = config.audit || {};
            var form = rootEl.closest('form');
            var hidden = form ? form.querySelector('[name="log_config"]') : null;

            function serialize() { if (hidden) { hidden.value = JSON.stringify(config); } }
            function sectionConf(key) {
                config[key] = config[key] || {};
                config[key].default_actions = config[key].default_actions || {};
                config[key].models = config[key].models || {};
                return config[key];
            }

            var master = rootEl.querySelector('[data-log-master]');
            var dependent = rootEl.querySelector('[data-log-dependent]');
            if (master) {
                master.checked = config.enabled !== false;
                if (dependent) { setBuilderSectionEnabled(dependent, master.checked, t('log_disabled_reason', 'Turn on activity logging to change these.')); }
                master.addEventListener('change', function () {
                    config.enabled = master.checked;
                    if (dependent) { setBuilderSectionEnabled(dependent, master.checked, t('log_disabled_reason', 'Turn on activity logging to change these.')); }
                    serialize();
                });
            }

            rootEl.querySelectorAll('[data-log-section]').forEach(function (sectionEl) {
                var key = sectionEl.getAttribute('data-log-section');
                var conf = sectionConf(key);
                var enabledInput = sectionEl.querySelector('[data-log-section-enabled]');
                var depEl = sectionEl.querySelector('[data-log-section-dependent]');
                if (enabledInput) {
                    enabledInput.checked = conf.enabled !== false;
                    if (depEl) { setBuilderSectionEnabled(depEl, enabledInput.checked, t('log_section_disabled_reason', 'Enable this log section to choose its actions.')); }
                    enabledInput.addEventListener('change', function () {
                        conf.enabled = enabledInput.checked;
                        if (depEl) { setBuilderSectionEnabled(depEl, enabledInput.checked, t('log_section_disabled_reason', 'Enable this log section to choose its actions.')); }
                        serialize();
                    });
                }
                sectionEl.querySelectorAll('[data-log-default-action]').forEach(function (inp) {
                    var act = inp.getAttribute('data-log-default-action');
                    inp.checked = conf.default_actions[act] !== false;
                    inp.addEventListener('change', function () { conf.default_actions[act] = inp.checked; serialize(); });
                });
                var ret = sectionEl.querySelector('[data-log-retention]');
                if (ret) {
                    ret.value = conf.retention_days || 0;
                    ret.addEventListener('input', function () { conf.retention_days = Math.max(0, parseInt(ret.value, 10) || 0); serialize(); });
                }
                sectionEl.querySelectorAll('[data-log-model]').forEach(function (row) {
                    var mkey = row.getAttribute('data-log-model');
                    var override = conf.models[mkey] || {};
                    var enabledCb = row.querySelector('[data-log-model-enabled]');
                    if (enabledCb) {
                        enabledCb.checked = override.enabled !== false;
                        enabledCb.addEventListener('change', function () {
                            conf.models[mkey] = conf.models[mkey] || {};
                            conf.models[mkey].enabled = enabledCb.checked;
                            serialize();
                        });
                    }
                    row.querySelectorAll('[data-log-action]').forEach(function (acb) {
                        var act = acb.getAttribute('data-log-action');
                        var actions = override.actions || {};
                        acb.checked = (act in actions) ? (actions[act] !== false) : (conf.default_actions[act] !== false);
                        acb.addEventListener('change', function () {
                            conf.models[mkey] = conf.models[mkey] || {};
                            conf.models[mkey].actions = conf.models[mkey].actions || {};
                            conf.models[mkey].actions[act] = acb.checked;
                            serialize();
                        });
                    });
                });
                var search = sectionEl.querySelector('[data-log-model-search]');
                if (search) {
                    search.addEventListener('input', function () {
                        var q = (search.value || '').toLowerCase().trim();
                        sectionEl.querySelectorAll('[data-log-model]').forEach(function (row) {
                            var label = row.getAttribute('data-log-model-label') || '';
                            var mk = (row.getAttribute('data-log-model') || '').toLowerCase();
                            var match = !q || label.indexOf(q) !== -1 || mk.indexOf(q) !== -1;
                            row.classList.toggle('dlux-log-row-hidden', !match);
                        });
                    });
                }
            });

            config.audit.events = config.audit.events || {};
            rootEl.querySelectorAll('[data-log-audit-event]').forEach(function (inp) {
                var ev = inp.getAttribute('data-log-audit-event');
                inp.checked = config.audit.events[ev] !== false;
                inp.addEventListener('change', function () { config.audit.events[ev] = inp.checked; serialize(); });
            });
            var auditRet = rootEl.querySelector('[data-log-audit-retention]');
            if (auditRet) {
                auditRet.value = config.audit.retention_days || 0;
                auditRet.addEventListener('input', function () { config.audit.retention_days = Math.max(0, parseInt(auditRet.value, 10) || 0); serialize(); });
            }
            serialize();
        });
    }

    function initProfileBuilder(root) {
        (root.querySelectorAll ? Array.from(root.querySelectorAll('[data-dlux-profile-root]')) : []).forEach(function (rootEl) {
            if (rootEl.dataset.dluxProfileInit === '1') { return; }
            rootEl.dataset.dluxProfileInit = '1';
            var config;
            try { config = JSON.parse(rootEl.getAttribute('data-config') || '{}'); } catch (e) { config = {}; }
            config = (config && typeof config === 'object') ? config : {};
            config.onboarding_options = config.onboarding_options || {};
            var form = rootEl.closest('form');
            var hidden = form ? form.querySelector('[name="profile_config"]') : null;
            function serialize() { if (hidden) { hidden.value = JSON.stringify(config); } }

            rootEl.querySelectorAll('[data-profile-key]').forEach(function (inp) {
                var key = inp.getAttribute('data-profile-key');
                inp.checked = config[key] !== false;
                inp.addEventListener('change', function () { config[key] = inp.checked; serialize(); });
            });
            var nudges = rootEl.querySelector('[data-profile-nudges]');
            if (nudges) {
                nudges.value = config.security_nudges || 'subtle';
                nudges.addEventListener('change', function () { config.security_nudges = nudges.value; serialize(); });
            }
            var onbEnabled = rootEl.querySelector('[data-profile-onboarding-enabled]');
            var onbDep = rootEl.querySelector('[data-profile-onboarding-dependent]');
            if (onbEnabled) {
                onbEnabled.checked = config.onboarding_enabled !== false;
                if (onbDep) { setBuilderSectionEnabled(onbDep, onbEnabled.checked, t('onboarding_disabled_reason', 'Turn on the first-login setup modal to choose what it offers.')); }
                onbEnabled.addEventListener('change', function () {
                    config.onboarding_enabled = onbEnabled.checked;
                    if (onbDep) { setBuilderSectionEnabled(onbDep, onbEnabled.checked, t('onboarding_disabled_reason', 'Turn on the first-login setup modal to choose what it offers.')); }
                    serialize();
                });
            }
            rootEl.querySelectorAll('[data-profile-onboard-key]').forEach(function (inp) {
                var key = inp.getAttribute('data-profile-onboard-key');
                inp.checked = config.onboarding_options[key] !== false;
                inp.addEventListener('change', function () { config.onboarding_options[key] = inp.checked; serialize(); });
            });
            serialize();
        });
    }

    root.DluxSetup = Object.assign(root.DluxSetup || {}, {
        initLogBuilder,
        initProfileBuilder
    });
})(typeof window !== 'undefined' ? window : globalThis);
